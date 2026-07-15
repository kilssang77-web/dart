"""
Cloudflare R2 히스토리 차트 라우터
────────────────────────────────────
데이터 경로:
  최근 1년  → Supabase (SQL, 빠름 <100ms)
  1년 이전  → R2 JSON.gz (boto3 + stdlib gzip/json, pandas/pyarrow 불필요)

R2 파일 구조:
  daily_bars/{code}/{year}.json.gz
  예: daily_bars/005930/2022.json.gz
"""
import gzip
import io
import json
import os
from datetime import date, datetime, timedelta
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query
import asyncpg

from deps import get_db

router = APIRouter()

_R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "")
_R2_ACCESS_KEY = os.environ.get("R2_ACCESS_KEY", "")
_R2_SECRET_KEY = os.environ.get("R2_SECRET_KEY", "")
_R2_BUCKET     = os.environ.get("R2_BUCKET", "quant-eye-history")

_HOT_DAYS = 365  # 최근 1년은 Supabase


@lru_cache(maxsize=1)
def _r2_client():
    """R2 클라이언트 싱글턴 — 환경변수 없으면 None 반환. boto3 lazy import."""
    if not _R2_ACCOUNT_ID:
        return None
    import boto3                          # lazy — startup 메모리 절약
    from botocore.config import Config    # lazy
    return boto3.client(
        "s3",
        endpoint_url=f"https://{_R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=_R2_ACCESS_KEY,
        aws_secret_access_key=_R2_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


async def _fetch_hot(db: asyncpg.Pool, code: str,
                     start: date, end: date) -> list[dict]:
    rows = await db.fetch(
        """
        SELECT date, open, high, low, close, volume, amount, change_rate,
               ma5, ma20, ma60, ma120, rsi14, macd, macd_signal,
               bb_upper, bb_lower, atr14,
               foreign_net_buy, inst_net_buy, indiv_net_buy
        FROM daily_bars
        WHERE code = $1 AND date >= $2 AND date <= $3
        ORDER BY date ASC
        """,
        code, start, end,
    )
    return [
        {**dict(r), "date": r["date"].isoformat()}
        for r in rows
    ]


def _fetch_cold(code: str, year: int,
                start: date, end: date) -> list[dict]:
    """R2에서 daily_bars/{code}/{year}.json.gz 조회."""
    s3 = _r2_client()
    if s3 is None:
        return []
    try:
        key = f"daily_bars/{code}/{year}.json.gz"
        obj = s3.get_object(Bucket=_R2_BUCKET, Key=key)
        with gzip.open(obj["Body"], "rt", encoding="utf-8") as f:
            rows: list[dict] = json.load(f)

        # 날짜 범위 필터
        start_s, end_s = start.isoformat(), end.isoformat()
        return [r for r in rows if start_s <= r.get("date", "") <= end_s]

    except s3.exceptions.NoSuchKey:
        return []
    except Exception:
        return []


@router.get("/history/{code}")
async def get_history(
    code: str,
    start: date = Query(..., description="조회 시작일 (YYYY-MM-DD)"),
    end:   date = Query(default_factory=date.today),
    db: asyncpg.Pool = Depends(get_db),
):
    """
    일봉 히스토리 통합 조회.
    최근 1년: Supabase SQL (빠름)
    1년 이전: Cloudflare R2 JSON.gz (1~2초)
    """
    cutoff = date.today() - timedelta(days=_HOT_DAYS)
    result: list[dict] = []

    # ── R2 구간 (1년 이전) ────────────────────────────────────
    if start < cutoff:
        cold_end = min(cutoff - timedelta(days=1), end)
        for year in range(start.year, cold_end.year + 1):
            result.extend(_fetch_cold(code, year, start, cold_end))

    # ── Supabase 구간 (최근 1년) ──────────────────────────────
    hot_start = max(start, cutoff)
    if hot_start <= end:
        result.extend(await _fetch_hot(db, code, hot_start, end))

    if not result:
        raise HTTPException(404, f"{code} 히스토리 데이터 없음")

    result.sort(key=lambda x: x.get("date", ""))
    return result

"""
Cloudflare R2 히스토리 데이터 내보내기 스크립트
─────────────────────────────────────────────────
DB → JSON.gz → R2 업로드 (per-code, per-year)

실행 방법:
    pip install asyncpg pandas boto3 python-dotenv
    python export_to_r2.py --years 5

R2 버킷 구조:
    quant-eye-history/
    └── daily_bars/
        ├── 005930/
        │   ├── 2020.json.gz
        │   └── 2021.json.gz
        └── 035720/
            └── 2020.json.gz ...

history.py 가 읽는 경로와 동일: daily_bars/{code}/{year}.json.gz
"""
import asyncio
import argparse
import gzip
import io
import json
import os
from datetime import date, datetime

import asyncpg
import pandas as pd
import boto3
from botocore.config import Config
from dotenv import load_dotenv

load_dotenv()

PG_DSN        = os.environ["POSTGRES_DSN"]
R2_ACCOUNT_ID = os.environ["R2_ACCOUNT_ID"]
R2_ACCESS_KEY = os.environ["R2_ACCESS_KEY"]
R2_SECRET_KEY = os.environ["R2_SECRET_KEY"]
R2_BUCKET     = os.environ.get("R2_BUCKET", "quant-eye-history")

# history.py 의 _fetch_cold 가 읽는 컬럼 목록과 일치시킴
_DAILY_COLS = [
    "date", "open", "high", "low", "close", "volume", "amount", "change_rate",
    "ma5", "ma20", "ma60", "ma120", "rsi14", "macd", "macd_signal",
    "bb_upper", "bb_lower", "atr14",
    "foreign_net_buy", "inst_net_buy", "indiv_net_buy",
]


def _r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def _to_json_gz(records: list[dict]) -> bytes:
    """list[dict] → gzip 압축된 JSON bytes."""
    raw = json.dumps(records, ensure_ascii=False, default=str).encode("utf-8")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        gz.write(raw)
    return buf.getvalue()


async def export_daily_bars(conn: asyncpg.Connection, s3, year: int) -> int:
    """daily_bars 테이블 → daily_bars/{code}/{year}.json.gz 로 R2 업로드."""
    start = date(year, 1, 1)
    end   = date(year + 1, 1, 1)

    rows = await conn.fetch(
        """
        SELECT code, date, open, high, low, close, volume, amount, change_rate,
               ma5, ma20, ma60, ma120, rsi14, macd, macd_signal,
               bb_upper, bb_lower, atr14,
               foreign_net_buy, inst_net_buy, indiv_net_buy
        FROM daily_bars
        WHERE date >= $1 AND date < $2
        ORDER BY code, date
        """,
        start, end,
    )

    if not rows:
        print(f"  [daily_bars/{year}] 데이터 없음, 건너뜀")
        return 0

    # code별 그룹화
    df = pd.DataFrame([dict(r) for r in rows])
    df["date"] = df["date"].apply(
        lambda d: d.isoformat() if hasattr(d, "isoformat") else str(d)
    )

    uploaded = 0
    for code, grp in df.groupby("code"):
        records = grp[_DAILY_COLS].fillna(0).to_dict("records")

        payload = _to_json_gz(records)
        key     = f"daily_bars/{code}/{year}.json.gz"

        s3.put_object(
            Bucket=R2_BUCKET,
            Key=key,
            Body=payload,
            ContentType="application/gzip",
        )
        uploaded += 1

    total_rows = len(df)
    print(
        f"  [daily_bars/{year}] {total_rows:,}행 → "
        f"{uploaded}개 종목 파일 업로드 완료"
    )
    return total_rows


async def main(years: int):
    current_year = datetime.now().year
    start_year   = current_year - years

    conn = await asyncpg.connect(PG_DSN)
    s3   = _r2_client()

    try:
        grand_total = 0
        for year in range(start_year, current_year + 1):
            print(f"\n[{year}년] 처리 중...")
            grand_total += await export_daily_bars(conn, s3, year)

        print(f"\n✅ R2 내보내기 완료: {grand_total:,}행")
        print(f"버킷: {R2_BUCKET}")
        print("경로 형식: daily_bars/{{code}}/{{year}}.json.gz")

    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="daily_bars → Cloudflare R2 JSON.gz 내보내기")
    parser.add_argument("--years", type=int, default=5, help="내보낼 연도 수 (기본: 5년)")
    args = parser.parse_args()

    asyncio.run(main(args.years))

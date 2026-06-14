"""
pattern_vector 백필 스크립트 v2.
PatternEmbedder(OHLCV 기반 256차원)를 사용하여 벡터 재계산.

변경 이력:
  v1: signal_score/risk_score 5값 + 251 제로 패딩 (품질 불량)
  v2: daily_bars OHLCV 20일 창 기반 PatternEmbedder 사용

사용:
  # 신규 NULL 레코드만 처리
  docker exec fstock-ml python scripts/backfill_vectors.py

  # 기존 벡터 전체 재계산 (v1→v2 마이그레이션)
  docker exec fstock-ml python scripts/backfill_vectors.py --reset

  # 특정 코드만 처리
  docker exec fstock-ml python scripts/backfill_vectors.py --code 005930

  # 건식 실행 (DB 쓰기 없음)
  docker exec fstock-ml python scripts/backfill_vectors.py --dry-run
"""
import argparse
import asyncio
import logging
import os
import random
import sys

import asyncpg
import numpy as np
import pandas as pd

sys.path.insert(0, "/app")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [backfill] %(levelname)s - %(message)s",
)
logger = logging.getLogger("backfill")

_BATCH_CODES = 30   # 읽기 병렬 종목 수
_MIN_BARS    = 20   # 벡터 생성 최소 일봉 수
_WRITE_BATCH = 2000 # 한 번에 DB에 쓸 최대 행 수


def _get_embedder():
    try:
        from similarity.pattern_embedder import PatternEmbedder
        return PatternEmbedder()
    except ImportError:
        logger.error("PatternEmbedder import 실패 — /app/similarity/ 경로 확인 필요")
        return None


def _embed_for_event(embedder, bars_df: pd.DataFrame, detected_at) -> list[float] | None:
    """detected_at 이전 20개 일봉으로 벡터 생성."""
    try:
        event_date = pd.Timestamp(detected_at).normalize().tz_localize(None)
    except TypeError:
        event_date = pd.Timestamp(detected_at).normalize()
    window = bars_df[bars_df["date"] <= event_date].tail(20)
    if len(window) < _MIN_BARS:
        return None
    vec = embedder.embed(window)
    if not np.isfinite(vec).all():
        vec = np.nan_to_num(vec, nan=0.0, posinf=1.0, neginf=-1.0)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
    return vec.tolist()


async def fetch_code_data(pool: asyncpg.Pool, code: str, reset: bool) -> tuple[pd.DataFrame, list]:
    """한 종목의 일봉 + 이벤트 데이터를 읽기 전용으로 로드."""
    async with pool.acquire() as conn:
        bar_rows = await conn.fetch(
            """
            SELECT date, open, high, low, close, volume, foreign_net_buy AS foreign_net
            FROM daily_bars
            WHERE code = $1 AND close > 0
            ORDER BY date
            """,
            code,
        )
        where = "code = $1" if reset else "code = $1 AND pattern_vector IS NULL"
        event_rows = await conn.fetch(
            f"SELECT id, detected_at FROM feature_events WHERE {where} ORDER BY id",
            code,
        )
    if not bar_rows:
        return pd.DataFrame(), []
    bars_df = pd.DataFrame([dict(r) for r in bar_rows])
    bars_df["date"] = pd.to_datetime(bars_df["date"])
    bars_df = bars_df.sort_values("date").reset_index(drop=True)
    return bars_df, list(event_rows)


async def write_updates_sorted(
    pool: asyncpg.Pool,
    updates: list[tuple[int, str]],
    dry_run: bool,
) -> int:
    """updates를 id 오름차순으로 정렬 후 unnest 단일 쿼리로 쓰기 (deadlock 방지 + 빠름)."""
    if not updates or dry_run:
        return len(updates) if dry_run else 0

    updates_sorted = sorted(updates, key=lambda x: x[0])

    written = 0
    for i in range(0, len(updates_sorted), _WRITE_BATCH):
        chunk = updates_sorted[i:i + _WRITE_BATCH]
        ids   = [u[0] for u in chunk]
        vecs  = [u[1] for u in chunk]
        # unnest 단일 UPDATE — executemany(N rows) 대비 ~10x 빠름
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE feature_events fe
                SET pattern_vector = upd.vec
                FROM (
                    SELECT UNNEST($1::bigint[]) AS id,
                           UNNEST($2::text[])::vector AS vec
                ) AS upd
                WHERE fe.id = upd.id
                """,
                ids, vecs,
            )
        written += len(chunk)
    return written


async def main(batch_codes: int, reset: bool, dry_run: bool, target_code: str | None):
    pool = await asyncpg.create_pool(
        dsn=os.environ["POSTGRES_DSN"].replace("+asyncpg", ""),
        min_size=4,
        max_size=10,
    )

    embedder = _get_embedder()
    if embedder is None:
        await pool.close()
        return

    if reset:
        logger.warning("--reset 모드: 모든 pattern_vector를 NULL로 초기화합니다")
        if not dry_run:
            reset_clause = f"WHERE code = $1" if target_code else ""
            params = [target_code] if target_code else []
            await pool.execute(
                f"UPDATE feature_events SET pattern_vector = NULL {reset_clause}",
                *params,
            )
            logger.info("초기화 완료")

    # 대상 종목 목록
    code_params = [target_code] if target_code else []
    code_where  = "AND code = $1" if target_code else ""

    code_rows = await pool.fetch(
        f"SELECT DISTINCT code FROM feature_events WHERE pattern_vector IS NULL {code_where} ORDER BY code",
        *code_params,
    )
    codes = [r["code"] for r in code_rows]

    total_events = await pool.fetchval(
        f"SELECT COUNT(*) FROM feature_events WHERE pattern_vector IS NULL {code_where}",
        *code_params,
    )

    logger.info(f"대상: {total_events}건 / {len(codes)}개 종목 (reset={reset}, dry_run={dry_run})")
    if not codes:
        logger.info("처리 대상 없음 — 종료")
        await pool.close()
        return

    updated_total = 0
    codes_done    = 0

    for i in range(0, len(codes), batch_codes):
        chunk = codes[i:i + batch_codes]

        # ── 1. 병렬 읽기 ──────────────────────────────────────────
        fetch_tasks = [fetch_code_data(pool, code, reset=False) for code in chunk]
        fetch_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

        # ── 2. CPU 임베딩 계산 (메모리에서) ────────────────────────
        all_updates: list[tuple[int, str]] = []
        for code, result in zip(chunk, fetch_results):
            if isinstance(result, Exception):
                logger.error(f"{code} 읽기 오류: {result}")
                continue
            bars_df, events = result
            if bars_df.empty:
                continue
            for ev in events:
                vec = _embed_for_event(embedder, bars_df, ev["detected_at"])
                if vec is not None:
                    all_updates.append((ev["id"], str(vec)))

        # ── 3. 순차 쓰기 (id 정렬 → deadlock 없음) ─────────────────
        written = await write_updates_sorted(pool, all_updates, dry_run)
        updated_total += written
        codes_done    += len(chunk)

        pct = round(updated_total / max(total_events, 1) * 100, 1)
        logger.info(
            f"진행: {updated_total}/{total_events} ({pct}%) — "
            f"종목 {codes_done}/{len(codes)}"
        )

    logger.info(f"완료 — 총 {updated_total}건 업데이트")
    await pool.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-codes", type=int, default=_BATCH_CODES, help="병렬 읽기 종목 수")
    parser.add_argument("--reset", action="store_true", help="기존 벡터 NULL 초기화 후 전체 재계산")
    parser.add_argument("--dry-run", action="store_true", help="DB 쓰기 없이 테스트")
    parser.add_argument("--code", type=str, default=None, help="특정 종목 코드만 처리")
    args = parser.parse_args()
    asyncio.run(main(args.batch_codes, args.reset, args.dry_run, args.code))

#!/usr/bin/env python3
"""
feature_events 테이블에서 pattern_vector가 없는 행을 소급 생성하는 스크립트.

실행 방법:
  docker exec fstock-ml python scripts/backfill_pattern_vectors.py [--batch 500] [--limit 0]

--batch : 한 번에 처리할 이벤트 수 (기본 500)
--limit : 총 처리 최대 건수, 0=전체 (기본 0)
"""
import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta

import asyncpg
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from similarity.pattern_embedder import PatternEmbedder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("backfill_vectors")

_WINDOW    = 20      # PatternEmbedder 참조 일수
_PRE_DAYS  = _WINDOW + 5  # 이벤트 날짜 이전 데이터 로딩 여유


async def _fetch_events_without_vector(
    pool: asyncpg.Pool, batch: int, offset: int
) -> list[dict]:
    rows = await pool.fetch(
        """
        SELECT id, code, detected_at::date AS event_date
        FROM feature_events
        WHERE pattern_vector IS NULL
        ORDER BY detected_at DESC
        LIMIT $1 OFFSET $2
        """,
        batch, offset,
    )
    return [dict(r) for r in rows]


async def _load_bars(
    pool: asyncpg.Pool, code: str, event_date
) -> list[dict]:
    """이벤트 날짜 포함 직전 _PRE_DAYS 일치 일봉 로드."""
    from datetime import date as date_type, timedelta
    if not isinstance(event_date, date_type):
        from datetime import datetime
        event_date = datetime.strptime(str(event_date), "%Y-%m-%d").date()
    since = event_date - timedelta(days=_PRE_DAYS)
    rows = await pool.fetch(
        """
        SELECT d.date, d.close, d.high, d.low, d.open, d.volume,
               COALESCE(sd.foreign_net, d.foreign_net_buy) AS foreign_net
        FROM daily_bars d
        LEFT JOIN supply_demand sd
               ON sd.code = d.code AND sd.date = d.date
        WHERE d.code = $1
          AND d.date <= $2
          AND d.date >= $3
          AND d.close > 0
        ORDER BY d.date
        """,
        code, event_date, since,
    )
    return [dict(r) for r in rows]


async def _update_vector(
    pool: asyncpg.Pool, event_id: int, vec: np.ndarray
) -> None:
    # pgvector는 '[x,y,...]' 형식 문자열로 입력
    vec_str = "[" + ",".join(f"{v:.8f}" for v in vec.tolist()) + "]"
    await pool.execute(
        "UPDATE feature_events SET pattern_vector = $1::vector WHERE id = $2",
        vec_str, event_id,
    )


async def run(batch: int, limit: int):
    dsn = os.environ["POSTGRES_DSN"].replace("+asyncpg", "")
    pool = await asyncpg.create_pool(dsn=dsn, min_size=2, max_size=6)
    embedder = PatternEmbedder()

    # 전체 미처리 건수 확인
    total_missing = await pool.fetchval(
        "SELECT COUNT(*) FROM feature_events WHERE pattern_vector IS NULL"
    )
    logger.info(f"벡터 없는 이벤트: {total_missing:,}건")

    if total_missing == 0:
        logger.info("백필 불필요 — 모든 이벤트에 벡터 존재")
        await pool.close()
        return

    to_process = total_missing if limit == 0 else min(limit, total_missing)
    logger.info(f"처리 예정: {to_process:,}건 (batch={batch})")

    processed = 0
    skipped   = 0
    offset    = 0

    while processed < to_process:
        events = await _fetch_events_without_vector(pool, batch, offset)
        if not events:
            break

        for ev in events:
            if processed >= to_process:
                break

            bars = await _load_bars(pool, ev["code"], ev["event_date"])
            if len(bars) < 5:
                skipped += 1
                offset  += 1
                continue

            import pandas as pd
            df = pd.DataFrame(bars)
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)

            vec = embedder.embed(df, window=min(_WINDOW, len(df)))

            if np.all(vec == 0):
                skipped += 1
                offset  += 1
                continue

            await _update_vector(pool, ev["id"], vec)
            processed += 1

            if processed % 1000 == 0:
                logger.info(f"진행: {processed:,}/{to_process:,} (skipped={skipped})")

        # offset은 skipped 건만큼 증가 (processed 건은 이미 벡터가 채워졌으므로
        # 다음 조회 시 WHERE pattern_vector IS NULL 에서 제외됨)

    await pool.close()
    logger.info(
        f"백필 완료 — 처리: {processed:,}건, 스킵: {skipped:,}건 "
        f"(데이터 부족 또는 제로 벡터)"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, default=500, help="배치 크기 (기본 500)")
    parser.add_argument("--limit", type=int, default=0,   help="처리 최대 건수, 0=전체")
    args = parser.parse_args()
    asyncio.run(run(args.batch, args.limit))

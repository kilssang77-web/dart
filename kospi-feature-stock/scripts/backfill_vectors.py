"""
feature_events.pattern_vector가 NULL인 이벤트에 대해 일괄 벡터 생성.

사용:
  # Docker 내부
  docker exec -it fstock-recommender python /app/scripts/backfill_vectors.py

  # 로컬 (POSTGRES_DSN 환경변수 필요)
  python scripts/backfill_vectors.py [--limit N]
"""
import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# recommender의 pattern_vector 모듈 사용
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "recommender"))

import asyncpg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill_vectors")


async def main(limit: int):
    from pattern_vector import update_pattern_vector

    dsn = os.environ.get("POSTGRES_DSN", "").replace("+asyncpg", "")
    if not dsn:
        logger.error("POSTGRES_DSN 환경변수가 설정되지 않았습니다.")
        sys.exit(1)

    pool = await asyncpg.create_pool(dsn=dsn, min_size=2, max_size=5)

    rows = await pool.fetch(
        """
        SELECT id, code FROM feature_events
        WHERE pattern_vector IS NULL
        ORDER BY detected_at DESC
        LIMIT $1
        """,
        limit,
    )
    logger.info(f"Backfill 대상: {len(rows)}건")

    ok, fail = 0, 0
    for r in rows:
        result = await update_pattern_vector(pool, r["id"], r["code"])
        if result:
            ok += 1
        else:
            fail += 1
        await asyncio.sleep(0.05)

    logger.info(f"완료: ok={ok}, fail={fail}")
    await pool.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10000, help="최대 처리 건수")
    args = parser.parse_args()
    asyncio.run(main(args.limit))

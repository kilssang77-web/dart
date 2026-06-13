"""
pattern_vector 백필 스크립트.
feature_events WHERE pattern_vector IS NULL 대상으로 벡터 재계산 후 업데이트.

사용:
  docker exec ml_trainer python scripts/backfill_vectors.py [--batch 500] [--dry-run]
"""
import argparse
import asyncio
import logging
import os
import sys

import asyncpg
import numpy as np

sys.path.insert(0, "/app")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [backfill] %(levelname)s - %(message)s")
logger = logging.getLogger("backfill")

_BATCH = 500


def _build_vector(row: dict) -> list[float] | None:
    """feature_events 행에서 256차원 패턴 벡터를 생성 (단순화 버전)."""
    try:
        from features.technical import TechnicalFeatureExtractor
        from features.supply_demand import SupplyDemandFeatureExtractor
    except ImportError:
        logger.error("Feature extractors not found — run from /app")
        return None

    # feature_events에 저장된 컬럼으로 최소 벡터 구성
    v = [
        float(row.get("signal_score") or 0),
        float(row.get("risk_score") or 0),
        float(row.get("result_1d") or 0),
        float(row.get("result_3d") or 0),
        float(row.get("result_5d") or 0),
    ]
    # 256차원으로 패딩 (zero)
    v += [0.0] * (256 - len(v))
    v = v[:256]
    # L2 정규화
    arr = np.array(v, dtype=np.float32)
    norm = np.linalg.norm(arr)
    if norm > 0:
        arr = arr / norm
    return arr.tolist()


async def main(batch: int, dry_run: bool):
    pool = await asyncpg.create_pool(
        dsn=os.environ["POSTGRES_DSN"].replace("+asyncpg", ""),
        min_size=2, max_size=5,
    )

    total = await pool.fetchval(
        "SELECT COUNT(*) FROM feature_events WHERE pattern_vector IS NULL"
    )
    logger.info(f"대상: {total}건 (pattern_vector IS NULL)")

    if total == 0:
        logger.info("백필 대상 없음 — 종료")
        await pool.close()
        return

    offset = 0
    updated = 0

    while offset < total:
        rows = await pool.fetch(
            """
            SELECT id, signal_score, risk_score, result_1d, result_3d, result_5d
            FROM feature_events
            WHERE pattern_vector IS NULL
            ORDER BY id
            LIMIT $1 OFFSET $2
            """,
            batch, offset,
        )
        if not rows:
            break

        updates = []
        for row in rows:
            vec = _build_vector(dict(row))
            if vec is not None:
                updates.append((row["id"], vec))

        if not dry_run and updates:
            async with pool.acquire() as conn:
                await conn.executemany(
                    "UPDATE feature_events SET pattern_vector=$2::vector WHERE id=$1",
                    [(uid, str(v)) for uid, v in updates],
                )
            updated += len(updates)
            logger.info(f"업데이트 {updated}/{total} ({offset+len(rows)}건 처리)")
        else:
            logger.info(f"[dry-run] {offset}~{offset+len(rows)} 처리 예정")

        offset += len(rows)

    logger.info(f"완료 — 총 {updated}건 업데이트")
    await pool.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, default=_BATCH)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.batch, args.dry_run))

"""
feature_events.result_1d/3d/5d 사후 업데이트 (수동 실행용).
ML main.py 루프에서 자동으로 실행되나, 수동 트리거가 필요할 때 사용.

사용: docker compose run --rm ml python /app/scripts/update_event_results.py
"""
import asyncio
import asyncpg
import os
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("update-results")


async def main():
    pool = await asyncpg.create_pool(
        dsn=os.environ["POSTGRES_DSN"].replace("+asyncpg", ""),
        min_size=2, max_size=5,
    )
    cutoff = datetime.now() - timedelta(hours=1)

    async with pool.acquire() as conn:
        events = await conn.fetch(
            """
            SELECT id, code, detected_at::TEXT AS dt
            FROM feature_events
            WHERE result_1d IS NULL
              AND detected_at < $1
            LIMIT 500
            """,
            cutoff,
        )
        updated = 0
        for ev in events:
            code = ev["code"]
            dt   = ev["dt"][:10]
            rows = await conn.fetch(
                """
                SELECT date::TEXT, close
                FROM daily_bars
                WHERE code = $1 AND date >= $2
                ORDER BY date
                LIMIT 6
                """,
                code, dt,
            )
            if len(rows) >= 2:
                entry = float(rows[0]["close"])
                def ret(n):
                    if len(rows) > n:
                        return round((float(rows[n]["close"]) - entry) / entry * 100, 2)
                    return None
                await conn.execute(
                    """
                    UPDATE feature_events
                    SET result_1d=$2, result_3d=$3, result_5d=$4
                    WHERE id=$1
                    """,
                    ev["id"], ret(1), ret(3), ret(5),
                )
                updated += 1

    logger.info(f"Updated {updated}/{len(events)} events")
    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())

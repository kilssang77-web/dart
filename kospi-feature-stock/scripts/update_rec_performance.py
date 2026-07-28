"""
Supabase 기반 추천 성과 자동 업데이트 (GitHub Actions daily cron).

로직:
  1. recommendations 에서 최근 10일 이내 signal_time 행 조회
  2. daily_bars 로 1d/3d/5d 후 종가 JOIN
  3. recommendation_performance 에 r_1d, r_3d, r_5d, hit_target, hit_stop, is_success 업데이트
  4. tracking_complete = TRUE (5영업일치 모두 확보 시)
"""
import asyncio
import logging
import os
from datetime import date, timedelta

import asyncpg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("rec_perf")


async def main():
    dsn = os.environ["POSTGRES_DSN"].replace("+asyncpg", "")
    conn = await asyncpg.connect(dsn)
    try:
        since = date.today() - timedelta(days=10)

        # 1. r_1d 업데이트 (signal_time + 1 영업일 종가)
        for offset_days, col in [(1, "r_1d"), (3, "r_3d"), (5, "r_5d")]:
            n = await conn.execute(f"""
                UPDATE recommendation_performance rp
                SET {col} = ROUND(((b.close / r.entry_price) - 1) * 100, 2)
                FROM recommendations r
                JOIN daily_bars b
                  ON b.code = r.code
                 AND b.date = (
                     SELECT MIN(date) FROM daily_bars
                     WHERE code = r.code
                       AND date >= (r.signal_time::date + $1)
                 )
                WHERE rp.rec_id = r.id
                  AND r.entry_price > 0
                  AND r.signal_time::date >= $2
                  AND rp.{col} IS NULL
            """, offset_days, since)
            log.info(f"{col} 업데이트: {n}")

        # 2. hit_target / hit_stop / is_success 업데이트 (5일간 고/저가 기준)
        n = await conn.execute("""
            UPDATE recommendation_performance rp
            SET
              hit_target = EXISTS (
                SELECT 1 FROM daily_bars b2
                 JOIN recommendations r2 ON r2.id = rp.rec_id
                WHERE b2.code = r2.code
                  AND b2.date BETWEEN r2.signal_time::date AND r2.signal_time::date + 5
                  AND b2.high >= r2.target_price
              ),
              hit_stop = EXISTS (
                SELECT 1 FROM daily_bars b3
                 JOIN recommendations r3 ON r3.id = rp.rec_id
                WHERE b3.code = r3.code
                  AND b3.date BETWEEN r3.signal_time::date AND r3.signal_time::date + 5
                  AND b3.low <= r3.stop_loss_price
              )
            FROM recommendations r
            WHERE rp.rec_id = r.id
              AND r.signal_time::date >= $1
              AND rp.r_5d IS NOT NULL
              AND rp.hit_target IS NULL
        """, since)
        log.info(f"hit_target/hit_stop 업데이트: {n}")

        # 3. is_success = 목표가 도달 AND 손절 미도달
        n = await conn.execute("""
            UPDATE recommendation_performance
            SET is_success = (hit_target = TRUE AND hit_stop = FALSE),
                tracking_complete = TRUE,
                last_updated = NOW()
            WHERE r_5d IS NOT NULL
              AND hit_target IS NOT NULL
              AND tracking_complete IS NOT TRUE
        """)
        log.info(f"is_success/tracking_complete 완료: {n}")

        log.info("추천 성과 업데이트 완료")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

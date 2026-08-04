"""
Supabase 기반 추천 성과 자동 업데이트 (GitHub Actions daily cron).

로직:
  0. recommendation_performance 테이블 없으면 자동 생성 + BUY 추천 백필
  1. recommendations 에서 최근 30일 이내 created_at 행 조회
  2. daily_bars 로 1d/3d/5d 후 종가 JOIN
  3. recommendation_performance 에 r_1d, r_3d, r_5d, hit_target, hit_stop, is_success 업데이트
  4. tracking_complete = TRUE (5영업일치 모두 확보 시)
"""
import asyncio
import json
import logging
import os
from datetime import date, timedelta

import asyncpg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("rec_perf")


def _publish_performance_summary(total: int, wins: int, rate: float, avg_r5d: float) -> None:
    """최근 30일 실전 승률을 ch:tg-outbox로 발행 (샘플 충분 시에만)."""
    redis_url = os.environ.get("REDIS_URL", "")
    if not redis_url or total < 5:
        return
    try:
        import redis as _r
        from datetime import datetime, timezone, timedelta
        kst = timezone(timedelta(hours=9))
        today = datetime.now(kst).date()
        text = (
            f"<b>📈 추천 성과 업데이트 ({today})</b>\n"
            f"최근 30일: 총{total}건  ✅{wins}건  승률 <b>{rate:.0%}</b>  "
            f"평균5일수익 {avg_r5d:+.2f}%"
        )
        rc = _r.from_url(redis_url, decode_responses=True, socket_timeout=5)
        rc.publish("ch:tg-outbox", json.dumps({
            "text": text, "msg_type": "performance_summary",
            "title": f"추천 성과 업데이트 {today}",
        }, ensure_ascii=False))
        rc.close()
        log.info("성과 요약 Redis 발행 완료 (ch:tg-outbox)")
    except Exception as e:
        log.warning(f"Redis publish 실패: {e}")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS recommendation_performance (
    id               BIGSERIAL PRIMARY KEY,
    rec_id           BIGINT NOT NULL,
    code             VARCHAR(10) NOT NULL,
    entry_price      NUMERIC,
    event_type       VARCHAR(50),
    signal_time      TIMESTAMPTZ,
    r_1d   NUMERIC, r_3d  NUMERIC, r_5d  NUMERIC,
    hit_target        BOOLEAN,
    hit_stop          BOOLEAN,
    is_success        BOOLEAN,
    tracking_complete BOOLEAN DEFAULT FALSE,
    last_updated      TIMESTAMPTZ DEFAULT NOW(),
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(rec_id)
);
CREATE INDEX IF NOT EXISTS idx_rec_perf_code     ON recommendation_performance (code);
CREATE INDEX IF NOT EXISTS idx_rec_perf_complete ON recommendation_performance (tracking_complete)
    WHERE tracking_complete = FALSE;
"""

_BACKFILL_SQL = """
INSERT INTO recommendation_performance (rec_id, code, entry_price, event_type, signal_time)
SELECT
    r.id,
    r.code,
    r.entry_price,
    (r.rationale::json ->> 'event_type'),
    r.created_at
FROM recommendations r
WHERE r.action = 'BUY'
ON CONFLICT (rec_id) DO NOTHING
"""


async def main():
    raw_dsn = os.environ.get("POSTGRES_DSN", "")
    dsn = raw_dsn.replace("+asyncpg", "")
    ssl = "require" if "supabase" in dsn else False
    # DSN 진단 로그 (비밀번호 마스킹)
    try:
        from urllib.parse import urlparse
        _p = urlparse(dsn)
        log.info(f"DB 연결 시도: {_p.scheme}://{_p.hostname}:{_p.port}{_p.path} ssl={ssl}")
    except Exception:
        log.info(f"DB 연결 시도: DSN 길이={len(dsn)} ssl={ssl}")
    conn = await asyncpg.connect(dsn, statement_cache_size=0, ssl=ssl)
    try:
        # 0. 테이블 자동 생성 + 백필 (Supabase 최초 실행 시)
        await conn.execute(_CREATE_TABLE)
        n_backfill = await conn.execute(_BACKFILL_SQL)
        log.info(f"백필 완료: {n_backfill}")

        since = date.today() - timedelta(days=30)

        # 1. r_1d / r_3d / r_5d 업데이트 (created_at + N 영업일 종가)
        for offset_days, col in [(1, "r_1d"), (3, "r_3d"), (5, "r_5d")]:
            n = await conn.execute(f"""
                UPDATE recommendation_performance rp
                SET {col} = ROUND(((b.close::numeric / r.entry_price) - 1) * 100, 2)
                FROM recommendations r
                JOIN daily_bars b
                  ON b.code = r.code
                 AND b.date = (
                     SELECT MIN(date) FROM daily_bars
                     WHERE code = r.code
                       AND date >= (r.created_at + ($1::int * INTERVAL '1 day'))::date
                 )
                WHERE rp.rec_id = r.id
                  AND r.entry_price > 0
                  AND r.created_at::date >= $2
                  AND rp.{col} IS NULL
            """, offset_days, since)
            log.info(f"{col} 업데이트: {n}")

        # 2. hit_target / hit_stop 업데이트 (5일간 고/저가 기준, target/stop NULL 방어)
        n = await conn.execute("""
            UPDATE recommendation_performance rp
            SET
              hit_target = COALESCE((
                SELECT TRUE FROM daily_bars b2
                 JOIN recommendations r2 ON r2.id = rp.rec_id
                WHERE b2.code = r2.code
                  AND b2.date BETWEEN r2.created_at::date AND (r2.created_at + INTERVAL '5 days')::date
                  AND r2.target_price IS NOT NULL
                  AND b2.high >= r2.target_price
                LIMIT 1
              ), FALSE),
              hit_stop = COALESCE((
                SELECT TRUE FROM daily_bars b3
                 JOIN recommendations r3 ON r3.id = rp.rec_id
                WHERE b3.code = r3.code
                  AND b3.date BETWEEN r3.created_at::date AND (r3.created_at + INTERVAL '5 days')::date
                  AND r3.stop_loss_price IS NOT NULL
                  AND b3.low <= r3.stop_loss_price
                LIMIT 1
              ), FALSE),
              last_updated = NOW()
            FROM recommendations r
            WHERE rp.rec_id = r.id
              AND r.created_at::date >= $1
              AND rp.r_5d IS NOT NULL
              AND NOT COALESCE(rp.tracking_complete, FALSE)
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
              AND NOT COALESCE(tracking_complete, FALSE)
        """)
        log.info(f"is_success/tracking_complete 완료: {n}")

        # 4. 최근 30일 실전 승률 집계 → Redis 발행
        stats = await conn.fetchrow("""
            SELECT
                COUNT(*)                                          AS total,
                SUM(CASE WHEN is_success THEN 1 ELSE 0 END)     AS wins,
                AVG(r_5d)                                         AS avg_r5d
            FROM recommendation_performance rp
            JOIN recommendations r ON r.id = rp.rec_id
            WHERE tracking_complete = TRUE
              AND r.created_at >= NOW() - INTERVAL '30 days'
        """)
        total  = int(stats["total"] or 0)
        wins   = int(stats["wins"]  or 0)
        avg_r5 = float(stats["avg_r5d"] or 0.0)
        rate   = wins / total if total > 0 else 0.0
        log.info(f"최근 30일 성과: 총{total}건 성공{wins}건 승률{rate:.1%} 평균5일수익{avg_r5:+.2f}%")

        _publish_performance_summary(total, wins, rate, avg_r5)
        log.info("추천 성과 업데이트 완료")
    finally:
        await conn.close()


if __name__ == "__main__":
    import sys
    try:
        asyncio.run(main())
    except Exception as e:
        log.error(f"[FATAL] {type(e).__name__}: {e}", exc_info=True)
        sys.exit(1)

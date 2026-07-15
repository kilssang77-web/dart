"""
DB 보존 정책 — GitHub Actions에서 매일 실행.

보존 기간:
  news           30일  (기사 본문이 전체의 73%)
  supply_demand  60일
  disclosures   180일
  feature_events 365일
  recommendations 365일
  telegram_logs   90일

news_stock_links 는 news FK ON DELETE CASCADE 로 자동 삭제.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone

import asyncpg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("db-retention")

RULES = [
    # (table, date_column, keep_days, label)
    ("news",            "created_at",   30,  "뉴스"),
    ("supply_demand",   "date",         60,  "수급 데이터"),
    ("disclosures",     "disclosed_at", 180, "공시"),
    ("feature_events",  "detected_at",  365, "특징 이벤트"),
    ("recommendations", "created_at",   365, "매매 추천"),
    ("telegram_logs",   "sent_at",       90, "텔레그램 로그"),
]


async def main() -> None:
    dsn = os.environ["POSTGRES_DSN"].replace("+asyncpg", "")
    ssl_val = "require" if "supabase" in dsn else False

    conn = await asyncpg.connect(dsn, ssl=ssl_val)
    log.info("DB 연결 완료")
    log.info("실행 시각: %s", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    log.info("=" * 56)

    total_deleted = 0
    vacuumed = []
    for table, col, days, label in RULES:
        try:
            result = await conn.execute(
                f"DELETE FROM {table} WHERE {col} < NOW() - INTERVAL '{days} days'"
            )
            cnt = int(result.split()[-1])
            total_deleted += cnt
            log.info("  %-20s -%6d rows  (보존 %d일)", label, cnt, days)
            if cnt > 0:
                vacuumed.append(table)
        except Exception as e:
            log.warning("  %-20s ERROR: %s", label, e)

    # 삭제된 테이블만 VACUUM — 공간 즉시 반환
    for table in vacuumed:
        try:
            await conn.execute(f"VACUUM ANALYZE {table}")
            log.info("  VACUUM %-20s 완료", table)
        except Exception as e:
            log.warning("  VACUUM %s ERROR: %s", table, e)

    # news 삭제 시 news_stock_links도 CASCADE 삭제되므로 별도 VACUUM
    if "news" in vacuumed:
        try:
            await conn.execute("VACUUM ANALYZE news_stock_links")
            log.info("  VACUUM %-20s 완료", "news_stock_links")
        except Exception as e:
            log.warning("  VACUUM news_stock_links ERROR: %s", e)

    size = await conn.fetchrow(
        "SELECT pg_size_pretty(pg_database_size(current_database())) AS pretty,"
        "       pg_database_size(current_database()) AS bytes"
    )
    mb = size["bytes"] / 1024 / 1024
    status = "✅ 여유" if mb < 400 else "⚠️ 주의" if mb < 480 else "🚨 위험"

    log.info("=" * 56)
    log.info("  삭제 합계 : %d rows", total_deleted)
    log.info("  DB 크기   : %s (%.1f MB)  %s", size["pretty"], mb, status)
    log.info("  무료 한도 : 500 MB")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

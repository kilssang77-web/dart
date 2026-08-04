"""
당일 추천 결과 텔레그램 알림 — GitHub Actions에서 실행.
직접 Telegram 발송 대신 Redis ch:tg-outbox 발행 → notifier 컨테이너가 처리.
"""
import asyncio
import json
import logging
import os
from datetime import date

import asyncpg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("notify-telegram")


def _publish_tg_outbox(text: str) -> None:
    """Redis ch:tg-outbox 발행 → notifier가 Telegram 발송."""
    redis_url = os.environ.get("REDIS_URL", "")
    if not redis_url:
        logger.warning("REDIS_URL 미설정 — 알림 발행 스킵")
        return
    try:
        import redis as _r
        rc = _r.from_url(redis_url, decode_responses=True, socket_timeout=5)
        rc.publish("ch:tg-outbox", json.dumps({
            "text": text, "msg_type": "daily_summary",
            "title": "오늘의 추천 종목 요약",
        }, ensure_ascii=False))
        rc.close()
        logger.info("일일 요약 Redis 발행 완료 (ch:tg-outbox)")
    except Exception as e:
        logger.warning(f"Redis publish 실패: {e}")


async def run():
    dsn = os.environ.get("POSTGRES_DSN", "").replace("+asyncpg", "")
    if not dsn:
        logger.error("POSTGRES_DSN 미설정")
        return

    ssl_val = "require" if "supabase" in dsn else False
    db = await asyncpg.create_pool(
        dsn=dsn, min_size=1, max_size=3,
        ssl=ssl_val, statement_cache_size=0,
    )

    today = date.today()
    rows = await db.fetch(
        """
        SELECT r.code,
               r.rationale->>'event_type' AS event_type,
               r.success_prob,
               r.target_price,
               r.stop_loss_price
        FROM recommendations r
        WHERE DATE(r.created_at AT TIME ZONE 'Asia/Seoul') = $1
          AND r.action = 'BUY'
          AND (r.expired_at IS NULL OR r.expired_at > NOW())
        ORDER BY r.success_prob DESC NULLS LAST
        LIMIT 20
        """,
        today,
    )
    await db.close()

    if not rows:
        logger.info("오늘 BUY 추천 없음 — 알림 스킵")
        return

    top_n = min(10, len(rows))
    lines = [
        f"📊 <b>오늘의 추천 종목 ({today})</b>",
        f"총 <b>{len(rows)}</b>건 생성\n",
    ]
    for r in rows[:top_n]:
        prob   = f"{r['success_prob']*100:.1f}%" if r["success_prob"] is not None else "-"
        target = f"{int(r['target_price']):,}원"    if r["target_price"]    else "-"
        stop   = f"{int(r['stop_loss_price']):,}원" if r["stop_loss_price"] else "-"
        etype  = r["event_type"] or "UNKNOWN"
        lines.append(
            f"• <b>{r['code']}</b> [{etype}] "
            f"확률={prob} 목표={target} 손절={stop}"
        )

    if len(rows) > top_n:
        lines.append(f"\n… 외 {len(rows) - top_n}건")

    _publish_tg_outbox("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(run())

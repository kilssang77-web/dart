"""
당일 추천 결과 텔레그램 알림 — GitHub Actions에서 실행.
stdlib(urllib) + asyncpg만 사용하므로 추가 패키지 불필요.
"""
import asyncio
import json
import logging
import os
import ssl
import urllib.request
from datetime import date

import asyncpg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("notify-telegram")

_TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
_TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def _send_telegram(text: str) -> None:
    if not _TELEGRAM_TOKEN or not _TELEGRAM_CHAT_ID:
        logger.info("TELEGRAM_TOKEN/CHAT_ID 미설정 — 알림 스킵")
        return
    url = f"https://api.telegram.org/bot{_TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": _TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }).encode()
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            resp.read()
        logger.info("텔레그램 알림 전송 완료")
    except Exception as e:
        logger.warning(f"텔레그램 전송 실패: {e}")


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

    _send_telegram("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(run())

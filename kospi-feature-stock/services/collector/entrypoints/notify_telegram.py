"""
당일 추천 결과 텔레그램 일일 요약 발송 — GitHub Actions 실행.

- 오늘 BUY 추천 상위 10종목을 Supabase에서 조회 (종목명 포함)
- urllib.request 직접 발송 — notifier 서비스 의존 없음
"""
import asyncio
import json
import logging
import os
import urllib.request
from datetime import date

import asyncpg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("notify-telegram")

TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHAT  = os.environ.get("TELEGRAM_CHAT_ID", "")


def _send_telegram(text: str) -> bool:
    if not TG_TOKEN or not TG_CHAT:
        logger.warning("TELEGRAM_TOKEN / TELEGRAM_CHAT_ID 미설정 — 알림 스킵")
        return False
    url  = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    body = json.dumps({
        "chat_id": TG_CHAT, "text": text, "parse_mode": "HTML",
    }).encode()
    try:
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        logger.warning(f"Telegram 전송 실패: {e}")
        return False


async def run():
    dsn = os.environ.get("POSTGRES_DSN", "").replace("+asyncpg", "")
    if not dsn:
        logger.error("POSTGRES_DSN 미설정")
        return
    if not TG_TOKEN or not TG_CHAT:
        logger.error("TELEGRAM_TOKEN / TELEGRAM_CHAT_ID 미설정")
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
               COALESCE(s.name, r.code)      AS name,
               r.rationale->>'event_type'    AS event_type,
               r.success_prob,
               r.target_price,
               r.stop_loss_price,
               r.confidence_grade
        FROM recommendations r
        LEFT JOIN stocks s ON s.code = r.code
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
        grade  = r["confidence_grade"] or "-"
        name   = r["name"]
        code   = r["code"]
        stock  = f"{name}({code})" if name != code else code
        lines.append(
            f"• <b>{stock}</b> [{etype}] "
            f"확률={prob} 목표={target} 손절={stop} [{grade}]"
        )

    if len(rows) > top_n:
        lines.append(f"\n… 외 {len(rows) - top_n}건")

    ok = _send_telegram("\n".join(lines))
    if ok:
        logger.info(f"일일 요약 Telegram 발송 완료 ({len(rows)}건)")
    else:
        logger.error("일일 요약 Telegram 발송 실패")


if __name__ == "__main__":
    asyncio.run(run())

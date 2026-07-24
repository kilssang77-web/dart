"""
장중 인트라데이 신호 알림 + 미니 추천 생성.

supply_worker 완료 후 실행. 최근 60분 feature_events 중 미처리된 이벤트를
간단한 규칙 기반으로 추천 DB에 저장하고 Telegram 알림을 발송한다.

의존성: asyncpg, orjson (collector requirements에 포함) + stdlib
"""
import asyncio
import logging
import os
import ssl
import sys
import urllib.request
import orjson
import asyncpg
from datetime import datetime, timedelta, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [intraday-notify] %(levelname)s %(message)s",
)
logger = logging.getLogger("intraday-notify")

_TG_TOKEN  = os.environ.get("TELEGRAM_TOKEN", "")
_TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# 추천 생성 기준
MIN_SCORE    = float(os.environ.get("INTRADAY_MIN_SCORE",  "0.55"))
LOOKBACK_MIN = int(os.environ.get("INTRADAY_LOOKBACK_MIN", "60"))
MAX_RECS     = int(os.environ.get("INTRADAY_MAX_RECS",     "5"))


def _send_telegram(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = orjson.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
    ctx = ssl.create_default_context()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            resp.read()
    except Exception as e:
        logger.warning(f"Telegram 전송 실패: {e}")


async def run(db: asyncpg.Pool) -> None:
    since = datetime.now(timezone.utc) - timedelta(minutes=LOOKBACK_MIN)

    # 최근 LOOKBACK_MIN분 내 탐지된 이벤트 중 추천이 없는 것
    events = await db.fetch(
        """
        SELECT fe.id, fe.code, fe.event_type, fe.price, fe.signal_score,
               fe.change_rate, fe.detected_at
        FROM   feature_events fe
        LEFT JOIN recommendations r ON r.feature_event_id = fe.id
        WHERE  fe.detected_at >= $1
          AND  fe.signal_score >= $2
          AND  r.id IS NULL
        ORDER BY fe.signal_score DESC
        LIMIT  50
        """,
        since, MIN_SCORE,
    )

    if not events:
        logger.info("신규 인트라데이 신호 없음")
        return

    logger.info(f"미처리 신호 {len(events)}건 → 추천 생성")

    inserted = []
    for ev in events:
        price = ev["price"] or 0
        score = float(ev["signal_score"] or 0)
        action = "BUY" if score >= 0.60 else "WAIT"

        # 간단 가격 목표 산출 (ML 없이)
        target      = int(price * 1.05) if price else None
        stop        = int(price * 0.97) if price else None
        entry_low   = int(price * 0.99) if price else None
        entry_high  = int(price * 1.01) if price else None
        expired_at  = datetime.now(timezone.utc) + timedelta(days=1)

        rationale = orjson.dumps({
            "source":       "INTRADAY",
            "event_type":   ev["event_type"],
            "signal_score": score,
        }).decode()

        try:
            row = await db.fetchrow(
                """
                INSERT INTO recommendations
                    (feature_event_id, code, action,
                     entry_price, entry_price_low, entry_price_high,
                     target_price, stop_loss_price,
                     expected_hold_days, success_prob,
                     expected_return, risk_score, risk_reward_ratio,
                     rationale, expired_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14::jsonb,$15)
                RETURNING id
                """,
                ev["id"], ev["code"], action,
                price, entry_low, entry_high,
                target, stop,
                3, round(score, 3),
                5.0, round(1.0 - score, 3), 1.67,
                rationale, expired_at,
            )
            if row:
                inserted.append({
                    "code":       ev["code"],
                    "event_type": ev["event_type"],
                    "price":      price,
                    "score":      score,
                    "action":     action,
                })
                logger.info(f"  추천 저장: {ev['code']} {ev['event_type']} score={score:.3f} → {action}")
        except Exception as e:
            logger.warning(f"  추천 저장 실패 [{ev['code']}]: {e}")

    if not inserted:
        return

    # Telegram 알림 (상위 MAX_RECS개)
    if not _TG_TOKEN or not _TG_CHAT_ID:
        logger.info("TELEGRAM_TOKEN 미설정 — 알림 스킵")
        return

    top = sorted(inserted, key=lambda x: x["score"], reverse=True)[:MAX_RECS]
    now_kst = datetime.now(timezone.utc) + timedelta(hours=9)
    lines = [f"📊 <b>[장중 신호] {now_kst.strftime('%H:%M')} KST</b>", ""]
    for i, r in enumerate(top, 1):
        mark = "🟢" if r["action"] == "BUY" else "🟡"
        lines.append(
            f"{mark} {i}. <b>{r['code']}</b> | {r['event_type']}"
            f"\n   현재가 {r['price']:,}원 | 강도 {r['score']:.2f}"
        )
    lines.append(f"\n총 {len(inserted)}건 신호 탐지")
    text = "\n".join(lines)
    _send_telegram(_TG_TOKEN, _TG_CHAT_ID, text)
    logger.info(f"Telegram 알림 발송 완료 ({len(top)}건)")


async def main() -> None:
    dsn = os.environ.get("POSTGRES_DSN", "")
    if not dsn:
        logger.error("POSTGRES_DSN 환경변수 없음")
        sys.exit(1)
    dsn = dsn.replace("+asyncpg", "")
    ssl_val = "require" if "supabase" in dsn else False
    db = await asyncpg.create_pool(
        dsn=dsn, min_size=1, max_size=3,
        ssl=ssl_val, statement_cache_size=0,
    )
    try:
        await run(db)
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())

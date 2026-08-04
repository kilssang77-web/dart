"""
ch:feature Redis Pub/Sub → Telegram 알림 데몬.
realtime_ws_detector.py와 함께 실행 (systemd ws-notifier.service).

탐지 이벤트별 Telegram 포맷:
  AMOUNT_SURGE  — 💰 거래대금 급등
  VOLUME_SURGE  — 📊 거래량 급등
  VI_TRIGGERED  — ⚡ VI(변동성완화장치) 발동
"""
import asyncio
import json
import logging
import os
import sys
import urllib.request
from dotenv import load_dotenv
import redis.asyncio as redis_lib
import orjson

load_dotenv(os.path.expanduser("~/.env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ws-notifier] %(levelname)s %(message)s",
)
logger = logging.getLogger("ws-notifier")

TG_TOKEN  = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHAT   = os.environ.get("TELEGRAM_CHAT_ID", "")
REDIS_URL = os.environ.get("REDIS_URL", "")

_EMOJI = {
    "AMOUNT_SURGE": "💰",
    "VOLUME_SURGE": "📊",
    "VI_TRIGGERED": "⚡",
}


def _send_telegram(text: str) -> bool:
    if not TG_TOKEN or not TG_CHAT:
        logger.warning("TELEGRAM_TOKEN / TELEGRAM_CHAT_ID 미설정")
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


def _format(ev: dict) -> str:
    code     = ev.get("code", "")
    etype    = ev.get("event_type", "")
    price    = ev.get("price", 0)
    score    = ev.get("signal_score", 0.0)
    sig      = ev.get("signal_data", {})
    emoji    = _EMOJI.get(etype, "🔔")
    ts       = str(ev.get("detected_at", ""))[:16]

    if etype == "AMOUNT_SURGE":
        ratio = sig.get("ratio", 0)
        avg   = int(sig.get("avg_amount_20d", 0))
        avg_b = f"{avg // 100_000_000:.0f}억" if avg >= 100_000_000 else f"{avg:,}"
        return (
            f"{emoji} <b>거래대금 급등 [{code}]</b>\n"
            f"현재가: {price:,}원\n"
            f"거래대금: 20일 평균 대비 <b>{ratio:.1f}배</b> (평균 {avg_b})\n"
            f"신호점수: {score:.2f}  |  탐지: {ts}"
        )
    if etype == "VOLUME_SURGE":
        ratio = sig.get("ratio", 0)
        return (
            f"{emoji} <b>거래량 급등 [{code}]</b>\n"
            f"현재가: {price:,}원\n"
            f"거래량: 20일 평균 대비 <b>{ratio:.1f}배</b>\n"
            f"신호점수: {score:.2f}  |  탐지: {ts}"
        )
    if etype == "VI_TRIGGERED":
        vi_kind = sig.get("vi_kind", "")
        return (
            f"{emoji} <b>VI 발동 [{code}]</b>\n"
            f"현재가: {price:,}원  |  유형: {vi_kind}\n"
            f"탐지: {ts}"
        )
    return (
        f"🔔 <b>{etype} [{code}]</b>\n"
        f"현재가: {price:,}원  |  탐지: {ts}"
    )


async def main():
    if not REDIS_URL:
        logger.error("REDIS_URL 미설정 — 종료")
        sys.exit(1)
    if not TG_TOKEN or not TG_CHAT:
        logger.error("TELEGRAM_TOKEN / TELEGRAM_CHAT_ID 미설정 — 종료")
        sys.exit(1)

    redis  = redis_lib.from_url(REDIS_URL, decode_responses=False)
    pubsub = redis.pubsub()
    await pubsub.subscribe("ch:feature")
    logger.info("ws-notifier 시작 — ch:feature 구독 중 (Telegram 알림 활성)")

    try:
        async for msg in pubsub.listen():
            if msg["type"] != "message":
                continue
            try:
                ev   = orjson.loads(msg["data"])
                text = _format(ev)
                ok   = _send_telegram(text)
                logger.info(
                    f"[{ev.get('event_type')}] {ev.get('code')} "
                    f"score={ev.get('signal_score', 0):.2f} "
                    f"→ Telegram {'전송' if ok else '실패'}"
                )
            except Exception as e:
                logger.warning(f"메시지 처리 오류: {e}")
    finally:
        await pubsub.unsubscribe()
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())

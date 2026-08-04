"""
ch:feature Redis Pub/Sub → Telegram 알림 데몬.
realtime_ws_detector.py와 함께 실행 (systemd ws-notifier.service).

UI 설정(telegram:config Redis 키) 연동:
  enabled       — 전체 알림 ON/OFF
  min_prob      — 최소 신호점수 (signal_score 기준, 기본 0.55)
  min_surge_ratio — 최소 급등 배율 (AMOUNT/VOLUME_SURGE, 기본 5.0)

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

# UI 설정이 없을 때 적용되는 기본값
_DEFAULT_MIN_PROB        = float(os.environ.get("WS_MIN_SCORE",     "0.55"))
_DEFAULT_MIN_SURGE_RATIO = float(os.environ.get("WS_MIN_SURGE",      "5.0"))
_CONFIG_KEY              = "telegram:config"

_EMOJI = {
    "AMOUNT_SURGE": "💰",
    "VOLUME_SURGE": "📊",
    "VI_TRIGGERED": "⚡",
}


async def _load_config(redis: redis_lib.Redis) -> dict:
    """UI 설정(telegram:config)을 Redis에서 읽어 반환. 없으면 기본값."""
    try:
        raw = await redis.get(_CONFIG_KEY)
        if raw:
            return orjson.loads(raw)
    except Exception:
        pass
    return {
        "enabled":          True,
        "min_prob":         _DEFAULT_MIN_PROB,
        "min_surge_ratio":  _DEFAULT_MIN_SURGE_RATIO,
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
    code   = ev.get("code", "")
    name   = ev.get("name") or code
    etype  = ev.get("event_type", "")
    price  = ev.get("price", 0)
    score  = ev.get("signal_score", 0.0)
    sig    = ev.get("signal_data", {})
    emoji  = _EMOJI.get(etype, "🔔")
    ts     = str(ev.get("detected_at", ""))[:16]
    stock  = f"{name}({code})" if name != code else code

    if etype == "AMOUNT_SURGE":
        ratio = sig.get("ratio", 0)
        avg   = int(sig.get("avg_amount_20d", 0))
        avg_b = f"{avg // 100_000_000:.0f}억" if avg >= 100_000_000 else f"{avg:,}"
        return (
            f"{emoji} <b>거래대금 급등 {stock}</b>\n"
            f"현재가: {price:,}원\n"
            f"거래대금: 20일 평균 대비 <b>{ratio:.1f}배</b> (평균 {avg_b})\n"
            f"신호점수: {score:.2f}  |  탐지: {ts}"
        )
    if etype == "VOLUME_SURGE":
        ratio = sig.get("ratio", 0)
        return (
            f"{emoji} <b>거래량 급등 {stock}</b>\n"
            f"현재가: {price:,}원\n"
            f"거래량: 20일 평균 대비 <b>{ratio:.1f}배</b>\n"
            f"신호점수: {score:.2f}  |  탐지: {ts}"
        )
    if etype == "VI_TRIGGERED":
        vi_kind = sig.get("vi_kind", "")
        return (
            f"{emoji} <b>VI 발동 {stock}</b>\n"
            f"현재가: {price:,}원  |  유형: {vi_kind}\n"
            f"탐지: {ts}"
        )
    return f"🔔 <b>{etype} {stock}</b>\n현재가: {price:,}원  |  탐지: {ts}"


async def _handle(ev: dict, redis: redis_lib.Redis) -> None:
    cfg     = await _load_config(redis)
    etype   = ev.get("event_type", "")
    code    = ev.get("code", "")
    score   = float(ev.get("signal_score", 0.0))
    sig     = ev.get("signal_data", {})

    # 전체 알림 ON/OFF
    if not cfg.get("enabled", True):
        logger.debug(f"[{etype}] {code} — 알림 비활성화(UI 설정), 스킵")
        return

    # 신호점수 필터 (VI_TRIGGERED는 점수 필터 제외 — 발동 자체가 이벤트)
    if etype != "VI_TRIGGERED":
        min_prob = float(cfg.get("min_prob", _DEFAULT_MIN_PROB))
        if score < min_prob:
            logger.debug(
                f"[{etype}] {code} score={score:.2f} < min_prob={min_prob:.2f} — 스킵"
            )
            return

        # 급등 배율 필터
        ratio     = float(sig.get("ratio", 0))
        min_surge = float(cfg.get("min_surge_ratio", _DEFAULT_MIN_SURGE_RATIO))
        if ratio < min_surge:
            logger.debug(
                f"[{etype}] {code} ratio={ratio:.1f} < min_surge={min_surge:.1f} — 스킵"
            )
            return

    text = _format(ev)
    ok   = _send_telegram(text)
    logger.info(
        f"[{etype}] {code} score={score:.2f} "
        f"→ Telegram {'전송' if ok else '실패'}"
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

    cfg = await _load_config(redis)
    logger.info(
        f"ws-notifier 시작 — ch:feature 구독 중 "
        f"(enabled={cfg.get('enabled')}, "
        f"min_prob={cfg.get('min_prob', _DEFAULT_MIN_PROB)}, "
        f"min_surge={cfg.get('min_surge_ratio', _DEFAULT_MIN_SURGE_RATIO)})"
    )

    try:
        async for msg in pubsub.listen():
            if msg["type"] != "message":
                continue
            try:
                ev = orjson.loads(msg["data"])
                await _handle(ev, redis)
            except Exception as e:
                logger.warning(f"메시지 처리 오류: {e}")
    finally:
        await pubsub.unsubscribe()
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())

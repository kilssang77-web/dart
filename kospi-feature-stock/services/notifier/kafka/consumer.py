import asyncio
import logging
import os
import orjson
import redis.asyncio as redis_lib
from telegram.sender import TelegramSender
from telegram.formatter import format_buy_signal, format_disclosure

logger = logging.getLogger("notifier.consumer")

_REDIS_KEY             = "telegram:config"
_DEDUP_TTL_SIGNAL      = int(os.environ.get("DEDUP_TTL_SIGNAL",     "3600"))  # 1시간
_DEDUP_TTL_DISCLOSURE  = int(os.environ.get("DEDUP_TTL_DISCLOSURE", "3600"))  # 1시간
_DEFAULT_MIN_PROB            = float(os.environ.get("REC_MIN_PROB", "0.22"))
_DEFAULT_DISCLOSURE_KEYWORDS = ["무상증자"]


async def _load_config(redis: redis_lib.Redis) -> dict:
    try:
        raw = await redis.get(_REDIS_KEY)
        if raw:
            return orjson.loads(raw)
    except Exception:
        pass
    return {
        "enabled":             True,
        "min_prob":            _DEFAULT_MIN_PROB,
        "disclosure_keywords": list(_DEFAULT_DISCLOSURE_KEYWORDS),
    }


async def _is_dup(redis: redis_lib.Redis, key: str) -> bool:
    return bool(await redis.exists(key))


async def _mark_sent(redis: redis_lib.Redis, key: str, ttl: int) -> None:
    await redis.set(key, "1", ex=ttl)


class NotifierConsumer:

    def __init__(self, sender: TelegramSender):
        self._sender = sender
        self._redis: redis_lib.Redis | None = None

    async def run(self):
        self._redis = redis_lib.from_url(os.environ["REDIS_URL"])
        pubsub = self._redis.pubsub()
        await pubsub.subscribe("ch:signal-generated", "ch:disclosure-analyzed")
        logger.info("Notifier consumer started — listening on ch:signal-generated, ch:disclosure-analyzed")
        try:
            async for msg in pubsub.listen():
                if msg["type"] != "message":
                    continue
                channel = msg["channel"]
                if isinstance(channel, bytes):
                    channel = channel.decode()
                topic = channel[3:]  # strip "ch:" prefix
                try:
                    data = orjson.loads(msg["data"])
                    if topic == "signal-generated":
                        await self._on_signal(data)
                    elif topic == "disclosure-analyzed":
                        await self._on_disclosure(data)
                except Exception as e:
                    logger.error(f"Handler error [{topic}]: {e}")
        finally:
            try:
                await pubsub.unsubscribe()
                await pubsub.aclose()
            except Exception:
                pass
            if self._redis:
                await self._redis.aclose()

    async def _on_signal(self, data: dict):
        cfg  = await _load_config(self._redis)
        if not cfg.get("enabled", True):
            return
        prob     = data.get("success_prob", 0)
        min_prob = cfg.get("min_prob", _DEFAULT_MIN_PROB)
        if prob < min_prob:
            logger.debug(f"[SIGNAL] skip code={data.get('code')} prob={prob:.3f} < min={min_prob:.3f}")
            return

        code      = data.get("code", "")
        name      = data.get("name", "") or code
        dedup_key = f"telegram:dedup:signal:{code}"

        if await _is_dup(self._redis, dedup_key):
            logger.debug(f"[SIGNAL] dedup skip code={code} ({_DEDUP_TTL_SIGNAL}s 이내 발송됨)")
            return

        logger.info(f"[SIGNAL] code={code} name={name} prob={prob:.3f} — sending Telegram")
        text = format_buy_signal(data)
        ok   = await self._sender.send_message(
            text,
            msg_type="signal",
            code=code,
            name=name,
            title=f"{name} 매수 신호 ({prob*100:.0f}%)",
        )
        if ok:
            await _mark_sent(self._redis, dedup_key, _DEDUP_TTL_SIGNAL)
        else:
            logger.warning(f"[SIGNAL] send failed — dedup key NOT set, retry allowed: code={code}")

    async def _on_disclosure(self, data: dict):
        import hashlib
        cfg      = await _load_config(self._redis)
        if not cfg.get("enabled", True):
            return
        title    = data.get("title", "")
        keywords = cfg.get("disclosure_keywords", _DEFAULT_DISCLOSURE_KEYWORDS)
        if not any(kw in title for kw in keywords):
            return

        code       = data.get("code", "")
        name       = data.get("corp_name", "")
        title_hash = hashlib.md5(title.encode()).hexdigest()[:12]
        dedup_key  = f"telegram:dedup:disclosure:{title_hash}"

        if await _is_dup(self._redis, dedup_key):
            logger.debug(f"[DISCLOSURE] dedup skip title={title[:30]!r}")
            return

        logger.info(f"[DISCLOSURE] {name} — {title[:40]} — sending Telegram")
        text = format_disclosure(data)
        ok   = await self._sender.send_message(
            text,
            msg_type="disclosure",
            code=code,
            name=name,
            title=title,
        )
        if ok:
            await _mark_sent(self._redis, dedup_key, _DEDUP_TTL_DISCLOSURE)
        else:
            logger.warning(f"[DISCLOSURE] send failed — dedup key NOT set, retry allowed: title={title[:40]!r}")

import logging
import os
from typing import Optional
import redis.asyncio as redis_lib

logger = logging.getLogger(__name__)

_SURGE_THRESHOLD = float(os.environ.get("POST_DISC_SURGE_PCT", "3.0"))   # 3% 이상 상승 (오탐 방지)
_DISC_TTL        = int(os.environ.get("POST_DISC_TTL_SEC", "14400"))      # 기본 4시간
_FIRE_COOLDOWN   = int(os.environ.get("POST_DISC_COOLDOWN_SEC", "1800"))  # 같은 종목 30분 내 재발화 방지
_MIN_PRICE       = int(os.environ.get("POST_DISC_MIN_PRICE", "1000"))     # 저가주 오탐 방지


class PostDisclosureDetector:
    """공시 발생 후 급등 탐지"""

    def __init__(self, redis_client: redis_lib.Redis):
        self.redis = redis_client

    async def mark_disclosure(self, code: str, category: str) -> None:
        """호재 또는 플래그 공시 발생 시 Redis에 마킹 (TTL=4시간)."""
        if category in ("favorable",):
            await self.redis.set(
                f"disclosure:recent:{code}",
                category,
                ex=_DISC_TTL,
            )
            logger.debug(f"[PostDisclosure] marked {code} category={category} ttl={_DISC_TTL}s")

    async def detect(self, tick: dict) -> Optional[dict]:
        code        = tick.get("code", "")
        change_rate = float(tick.get("change_rate", 0.0))
        price       = int(tick.get("price", 0))

        if price < _MIN_PRICE or change_rate < _SURGE_THRESHOLD:
            return None

        disc_flag = await self.redis.get(f"disclosure:recent:{code}")
        if not disc_flag:
            return None

        # 30분 내 이미 발화한 경우 스킵 (쿨다운)
        cooldown_key = f"disclosure:fired:{code}"
        if await self.redis.exists(cooldown_key):
            return None

        await self.redis.set(cooldown_key, "1", ex=_FIRE_COOLDOWN)

        category = disc_flag.decode() if isinstance(disc_flag, bytes) else disc_flag
        score = min(1.0, 0.65 + change_rate / 20.0)

        return {
            "code":         code,
            "event_type":   "POST_DISCLOSURE_SURGE",
            "price":        int(tick.get("price", 0)),
            "change_rate":  change_rate,
            "signal_score": round(score, 3),
            "signal_data":  {
                "disclosure_category": category,
                "surge_pct":           round(change_rate, 2),
                "threshold_pct":       _SURGE_THRESHOLD,
            },
        }

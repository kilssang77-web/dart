import logging
from typing import Optional
import redis.asyncio as redis_lib

logger = logging.getLogger(__name__)


class PostDisclosureDetector:
    """공시 발생 후 급등 탐지"""

    POST_SURGE_THRESHOLD = 3.0  # 공시 후 3% 이상 상승

    def __init__(self, redis_client: redis_lib.Redis):
        self.redis = redis_client

    async def mark_disclosure(self, code: str, category: str) -> None:
        if category == "favorable":
            await self.redis.set(
                f"disclosure:recent:{code}",
                category,
                ex=3600,  # 1시간 유효
            )

    async def detect(self, tick: dict) -> Optional[dict]:
        code        = tick.get("code", "")
        change_rate = float(tick.get("change_rate", 0.0))

        if change_rate < self.POST_SURGE_THRESHOLD:
            return None

        disc_flag = await self.redis.get(f"disclosure:recent:{code}")
        if not disc_flag:
            return None

        return {
            "code":        code,
            "event_type":  "POST_DISCLOSURE_SURGE",
            "price":       int(tick.get("price", 0)),
            "change_rate": change_rate,
            "signal_score": min(1.0, 0.7 + change_rate / 30.0),
            "signal_data": {"disclosure_category": disc_flag.decode()},
        }

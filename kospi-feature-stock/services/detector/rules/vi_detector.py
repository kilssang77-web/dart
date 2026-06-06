import logging
import os
from typing import Optional
import redis.asyncio as redis_lib

logger = logging.getLogger(__name__)

_VI_RATE     = float(os.environ.get("VI_RATE_PCT", "10.0"))
_VI_DEDUP_EX = int(os.environ.get("VI_DEDUP_SEC", "300"))


class VIDetector:
    """변동성 완화장치(VI) 탐지"""

    def __init__(self, redis_client: redis_lib.Redis):
        self.redis   = redis_client
        self.vi_rate = _VI_RATE

    async def detect(self, tick: dict) -> Optional[dict]:
        code        = tick.get("code", "")
        change_rate = abs(float(tick.get("change_rate", 0.0)))

        if change_rate < self.vi_rate:
            return None

        vi_key = f"vi:{code}:triggered"
        is_new = await self.redis.set(vi_key, "1", ex=_VI_DEDUP_EX, nx=True)
        if not is_new:
            return None

        # 변동폭이 클수록 높은 점수 (10%=0.65, 15%=0.75, 20%=0.85)
        score = min(0.95, 0.55 + (change_rate - self.vi_rate) / (self.vi_rate * 2))

        return {
            "code":        code,
            "event_type":  "VI_TRIGGERED",
            "price":       int(tick.get("price", 0)),
            "change_rate": float(tick.get("change_rate", 0.0)),
            "signal_score": round(score, 3),
            "signal_data":  {
                "vi_type":    "dynamic",
                "change_rate": change_rate,
                "threshold":  self.vi_rate,
            },
        }

import logging
import os
from dataclasses import dataclass, field
from typing import Optional
import redis.asyncio as redis_lib

logger = logging.getLogger(__name__)

_RATIO_THRESHOLD = float(os.environ.get("VOL_SURGE_RATIO", "5.0"))
_MIN_AMOUNT      = int(os.environ.get("VOL_SURGE_MIN_AMOUNT", "200000000"))
_SCORE_K         = float(os.environ.get("VOL_SURGE_SCORE_K", "4.0"))


@dataclass
class VolumeSurgeSignal:
    code: str
    event_type: str = "VOLUME_SURGE"
    price: int = 0
    change_rate: float = 0.0
    volume: int = 0
    volume_ratio: float = 0.0
    amount: int = 0
    signal_score: float = 0.0
    signal_data: dict = field(default_factory=dict)


class VolumeSurgeDetector:

    def __init__(self, redis_client: redis_lib.Redis):
        self.redis           = redis_client
        self.ratio_threshold = _RATIO_THRESHOLD
        self.min_amount      = _MIN_AMOUNT

    async def detect(self, bar: dict) -> Optional[VolumeSurgeSignal]:
        code   = bar.get("code", "")
        volume = int(bar.get("volume", 0))
        amount = int(bar.get("amount", 0))

        if volume == 0 or amount < self.min_amount:
            return None

        avg_vol = await self._avg_volume(code)
        if avg_vol <= 0:
            return None

        ratio = volume / avg_vol
        if ratio < self.ratio_threshold:
            return None

        # 비율이 threshold의 몇 배인지로 점수 산출
        excess = ratio - self.ratio_threshold
        score  = min(0.95, 0.50 + excess / (self.ratio_threshold * _SCORE_K))

        return VolumeSurgeSignal(
            code=code,
            price=int(bar.get("close", 0)),
            change_rate=float(bar.get("change_rate", 0.0)),
            volume=volume,
            volume_ratio=round(ratio, 2),
            amount=amount,
            signal_score=round(score, 3),
            signal_data={
                "avg_volume_20d": round(avg_vol),
                "ratio":          round(ratio, 2),
                "threshold":      self.ratio_threshold,
            },
        )

    async def _avg_volume(self, code: str) -> float:
        val = await self.redis.get(f"stats:{code}:avg_vol_20d")
        return float(val) if val else 0.0

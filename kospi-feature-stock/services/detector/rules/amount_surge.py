import logging
import os
from dataclasses import dataclass, field
from typing import Optional
import redis.asyncio as redis_lib

logger = logging.getLogger(__name__)

_RATIO_THRESHOLD = float(os.environ.get("AMOUNT_SURGE_RATIO", "5.0"))
_MIN_AMOUNT      = int(os.environ.get("AMOUNT_SURGE_MIN_AMOUNT", "5000000000"))  # 50억
_SCORE_K         = float(os.environ.get("AMOUNT_SURGE_SCORE_K", "4.0"))


@dataclass
class AmountSurgeSignal:
    code: str
    event_type: str = "AMOUNT_SURGE"
    price: int = 0
    change_rate: float = 0.0
    volume: int = 0
    amount: int = 0
    amount_ratio: float = 0.0
    signal_score: float = 0.0
    signal_data: dict = field(default_factory=dict)


class AmountSurgeDetector:

    def __init__(self, redis_client: redis_lib.Redis):
        self.redis           = redis_client
        self.ratio_threshold = _RATIO_THRESHOLD
        self.min_amount      = _MIN_AMOUNT

    async def detect(self, bar: dict) -> Optional[AmountSurgeSignal]:
        code   = bar.get("code", "")
        amount = int(bar.get("amount", 0))

        if amount < self.min_amount:
            return None

        avg_amount = await self._avg_amount(code)
        if avg_amount <= 0:
            return None

        ratio = amount / avg_amount
        if ratio < self.ratio_threshold:
            return None

        excess = ratio - self.ratio_threshold
        score  = min(0.95, 0.50 + excess / (self.ratio_threshold * _SCORE_K))

        return AmountSurgeSignal(
            code=code,
            price=int(bar.get("close", 0)),
            change_rate=float(bar.get("change_rate", 0.0)),
            volume=int(bar.get("volume", 0)),
            amount=amount,
            amount_ratio=round(ratio, 2),
            signal_score=round(score, 3),
            signal_data={
                "avg_amount_20d": round(avg_amount),
                "ratio":          round(ratio, 2),
                "threshold":      self.ratio_threshold,
            },
        )

    async def _avg_amount(self, code: str) -> float:
        val = await self.redis.get(f"stats:{code}:avg_amount_20d")
        return float(val) if val else 0.0

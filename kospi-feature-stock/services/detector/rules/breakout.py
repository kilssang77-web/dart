import logging
import os
from dataclasses import dataclass
import redis.asyncio as redis_lib

logger = logging.getLogger(__name__)

# (기간_일, Redis_키_suffix, 이벤트_타입, 기본점수)
BREAKOUT_PERIODS = [
    (260, "52w", "BREAKOUT_52W", 0.80),
    (130, "26w", "BREAKOUT_26W", 0.70),
    (65,  "13w", "BREAKOUT_13W", 0.60),
    (20,  "20d", "BREAKOUT_20D", 0.50),
]

_MIN_BREAKOUT_PCT = float(os.environ.get("BREAKOUT_MIN_PCT", "0.1"))


@dataclass
class BreakoutSignal:
    code: str
    event_type: str
    price: int
    prev_high: int
    period_label: str
    period_days: int
    change_rate: float
    signal_score: float


class BreakoutDetector:

    def __init__(self, redis_client: redis_lib.Redis):
        self.redis = redis_client

    async def detect(self, tick: dict) -> list[BreakoutSignal]:
        code  = tick.get("code", "")
        price = int(tick.get("price", 0))
        if not price:
            return []

        for days, label, event_type, base_score in BREAKOUT_PERIODS:
            high_str = await self.redis.get(f"stats:{code}:high_{days}d")
            if not high_str:
                continue
            prev_high = int(high_str)
            if prev_high <= 0:
                continue

            excess_pct = (price - prev_high) / prev_high * 100
            if excess_pct < _MIN_BREAKOUT_PCT:
                continue

            # 초과 비율이 클수록 높은 점수
            score = min(0.95, base_score + excess_pct / 20.0)

            return [BreakoutSignal(
                code=code,
                event_type=event_type,
                price=price,
                prev_high=prev_high,
                period_label=label,
                period_days=days,
                change_rate=float(tick.get("change_rate", 0.0)),
                signal_score=round(score, 3),
            )]

        return []

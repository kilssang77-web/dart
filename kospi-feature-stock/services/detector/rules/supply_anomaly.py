import logging
import os
from typing import Optional
import redis.asyncio as redis_lib

logger = logging.getLogger(__name__)

_SURGE_RATIO  = float(os.environ.get("SUPPLY_SURGE_RATIO", "5.0"))
_DUAL_BUY_MIN = float(os.environ.get("SUPPLY_DUAL_BUY_MIN_RATIO", "2.0"))


class SupplyAnomalyDetector:

    def __init__(self, redis_client: redis_lib.Redis):
        self.redis       = redis_client
        self.surge_ratio = _SURGE_RATIO

    async def detect(self, data: dict) -> Optional[dict]:
        code        = data.get("code", "")
        foreign_net = int(data.get("foreign_net", 0))
        inst_net    = int(data.get("inst_net", 0))

        avg_foreign = await self._avg(code, "foreign")
        avg_inst    = await self._avg(code, "inst")

        signals = []

        if avg_foreign != 0:
            f_ratio = foreign_net / (abs(avg_foreign) + 1)
            if f_ratio >= self.surge_ratio:
                signals.append({
                    "type":  "FOREIGN_BUY_SURGE",
                    "net":   foreign_net,
                    "ratio": round(f_ratio, 1),
                })

        if avg_inst != 0:
            i_ratio = inst_net / (abs(avg_inst) + 1)
            if i_ratio >= self.surge_ratio:
                signals.append({
                    "type":  "INST_BUY_SURGE",
                    "net":   inst_net,
                    "ratio": round(i_ratio, 1),
                })

        # 외인+기관 동시 매수 (각각이 기준치 절반 이상이면 탐지)
        if (avg_foreign != 0 and avg_inst != 0
                and foreign_net / (abs(avg_foreign) + 1) >= _DUAL_BUY_MIN
                and inst_net    / (abs(avg_inst)    + 1) >= _DUAL_BUY_MIN):
            signals.append({"type": "DUAL_BUY", "foreign": foreign_net, "inst": inst_net})

        if not signals:
            return None

        # 시그널 수와 각 비율의 강도로 점수 계산
        max_ratio = max(
            (s.get("ratio", _DUAL_BUY_MIN) for s in signals),
            default=_DUAL_BUY_MIN,
        )
        score = min(0.95, 0.35 + (max_ratio / (self.surge_ratio * 4)) + len(signals) * 0.10)

        last_price = await self.redis.get(f"stats:{code}:last_price")
        last_rate  = await self.redis.get(f"stats:{code}:last_change_rate")

        return {
            "code":         code,
            "event_type":   "SUPPLY_ANOMALY",
            "price":        int(last_price) if last_price else 0,
            "change_rate":  float(last_rate) if last_rate else 0.0,
            "signal_score": round(score, 3),
            "signal_data":  {"supply_signals": signals},
        }

    async def _avg(self, code: str, investor: str) -> float:
        val = await self.redis.get(f"stats:{code}:avg_{investor}_20d")
        return float(val) if val else 0.0

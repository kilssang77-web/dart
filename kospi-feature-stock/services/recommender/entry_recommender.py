import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_MIN_RR        = float(os.environ.get("REC_MIN_RISK_REWARD", "2.0"))
_MAX_RISK      = float(os.environ.get("REC_MAX_RISK", "0.60"))
_MIN_PROB      = float(os.environ.get("REC_MIN_PROB", "0.55"))
_STOP_LOSS_PCT = float(os.environ.get("REC_STOP_LOSS_PCT", "0.05"))
_TARGET_PCT    = float(os.environ.get("REC_TARGET_PCT", "0.10"))
_ENTRY_BAND    = float(os.environ.get("REC_ENTRY_BAND", "0.015"))
_VOL_HEAT_H    = float(os.environ.get("REC_VOL_HEAT_HIGH", "20.0"))
_VOL_HEAT_M    = float(os.environ.get("REC_VOL_HEAT_MED", "10.0"))
_CHG_HEAT_H    = float(os.environ.get("REC_CHG_HEAT_HIGH", "15.0"))
_CHG_HEAT_M    = float(os.environ.get("REC_CHG_HEAT_MED", "10.0"))
_ML_RISK_W     = float(os.environ.get("REC_ML_RISK_WEIGHT", "0.45"))
_SIM_MAX_W     = float(os.environ.get("REC_SIM_MAX_WEIGHT", "0.40"))
_SIM_SCALE_N   = float(os.environ.get("REC_SIM_SCALE_N", "25.0"))


@dataclass
class EntryRecommendation:
    code: str
    action: str
    entry_price: int
    entry_price_low: int
    entry_price_high: int
    target_price: int
    stop_loss_price: int
    expected_hold_days: int
    success_prob: float
    expected_return: float
    risk_score: float
    risk_reward_ratio: float
    rationale: dict = field(default_factory=dict)
    similar_cases: list = field(default_factory=list)


class EntryRecommender:

    def recommend(
        self,
        event: dict,
        ml_result,
        sim_stats: dict,
        similar_cases: list,
    ) -> EntryRecommendation:
        code  = event.get("code", "")
        price = int(event.get("price", 0))
        if not price:
            return self._skip(code, price, "price unavailable")

        atr_ratio   = abs(ml_result.expected_return / 10.0) if ml_result else 0.02
        stop_dist   = max(_STOP_LOSS_PCT, min(atr_ratio * 1.5, 0.12))
        target_dist = max(_TARGET_PCT, stop_dist * _MIN_RR)

        stop   = int(price * (1 - stop_dist))
        target = int(price * (1 + target_dist))
        rr     = target_dist / stop_dist if stop_dist > 0 else 0

        ml_prob  = ml_result.success_prob if ml_result else 0.5
        sim_prob = sim_stats.get("success_rate", ml_prob)
        n_cases  = sim_stats.get("count", 0)
        sim_w    = min(_SIM_MAX_W, n_cases / _SIM_SCALE_N * _SIM_MAX_W)
        prob     = (1.0 - sim_w) * ml_prob + sim_w * sim_prob

        risk   = self._risk(event, ml_result)
        action = self._decide(prob, risk, rr)

        return EntryRecommendation(
            code=code,
            action=action,
            entry_price=price,
            entry_price_low=int(price * (1 - _ENTRY_BAND)),
            entry_price_high=int(price * (1 + _ENTRY_BAND)),
            target_price=target,
            stop_loss_price=stop,
            expected_hold_days=ml_result.hold_days if ml_result else 5,
            success_prob=round(float(prob), 4),
            expected_return=round((target - price) / price * 100, 2),
            risk_score=round(float(risk), 4),
            risk_reward_ratio=round(rr, 2),
            rationale={
                "event_type":      event.get("event_type"),
                "ml_prob":         round(float(ml_prob), 4),
                "sim_prob":        round(float(sim_prob), 4),
                "sim_count":       n_cases,
                "sim_weight":      round(sim_w, 3),
                "avg_sim_return":  sim_stats.get("avg_return_5d", 0),
                "stop_dist_pct":   round(stop_dist * 100, 2),
                "target_dist_pct": round(target_dist * 100, 2),
                "risk_factors":    self._risk_factors(event, ml_result),
            },
            similar_cases=similar_cases[:5],
        )

    def _decide(self, prob: float, risk: float, rr: float) -> str:
        if risk > _MAX_RISK:
            return "SKIP"
        if prob < _MIN_PROB or rr < _MIN_RR:
            return "WAIT"
        return "BUY"

    def _risk(self, event: dict, ml_result) -> float:
        score = 0.0
        vol_r = float(event.get("volume_ratio") or 1.0)
        chg   = abs(float(event.get("change_rate") or 0.0))

        if vol_r > _VOL_HEAT_H:
            score += 0.25
        elif vol_r > _VOL_HEAT_M:
            score += 0.10
        if chg > _CHG_HEAT_H:
            score += 0.30
        elif chg > _CHG_HEAT_M:
            score += 0.10
        if ml_result:
            score += ml_result.risk_score * _ML_RISK_W

        return min(1.0, score)

    def _risk_factors(self, event: dict, ml_result) -> list[str]:
        factors = []
        if float(event.get("volume_ratio") or 0) > _VOL_HEAT_H:
            factors.append("거래량 과열")
        if abs(float(event.get("change_rate") or 0)) > _CHG_HEAT_H:
            factors.append("급등 과열")
        if ml_result and ml_result.risk_score > 0.5:
            factors.append("ML 고위험 판정")
        return factors

    def _skip(self, code: str, price: int, reason: str) -> EntryRecommendation:
        return EntryRecommendation(
            code=code, action="SKIP",
            entry_price=price, entry_price_low=price, entry_price_high=price,
            target_price=price, stop_loss_price=price,
            expected_hold_days=0, success_prob=0.0,
            expected_return=0.0, risk_score=1.0, risk_reward_ratio=0.0,
            rationale={"skip_reason": reason},
        )

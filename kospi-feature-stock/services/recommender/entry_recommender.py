import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_MIN_RR        = float(os.environ.get("REC_MIN_RISK_REWARD", "2.0"))
_MAX_RISK      = float(os.environ.get("REC_MAX_RISK", "0.60"))
_MIN_PROB      = float(os.environ.get("REC_MIN_PROB", "0.55"))
_ENTRY_BAND    = float(os.environ.get("REC_ENTRY_BAND", "0.015"))
_VOL_HEAT_H    = float(os.environ.get("REC_VOL_HEAT_HIGH", "20.0"))
_VOL_HEAT_M    = float(os.environ.get("REC_VOL_HEAT_MED", "10.0"))
_CHG_HEAT_H    = float(os.environ.get("REC_CHG_HEAT_HIGH", "15.0"))
_CHG_HEAT_M    = float(os.environ.get("REC_CHG_HEAT_MED", "10.0"))
_ML_RISK_W     = float(os.environ.get("REC_ML_RISK_WEIGHT", "0.45"))
_SIM_MAX_W     = float(os.environ.get("REC_SIM_MAX_WEIGHT", "0.40"))
_SIM_SCALE_N   = float(os.environ.get("REC_SIM_SCALE_N", "25.0"))

# ATR 기반 동적 익절/손절 파라미터
_ATR_STOP_MULT   = float(os.environ.get("REC_ATR_STOP_MULT",   "1.5"))   # 손절: ATR × 1.5
_ATR_TARGET_MULT = float(os.environ.get("REC_ATR_TARGET_MULT", "3.0"))   # 익절: ATR × 3.0
_STOP_MIN_PCT    = float(os.environ.get("REC_STOP_MIN_PCT",    "0.03"))   # 최소 손절 3%
_STOP_MAX_PCT    = float(os.environ.get("REC_STOP_MAX_PCT",    "0.12"))   # 최대 손절 12%
_TARGET_MIN_PCT  = float(os.environ.get("REC_TARGET_MIN_PCT",  "0.06"))   # 최소 익절 6%


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
        atr14: float | None = None,
    ) -> EntryRecommendation:
        """
        atr14: 14일 ATR 절댓값 (daily_bars.atr14 또는 feature 딕셔너리에서 전달).
               없으면 변동률 기반 추정값 사용.
        """
        code  = event.get("code", "")
        price = int(event.get("price", 0))
        if not price:
            return self._skip(code, price, "price unavailable")

        # ATR 비율 계산 (실제 ATR 우선, 없으면 feature의 atr_ratio 사용)
        atr_val = atr14
        if atr_val is None and ml_result:
            # ml_result에 atr_ratio 있으면 역산
            atr_ratio_feat = getattr(ml_result, "atr_ratio", None)
            if atr_ratio_feat and atr_ratio_feat > 0:
                atr_val = price * float(atr_ratio_feat)

        if atr_val and atr_val > 0:
            # ATR 기반 동적 익절/손절
            raw_stop   = atr_val * _ATR_STOP_MULT / price
            raw_target = atr_val * _ATR_TARGET_MULT / price
            stop_dist   = max(_STOP_MIN_PCT, min(raw_stop,   _STOP_MAX_PCT))
            target_dist = max(_TARGET_MIN_PCT, max(raw_target, stop_dist * _MIN_RR))
        else:
            # ATR 없을 때: 이벤트 변동률 기반 추정
            chg_rate = abs(float(event.get("change_rate") or 2.0))
            est_atr_ratio = max(0.01, chg_rate / 100 * 0.7)
            stop_dist   = max(_STOP_MIN_PCT, min(est_atr_ratio * _ATR_STOP_MULT,   _STOP_MAX_PCT))
            target_dist = max(_TARGET_MIN_PCT, stop_dist * _MIN_RR)

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
                "atr_based":       atr_val is not None and atr_val > 0,
                "atr14":           round(float(atr_val), 2) if atr_val else None,
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

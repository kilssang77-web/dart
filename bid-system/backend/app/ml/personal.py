"""
개인화 편향 보정 엔진 — 내 투찰이력 기반 습관적 편향 계산.

rate_diff 정의: (actual_winner_rate - submitted_rate) * 100
  양수 → 낙찰자가 더 높게 입찰 → 사용자가 너무 낮게 입찰
  음수 → 낙찰자가 더 낮게 입찰 → 사용자가 너무 높게 입찰
"""
import logging
import numpy as np
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

MAX_CORRECTION = 0.008
OUTLIER_THRESHOLD = 5.0
MIN_SAMPLES_FULL_CONF = 50


class PersonalBiasAnalyzer:
    """사용자 투찰이력에서 습관적 편향을 추출해 추천 요율 보정."""

    def compute(
        self,
        db,
        user_id: int,
        agency_name: Optional[str] = None,
        lookback_months: int = 24,
    ) -> dict:
        from sqlalchemy import text

        cutoff = datetime.now() - timedelta(days=lookback_months * 30)

        rows = db.execute(text("""
            SELECT submitted_rate, actual_winner_rate, rate_diff,
                   agency_name, bid_date
            FROM my_bid_records
            WHERE user_id = :uid
              AND result IN ('won', 'lost')
              AND actual_winner_rate IS NOT NULL
              AND submitted_rate IS NOT NULL
              AND bid_date >= :cutoff
            ORDER BY bid_date DESC
        """), {"uid": user_id, "cutoff": cutoff}).fetchall()

        if not rows:
            return self._empty_result()

        diffs, agency_diffs, weights = [], [], []
        now = datetime.now()

        for r in rows:
            if r.rate_diff is not None:
                diff = float(r.rate_diff)
            elif r.actual_winner_rate and r.submitted_rate:
                diff = (float(r.actual_winner_rate) - float(r.submitted_rate)) * 100
            else:
                continue

            if abs(diff) > OUTLIER_THRESHOLD:
                continue

            bd = r.bid_date if isinstance(r.bid_date, datetime) else (datetime.combine(r.bid_date, datetime.min.time()) if r.bid_date else None)
            days_ago = (now - bd).days if bd else 365
            weight = np.exp(-days_ago / 365)
            diffs.append(diff)
            weights.append(weight)

            if agency_name and r.agency_name and agency_name in r.agency_name:
                agency_diffs.append(diff)

        if not diffs:
            return self._empty_result()

        w = np.array(weights)
        d = np.array(diffs)
        avg_bias_pct = float(np.average(d, weights=w))
        correction = float(np.clip(avg_bias_pct / 100.0, -MAX_CORRECTION, MAX_CORRECTION))

        agency_correction = None
        if len(agency_diffs) >= 3:
            agency_correction = float(np.clip(np.mean(agency_diffs) / 100.0, -MAX_CORRECTION, MAX_CORRECTION))

        sample_count = len(diffs)
        confidence = min(1.0, sample_count / MIN_SAMPLES_FULL_CONF)

        if avg_bias_pct > 0.15:
            direction = "too_low"
        elif avg_bias_pct < -0.15:
            direction = "too_high"
        else:
            direction = "balanced"

        narrative = self._build_narrative(
            avg_bias_pct, direction, sample_count,
            agency_name, agency_diffs, agency_correction
        )

        return {
            "correction": round(correction, 6),
            "agency_correction": round(agency_correction, 6) if agency_correction is not None else None,
            "confidence": round(confidence, 3),
            "direction": direction,
            "avg_bias_pct": round(avg_bias_pct, 4),
            "sample_count": sample_count,
            "narrative": narrative,
        }

    def _build_narrative(self, avg_bias_pct, direction, sample_count,
                         agency_name, agency_diffs, agency_correction) -> str:
        if direction == "too_low":
            msg = (f"최근 {sample_count}건 분석: 낙찰자 대비 평균 {avg_bias_pct:.2f}% "
                   f"낮게 투찰하는 경향 → 추천 요율 상향 조정됨.")
        elif direction == "too_high":
            msg = (f"최근 {sample_count}건 분석: 낙찰자 대비 평균 {abs(avg_bias_pct):.2f}% "
                   f"높게 투찰하는 경향 → 추천 요율 하향 조정됨.")
        else:
            msg = (f"최근 {sample_count}건 분석: 투찰 편향 균형 "
                   f"(낙찰자 대비 평균 차이 {avg_bias_pct:+.2f}%).")

        if agency_name and len(agency_diffs) >= 3 and agency_correction is not None:
            ac_pct = agency_correction * 100
            if abs(ac_pct) > 0.1:
                d_str = "상향" if ac_pct > 0 else "하향"
                msg += (f" '{agency_name}' 발주처 {len(agency_diffs)}건 기준 "
                        f"추가 {d_str} 조정({ac_pct:+.2f}%) 적용.")
        return msg

    def _empty_result(self) -> dict:
        return {
            "correction": 0.0,
            "agency_correction": None,
            "confidence": 0.0,
            "direction": "balanced",
            "avg_bias_pct": 0.0,
            "sample_count": 0,
            "narrative": "투찰이력 데이터 부족 (이력이 쌓일수록 추천 정확도 향상).",
        }


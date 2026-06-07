"""
E2: 적격심사 엔진

목표: 투찰 전 적격심사 통과 가능성 사전 검증
      통과 불가 공고 → NO_GO 처리로 헛수고 방지

지원 기준:
  - 지방계약법 시행규칙 [별표2] 적격심사 세부기준 (추정가격 50억 미만 공사)
  - 국가계약법 시행규칙 [별표2] 적격심사 세부기준 (50억 이상)

점수 구성 (지방계약법 50억 미만):
  시공경험평가  40점 만점
  기술능력평가  20점 만점
  경영상태평가  20점 만점
  신인도        ±10점 (가감점)
  합계 통과기준 82점 이상
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import math


# ── 계약법별 기준 상수 ──────────────────────────────────────────────

CRITERIA = {
    # 지방계약법 — 추정가격 50억 미만
    "local_under50": {
        "pass_score": 82.0,
        "experience_max": 40.0,
        "tech_max": 20.0,
        "finance_max": 20.0,
        "reputation_range": (-10.0, 10.0),
        "experience_ratio_full": 2.0,   # 실적/투찰금액 >= 2배 시 만점
        "experience_ratio_min": 0.5,    # 최소 인정 비율
    },
    # 지방계약법 — 추정가격 50억 이상
    "local_over50": {
        "pass_score": 87.0,
        "experience_max": 30.0,
        "tech_max": 25.0,
        "finance_max": 30.0,
        "reputation_range": (-5.0, 5.0),
        "experience_ratio_full": 2.0,
        "experience_ratio_min": 0.5,
    },
    # 국가계약법 — 추정가격 100억 미만
    "national_under100": {
        "pass_score": 88.0,
        "experience_max": 30.0,
        "tech_max": 25.0,
        "finance_max": 30.0,
        "reputation_range": (-5.0, 5.0),
        "experience_ratio_full": 2.0,
        "experience_ratio_min": 0.5,
    },
}


@dataclass
class QualificationResult:
    verdict: str                   # PASS / FAIL / UNCERTAIN
    pass_prob: float               # 0~1
    min_pass_amount: Optional[int]
    max_pass_amount: Optional[int]
    score_breakdown: Dict[str, Any]
    fail_reason: Optional[str]
    criteria_type: str


def _get_criteria_type(base_amount: int, contract_law: str = "local") -> str:
    if contract_law == "national":
        return "national_under100"
    if base_amount >= 5_000_000_000:
        return "local_over50"
    return "local_under50"


def _calc_experience_score(
    our_experience: int,
    bid_amount: int,
    share_rate: float,
    criteria: dict,
) -> float:
    """시공경험평가 점수 계산"""
    adjusted_amount = bid_amount * share_rate
    if adjusted_amount <= 0:
        return 0.0
    ratio = our_experience / adjusted_amount
    ratio_full = criteria["experience_ratio_full"]
    ratio_min  = criteria["experience_ratio_min"]
    max_score  = criteria["experience_max"]

    if ratio >= ratio_full:
        return max_score
    if ratio < ratio_min:
        return 0.0
    # 선형 보간
    return max_score * (ratio - ratio_min) / (ratio_full - ratio_min)


def _calc_finance_score(
    annual_revenue: int,
    bid_amount: int,
    share_rate: float,
    criteria: dict,
) -> float:
    """경영상태평가 점수 — 매출 대비 투찰금액 비율 기반"""
    adjusted = bid_amount * share_rate
    if adjusted <= 0 or annual_revenue <= 0:
        return criteria["finance_max"] * 0.5  # 데이터 없으면 50% 가정
    ratio = annual_revenue / adjusted
    max_score = criteria["finance_max"]
    if ratio >= 1.5:
        return max_score
    if ratio < 0.3:
        return 0.0
    return max_score * (ratio - 0.3) / (1.5 - 0.3)


def _calc_tech_score(
    workforce_count: int,
    bid_amount: int,
    criteria: dict,
) -> float:
    """기술능력평가 점수 — 기술인력 / 공사규모 비율 기반 (단순화)"""
    max_score = criteria["tech_max"]
    if workforce_count <= 0:
        return max_score * 0.5  # 데이터 없으면 50% 가정
    # 10억당 기술인력 1명 기준 만점
    required = max(1, bid_amount / 1_000_000_000)
    ratio = workforce_count / required
    if ratio >= 2.0:
        return max_score
    if ratio < 0.5:
        return max_score * 0.3
    return max_score * min(1.0, ratio / 2.0)


def check_qualification(
    *,
    base_amount: int,
    estimated_price_center: float,
    estimated_price_std: float,
    our_experience: int,
    annual_revenue: int,
    workforce_count: int,
    share_rate: float = 1.0,
    reputation_score: float = 0.0,
    contract_law: str = "local",
    n_scenarios: int = 200,
) -> QualificationResult:
    """
    적격심사 통과 확률 및 유효 투찰 금액 범위 계산.

    Args:
        base_amount:             기초금액 (원)
        estimated_price_center:  예정가격/기초금액 사정율 중앙값
        estimated_price_std:     사정율 표준편차
        our_experience:          해당 업종 시공실적 (원)
        annual_revenue:          연매출 (원)
        workforce_count:         기술인력 수
        share_rate:              공동도급 우리 지분율 (단독=1.0)
        reputation_score:        신인도 점수 (-10 ~ +10)
        contract_law:            "local" / "national"
        n_scenarios:             시나리오 수 (사정율 범위 순열)
    """
    import numpy as np
    rng = np.random.default_rng(42)

    criteria_type = _get_criteria_type(base_amount, contract_law)
    crit = CRITERIA[criteria_type]

    # 사정율 시나리오 생성 (P10 ~ P90)
    srate_samples = rng.normal(estimated_price_center, max(estimated_price_std, 0.002), n_scenarios)
    srate_samples = np.clip(srate_samples, estimated_price_center - 0.03, estimated_price_center + 0.03)

    pass_count  = 0
    pass_amounts: list[int] = []
    fail_amounts: list[int] = []
    score_list: list[float] = []

    for srate in srate_samples:
        ep = int(base_amount * srate)          # 예정가격 (원)
        bid_amount = int(ep * share_rate)       # 실질 투찰금액 기준

        exp_score  = _calc_experience_score(our_experience, bid_amount, share_rate, crit)
        fin_score  = _calc_finance_score(annual_revenue, bid_amount, share_rate, crit)
        tech_score = _calc_tech_score(workforce_count, bid_amount, crit)
        rep_score  = max(crit["reputation_range"][0], min(crit["reputation_range"][1], reputation_score))

        total = exp_score + fin_score + tech_score + rep_score
        score_list.append(total)

        if total >= crit["pass_score"]:
            pass_count += 1
            pass_amounts.append(ep)
        else:
            fail_amounts.append(ep)

    pass_prob = pass_count / n_scenarios

    # 유효 금액 범위 (통과 시나리오 기준)
    min_pass = int(min(pass_amounts)) if pass_amounts else None
    max_pass = int(max(pass_amounts)) if pass_amounts else None

    avg_score = float(np.mean(score_list))
    score_breakdown = {
        "avg_total_score":  round(avg_score, 2),
        "pass_score_threshold": crit["pass_score"],
        "avg_experience_score": round(float(np.mean([
            _calc_experience_score(our_experience, int(base_amount * s * share_rate), share_rate, crit)
            for s in srate_samples
        ])), 2),
        "avg_finance_score":    round(float(np.mean([
            _calc_finance_score(annual_revenue, int(base_amount * s * share_rate), share_rate, crit)
            for s in srate_samples
        ])), 2),
        "reputation_score":     round(rep_score, 2),
        "criteria_type":        criteria_type,
    }

    # 판정
    if pass_prob >= 0.80:
        verdict = "PASS"
        fail_reason = None
    elif pass_prob >= 0.40:
        verdict = "UNCERTAIN"
        fail_reason = f"적격 통과 확률 {pass_prob:.0%} — 시공실적 또는 경영상태 보강 필요"
    else:
        verdict = "FAIL"
        fail_reason = _build_fail_reason(score_breakdown, crit, our_experience, annual_revenue)

    return QualificationResult(
        verdict=verdict,
        pass_prob=round(pass_prob, 4),
        min_pass_amount=min_pass,
        max_pass_amount=max_pass,
        score_breakdown=score_breakdown,
        fail_reason=fail_reason,
        criteria_type=criteria_type,
    )


def _build_fail_reason(breakdown: dict, crit: dict, experience: int, revenue: int) -> str:
    reasons = []
    avg = breakdown["avg_total_score"]
    gap = crit["pass_score"] - avg

    if breakdown["avg_experience_score"] < crit["experience_max"] * 0.5:
        exp_fmt = f"{experience / 1e8:.1f}억"
        reasons.append(f"시공실적 부족 ({exp_fmt} 보유, 추가 확보 필요)")
    if breakdown["avg_finance_score"] < crit["finance_max"] * 0.5:
        rev_fmt = f"{revenue / 1e8:.1f}억"
        reasons.append(f"경영상태 미흡 (연매출 {rev_fmt})")
    if not reasons:
        reasons.append(f"종합점수 미달 (평균 {avg:.1f}점, 기준 {crit['pass_score']}점, 부족 {gap:.1f}점)")

    return " | ".join(reasons)


def get_valid_bid_range(
    qual_result: QualificationResult,
    floor_rate: float,
    base_amount: int,
) -> tuple[Optional[int], Optional[int]]:
    """
    적격심사 통과 + 낙찰 유효 조건을 모두 만족하는 투찰금액 범위 반환.

    낙찰 유효 조건: floor_rate * base_amount <= bid <= estimated_price
    적격 통과 조건: min_pass_amount <= bid <= max_pass_amount
    """
    floor_amount = int(floor_rate * base_amount)

    if qual_result.min_pass_amount is None:
        return None, None

    low  = max(floor_amount, qual_result.min_pass_amount)
    high = qual_result.max_pass_amount

    if low > high:
        return None, None  # 두 조건 양립 불가

    return low, high

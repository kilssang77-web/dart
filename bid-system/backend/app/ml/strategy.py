"""
E5: 전략 추천 엔진 — 단일 최적 투찰률 결정

핵심 변경:
  기존: 4개 전략 제시 → 사용자가 선택
  신규: 단일 최적 투찰률 + 명확한 이유 제시
        "이렇게 투찰하십시오"

목표함수:
  Maximize P(win | rate) × P(qualify | rate) × margin(rate)
  Subject to: rate ∈ valid_range (적격 통과 + 낙찰 유효 구간)

월간 수주 목표 달성 상황에 따라 공격성 자동 조절:
  목표 미달 → 공격적 (높은 win_prob 타겟)
  목표 달성 → 보수적 (마진 우선)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict, Any
import numpy as np


@dataclass
class StrategyInput:
    # 기초 정보
    base_amount:        int
    floor_rate:         float               # 낙찰하한율 (예: 0.87745)
    srate_center:       float               # 예정가격/기초금액 예측 중앙값
    srate_std:          float               # 표준편차
    srate_dist:         Optional[np.ndarray] = None  # Monte Carlo 사정율 분포

    # 경쟁 정보
    competitor_means:   List[float] = field(default_factory=list)
    competitor_stds:    List[float] = field(default_factory=list)
    competitor_min_dist: Optional[np.ndarray] = None  # 경쟁사 최소 투찰률 분포

    # 적격 정보
    valid_low:          Optional[float] = None   # 유효 투찰률 하한 (적격+낙찰 통합)
    valid_high:         Optional[float] = None   # 유효 투찰률 상한

    # 개인 편향
    bias_correction:    float = 0.0

    # 월 수주 목표 달성 상황
    monthly_target:     int = 3
    current_month_wins: int = 0

    # 이 기관 과거 승률
    historical_win_rate: float = 0.20


@dataclass
class SingleRecommendation:
    rate:               float           # 최적 투찰률 (소수, 예: 0.8720)
    bid_amount:         int             # 투찰금액 (원)
    win_prob:           float           # 해당 투찰률에서의 낙찰확률
    expected_value:     int             # 기대가치 (원)
    confidence:         float           # 추천 신뢰도 (0~1)
    strategy_type:      str             # aggressive / balanced / conservative
    rationale:          str             # 한국어 설명
    rationale_details:  List[str] = field(default_factory=list)
    valid_range:        Tuple[float, float] = (0.0, 1.0)
    prism_top5:         List[Dict] = field(default_factory=list)  # 상위 5개 후보 구간


def _target_win_prob(inp: StrategyInput) -> float:
    """월 수주 목표 달성도에 따라 목표 낙찰확률 조정"""
    remaining = inp.monthly_target - inp.current_month_wins
    if remaining > 2:
        return 0.60   # 많이 부족 → 공격적
    elif remaining > 0:
        return 0.45   # 약간 부족 → 균형
    else:
        return 0.25   # 달성 완료 → 마진 우선


def _calc_win_prob_at_rate(
    rate: float,
    floor_rate: float,
    srate_dist: np.ndarray,
    competitor_min_dist: Optional[np.ndarray],
    n_sim: int = 10_000,
    rng: Optional[np.random.Generator] = None,
) -> float:
    """특정 투찰률에서의 낙찰확률 계산"""
    if rng is None:
        rng = np.random.default_rng(42)

    # 낙찰하한 미달 → 즉시 0
    if rate < floor_rate:
        return 0.0

    # 사정율 분포 샘플링 (전달된 분포 사용 또는 전체 사용)
    if srate_dist is not None and len(srate_dist) > 0:
        n = min(n_sim, len(srate_dist))
        idx = rng.choice(len(srate_dist), size=n, replace=False)
        srates = srate_dist[idx]
    else:
        return 0.0

    # 유효 조건 1: rate <= srate (예정가격 이하)
    valid_mask = rate <= srates

    # 유효 조건 2: rate < min(경쟁사) (최저가 낙찰)
    if competitor_min_dist is not None and len(competitor_min_dist) > 0:
        n_comp = min(n, len(competitor_min_dist))
        comp_mins = competitor_min_dist[rng.choice(len(competitor_min_dist), size=n, replace=True)]
        win_mask = valid_mask & (rate <= comp_mins)
    else:
        # 경쟁사 분포 없으면 경쟁사 없다고 가정 (낙관적)
        win_mask = valid_mask

    return float(np.mean(win_mask))


def _scan_rate_range(
    inp: StrategyInput,
    rng: np.random.Generator,
    n_points: int = 100,
) -> List[Dict[str, float]]:
    """
    유효 투찰률 구간을 스캔하여 각 지점의 (rate, win_prob, ev) 계산.
    Prism 방식을 단일 추천으로 통합.
    """
    low  = inp.valid_low  or (inp.floor_rate * 0.99)
    high = inp.valid_high or (inp.srate_center + 0.015)

    # 너무 좁으면 사정율 중앙값 기준으로 확장
    if high - low < 0.002:
        low  = inp.srate_center * inp.floor_rate - 0.002
        high = inp.srate_center + 0.005

    rates = np.linspace(low, high, n_points)
    results = []

    for rate in rates:
        wp = _calc_win_prob_at_rate(
            rate=rate,
            floor_rate=inp.floor_rate,
            srate_dist=inp.srate_dist,
            competitor_min_dist=inp.competitor_min_dist,
            n_sim=5_000,
            rng=rng,
        )
        # 기대가치 = 낙찰확률 × 기초금액 × (1 - rate/srate_center) 근사 마진
        approx_margin = max(0.0, 1.0 - rate / max(inp.srate_center, 0.001))
        ev = wp * inp.base_amount * approx_margin
        results.append({"rate": float(rate), "win_prob": wp, "ev": ev})

    return results


def _select_optimal_rate(
    scan: List[Dict],
    target_win_prob: float,
    strategy_type: str,
) -> Dict:
    """스캔 결과에서 전략 목표에 맞는 최적 포인트 선택"""
    if not scan:
        return {"rate": 0.0, "win_prob": 0.0, "ev": 0.0}

    if strategy_type == "aggressive":
        # win_prob 최대화 포인트
        return max(scan, key=lambda x: x["win_prob"])

    elif strategy_type == "conservative":
        # EV 최대화 포인트 (단, win_prob >= 0.15 보장)
        candidates = [p for p in scan if p["win_prob"] >= 0.15]
        if not candidates:
            candidates = scan
        return max(candidates, key=lambda x: x["ev"])

    else:  # balanced
        # target_win_prob에 가장 가까우면서 EV 좋은 포인트
        closest = min(scan, key=lambda x: abs(x["win_prob"] - target_win_prob))
        # 근처 ±10 포인트 중 EV 최대
        idx = scan.index(closest)
        neighborhood = scan[max(0, idx - 10): idx + 11]
        return max(neighborhood, key=lambda x: x["ev"])


def _determine_strategy_type(inp: StrategyInput, target_wp: float) -> str:
    """상황에 따라 전략 유형 결정"""
    remaining = inp.monthly_target - inp.current_month_wins
    strong_comp = len([m for m in inp.competitor_means if m < inp.srate_center - 0.005])

    if remaining > 2 or strong_comp >= 2:
        return "aggressive"
    if remaining <= 0:
        return "conservative"
    return "balanced"


def _build_rationale(
    rec_rate: float,
    strategy_type: str,
    win_prob: float,
    inp: StrategyInput,
) -> Tuple[str, List[str]]:
    """추천 이유 한국어 설명 생성"""
    details = []

    # 전략 유형 설명
    strategy_labels = {
        "aggressive": "공격형 (낙찰확률 우선)",
        "balanced":   "균형형 (확률·이익 균형)",
        "conservative": "안정형 (이익 우선)",
    }
    details.append(f"전략: {strategy_labels.get(strategy_type, strategy_type)}")

    # 경쟁 상황
    n_comp = len(inp.competitor_means)
    if n_comp > 0:
        avg_comp = np.mean(inp.competitor_means)
        if rec_rate < avg_comp:
            details.append(f"경쟁사 평균 투찰률({avg_comp:.4f}) 하회 → 낙찰 가능 포지션")
        else:
            details.append(f"경쟁사 평균 투찰률({avg_comp:.4f}) 상회 → 마진 우선 전략")

    # 목표 달성 상황
    remaining = inp.monthly_target - inp.current_month_wins
    if remaining > 0:
        details.append(f"이달 수주 목표 {remaining}건 남음 → {'공격적 투찰' if remaining > 2 else '균형 투찰'} 적용")
    else:
        details.append("이달 수주 목표 달성 → 이익 우선 전략 적용")

    # 개인 편향 보정
    if abs(inp.bias_correction) > 0.001:
        direction = "상향" if inp.bias_correction > 0 else "하향"
        details.append(f"과거 이력 기반 개인 편향 보정 {direction} ({inp.bias_correction:+.4f})")

    main = (
        f"투찰률 {rec_rate:.4f} 추천 — "
        f"낙찰확률 {win_prob:.1%}, 전략: {strategy_labels.get(strategy_type, '')}"
    )
    return main, details


def recommend(inp: StrategyInput, n_sim: int = 30_000) -> SingleRecommendation:
    """
    단일 최적 투찰률 추천 메인 함수.

    Monte Carlo 사정율 분포와 경쟁사 최소 투찰률 분포가 없으면
    규칙 기반 폴백으로 동작.
    """
    rng = np.random.default_rng(42)

    # srate_dist 없으면 생성
    if inp.srate_dist is None or len(inp.srate_dist) == 0:
        sigma = max(0.002, min(inp.srate_std, 0.010))
        inp.srate_dist = rng.normal(inp.srate_center, sigma, n_sim).clip(
            inp.srate_center - 0.028, inp.srate_center + 0.028
        )

    # 목표 낙찰확률 + 전략 유형 결정
    target_wp     = _target_win_prob(inp)
    strategy_type = _determine_strategy_type(inp, target_wp)

    # 유효 투찰률 구간 확인
    floor_amount_rate = inp.floor_rate
    low  = inp.valid_low  or (floor_amount_rate * 0.99)
    high = inp.valid_high or (inp.srate_center + 0.015)

    # 구간 스캔
    scan = _scan_rate_range(inp, rng, n_points=120)

    # 최적 포인트 선택
    optimal = _select_optimal_rate(scan, target_wp, strategy_type)

    # 개인 편향 보정 적용
    final_rate = optimal["rate"] + inp.bias_correction
    final_rate = max(low, min(high, final_rate))

    # 보정 후 win_prob 재계산
    final_wp = _calc_win_prob_at_rate(
        rate=final_rate,
        floor_rate=inp.floor_rate,
        srate_dist=inp.srate_dist,
        competitor_min_dist=inp.competitor_min_dist,
        n_sim=n_sim,
        rng=rng,
    )

    # 기대가치
    approx_margin = max(0.0, 1.0 - final_rate / max(inp.srate_center, 0.001))
    ev = int(final_wp * inp.base_amount * approx_margin)

    # 신뢰도: 사정율 신뢰도 + 경쟁사 데이터 유무 반영
    confidence = 0.5
    if inp.srate_std < 0.005:
        confidence += 0.2   # 사정율 예측이 안정적
    if inp.competitor_min_dist is not None:
        confidence += 0.2   # 경쟁사 분포 있음
    if inp.historical_win_rate > 0:
        confidence += 0.1   # 과거 이력 있음
    confidence = min(1.0, confidence)

    rationale, details = _build_rationale(final_rate, strategy_type, final_wp, inp)

    # Prism 상위 5개 구간
    prism_top5 = sorted(scan, key=lambda x: x["ev"], reverse=True)[:5]

    return SingleRecommendation(
        rate=round(final_rate, 4),
        bid_amount=int(final_rate * inp.base_amount),
        win_prob=round(final_wp, 4),
        expected_value=ev,
        confidence=round(confidence, 3),
        strategy_type=strategy_type,
        rationale=rationale,
        rationale_details=details,
        valid_range=(round(low, 4), round(high, 4)),
        prism_top5=[
            {"rate": round(p["rate"], 4), "win_prob": round(p["win_prob"], 4), "ev": int(p["ev"])}
            for p in prism_top5
        ],
    )

"""
복수예가 시뮬레이션 + Monte Carlo 낙찰확률 엔진

나라장터 메커니즘:
  기초금액 → 복수예가 15개(±2%) 생성 → 4개 무작위 추첨 → 평균 = 예정가격(사정률)
  → 낙찰하한가(예정가격 × 낙찰하한율) → 유효입찰 중 최저가 낙찰

공종별 낙찰하한율:
  전기공사업, 정보통신공사업, 소방시설공사업: 86.745%
  나머지 모든 공종: 87.745%
"""
import numpy as np
from typing import List, Optional

# 낙찰하한율 테이블: 공종명 키워드 → 비율
FLOOR_RATE_TABLE: dict = {
    "전기공사업":    0.86745,
    "정보통신공사업": 0.86745,
    "소방시설공사업": 0.86745,
}
DEFAULT_FLOOR_RATE: float = 0.87745


def get_floor_rate(industry_name: str) -> float:
    """공종명으로 낙찰하한율 반환 (미매칭 시 87.745%)."""
    if not industry_name:
        return DEFAULT_FLOOR_RATE
    for keyword, rate in FLOOR_RATE_TABLE.items():
        if keyword in industry_name:
            return rate
    return DEFAULT_FLOOR_RATE


def simulate_yejung(
    base_amount: int,
    srate_center: float,
    srate_std: float,
    n_sim: int = 30_000,
    rng: Optional[np.random.Generator] = None,
) -> np.ndarray:
    """
    복수예가 추첨 시뮬레이션 -> 사정률 분포 반환.

    나라장터 실제 메커니즘:
      예가 후보 15개 생성 -> 4개 무작위 추첨 -> 평균 = 예정가격/기초금액

    시뮬레이션 근사:
      각 예가 ~ N(srate_center, sigma), ±2% 클램프
      n_sim 회 반복: 15개 샘플 후 4개 추첨 -> 평균

    Returns:
        shape (n_sim,) 사정률 배열
    """
    if rng is None:
        rng = np.random.default_rng(42)

    sigma = max(0.002, min(srate_std, 0.010))

    candidates = rng.normal(loc=srate_center, scale=sigma, size=(n_sim, 15))
    candidates = np.clip(candidates, srate_center - 0.02, srate_center + 0.02)

    # 각 행에서 4개 무작위 선택 (noise 정렬로 벡터화)
    noise = rng.random((n_sim, 15))
    idx   = np.argsort(noise, axis=1)[:, :4]
    selected = candidates[np.arange(n_sim)[:, None], idx]
    return selected.mean(axis=1)


def monte_carlo_win_prob(
    our_bid_rate: float,
    floor_rate_pct: float,
    srate_dist: np.ndarray,
    competitor_means: List[float],
    competitor_stds: List[float],
    n_sim: int = 30_000,
    rng: Optional[np.random.Generator] = None,
) -> dict:
    """
    Monte Carlo 낙찰확률 계산.

    낙찰 성공 조건:
      1. our_bid_rate >= srate_dist[i] x floor_rate_pct  (낙찰하한 이상)
      2. our_bid_rate <= srate_dist[i]                    (예정가격 이하)
      3. our_bid_rate <= min(경쟁사 투찰률)               (최저가 낙찰)

    Parameters:
        our_bid_rate    : 우리 투찰률 (기초금액 대비, 예: 0.9120)
        floor_rate_pct  : 낙찰하한율 (예: 0.87745)
        srate_dist      : simulate_yejung() 반환 사정률 분포
        competitor_means: 경쟁사별 평균 투찰률
        competitor_stds : 경쟁사별 표준편차

    Returns:
        win_prob    : 낙찰확률 (0~1)
        avg_rank    : 평균 순위 (유효 입찰 시)
        valid_ratio : 유효 입찰 비율 (하한 이상 & 예가 이하)
    """
    if rng is None:
        rng = np.random.default_rng(42)

    n = len(srate_dist)
    if n_sim != n:
        idx    = rng.integers(0, n, size=n_sim)
        srates = srate_dist[idx]
    else:
        srates = srate_dist

    floor_prices = srates * floor_rate_pct
    valid        = (our_bid_rate >= floor_prices) & (our_bid_rate <= srates)
    valid_ratio  = float(valid.mean())

    if not competitor_means:
        return {
            "win_prob":    round(valid_ratio, 4),
            "avg_rank":    1.0,
            "valid_ratio": round(valid_ratio, 4),
        }

    n_comp    = len(competitor_means)
    comp_bids = np.column_stack([
        rng.normal(m, max(s, 0.001), n_sim)
        for m, s in zip(competitor_means, competitor_stds)
    ])

    comp_min = comp_bids.min(axis=1)
    win_mask = valid & (our_bid_rate <= comp_min)
    win_prob = float(win_mask.mean())

    if valid.any():
        ranks    = (comp_bids[valid] < our_bid_rate).sum(axis=1) + 1
        avg_rank = float(ranks.mean())
    else:
        avg_rank = float(n_comp + 1)

    return {
        "win_prob":    round(win_prob,    4),
        "avg_rank":    round(avg_rank,    2),
        "valid_ratio": round(valid_ratio, 4),
    }


def recommend_with_simulation(
    base_amount: int,
    industry_name: str,
    srate_center: float,
    srate_std: float,
    competitor_means: List[float],
    competitor_stds: List[float],
    hard_floor: float,
    ens_center: float,
    ens_upper: float,
    n_sim: int = 30_000,
) -> dict:
    """
    Monte Carlo 기반 4전략 추천.

    전략:
      공격형(aggressive)          : 낙찰하한 직상 (낙찰확률 최우선)
      균형형(balanced)            : 앙상블 중심
      보수형(conservative)        : 앙상블 상단 (마진 우선)
      경쟁회피형(avoid_competition): 경쟁사 군집 최솟값 아래 포지션

    Returns:
        strategies        : 4전략별 {rate, win_prob, avg_rank, target, risk, note}
        win_probabilities : 4전략 낙찰확률 요약
        simulation        : 시뮬레이션 메타데이터
    """
    rng = np.random.default_rng(42)
    floor_rate_pct = get_floor_rate(industry_name)

    srate_dist    = simulate_yejung(base_amount, srate_center, srate_std, n_sim, rng)
    floor_abs_p50 = float(np.percentile(srate_dist, 50)) * floor_rate_pct
    delta         = 0.0015

    rate_aggressive   = round(max(hard_floor + delta, floor_abs_p50 + delta), 4)
    rate_balanced     = round(max(ens_center, rate_aggressive + 0.001), 4)
    rate_conservative = round(max(ens_upper,  rate_balanced   + 0.001), 4)

    if competitor_means:
        rate_avoid = max(round(min(competitor_means) - 0.001, 4), rate_aggressive)
    else:
        rate_avoid = max(round(ens_center - 0.002, 4), rate_aggressive)
    rate_avoid = round(rate_avoid, 4)

    def _wp(rate: float) -> dict:
        return monte_carlo_win_prob(
            rate, floor_rate_pct, srate_dist,
            competitor_means, competitor_stds, n_sim, rng,
        )

    wp_agg   = _wp(rate_aggressive)
    wp_bal   = _wp(rate_balanced)
    wp_con   = _wp(rate_conservative)
    wp_avoid = _wp(rate_avoid)

    return {
        "strategies": {
            "aggressive": {
                "rate":     rate_aggressive,
                "win_prob": wp_agg["win_prob"],
                "avg_rank": wp_agg["avg_rank"],
                "target":   "예정가격 직하 -- 낙찰확률 최우선",
                "risk":     "HIGH",
                "note":     f"낙찰하한({floor_rate_pct*100:.3f}%) 직상. 마진 최소 허용 전략.",
            },
            "balanced": {
                "rate":     rate_balanced,
                "win_prob": wp_bal["win_prob"],
                "avg_rank": wp_bal["avg_rank"],
                "target":   "확률·수익 균형",
                "risk":     "MEDIUM",
                "note":     "4개 엔진 앙상블 중심값. Monte Carlo 30,000회 확률 반영.",
            },
            "conservative": {
                "rate":     rate_conservative,
                "win_prob": wp_con["win_prob"],
                "avg_rank": wp_con["avg_rank"],
                "target":   "마진 우선 -- 낙찰확률 일부 양보",
                "risk":     "LOW",
                "note":     "공격적 경쟁사 위험 시 상단 전략으로 수익성 방어.",
            },
            "avoid_competition": {
                "rate":     rate_avoid,
                "win_prob": wp_avoid["win_prob"],
                "avg_rank": wp_avoid["avg_rank"],
                "target":   "경쟁사 회피 -- 공격형 군집 외부 포지션",
                "risk":     "MEDIUM",
                "note":     "경쟁사 투찰 집중 대역 회피. HHI 높을 때 유효.",
            },
        },
        "win_probabilities": {
            "at_aggressive":        wp_agg["win_prob"],
            "at_balanced":          wp_bal["win_prob"],
            "at_conservative":      wp_con["win_prob"],
            "at_avoid_competition": wp_avoid["win_prob"],
        },
        "simulation": {
            "n_sim":          n_sim,
            "floor_rate_pct": floor_rate_pct,
            "srate_p10":      round(float(np.percentile(srate_dist, 10)), 4),
            "srate_p25":      round(float(np.percentile(srate_dist, 25)), 4),
            "srate_median":   round(float(np.percentile(srate_dist, 50)), 4),
            "srate_p75":      round(float(np.percentile(srate_dist, 75)), 4),
            "srate_p90":      round(float(np.percentile(srate_dist, 90)), 4),
            "floor_abs_p50":  round(floor_abs_p50, 4),
        },
    }
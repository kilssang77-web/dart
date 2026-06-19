"""
복수예가 시뮬레이션 + Monte Carlo 낙찰확률 엔진

나라장터 메커니즘:
  기초금액 → 복수예가 15개(±2%) 생성 → 4개 무작위 추첨 → 평균 = 예정가격(사정률)
  → 낙찰하한가(예정가격 × 낙찰하한율) → 유효입찰 중 최고가 낙찰 (예정가격에 가장 근접한 아래 입찰)

공종별 낙찰하한율:
  전기공사업, 정보통신공사업, 소방시설공사업: 86.745%
  나머지 모든 공종: 87.745%
"""
import numpy as np
from itertools import combinations
from typing import List, Optional

from .a_value import FLOOR_RATE_TABLE, DEFAULT_FLOOR_RATE, calc_floor_rate as get_floor_rate


def simulate_yejung_bimodal(
    base_amount: int,
    srate_center: float,
    srate_std: float,
    n_sim: int = 30_000,
    rng: Optional[np.random.Generator] = None,
    pos_weights: Optional[List[float]] = None,
    high_mix: float = 0.30,
    high_shift: float = 0.008,
) -> np.ndarray:
    """
    바이모달 사정율 시뮬레이션.

    일부 발주기관의 복수예가는 단일 정규분포가 아닌 두 봉우리를 가짐.
    예: 사전공개 없이 동일 기관이 분기별로 높/낮 예가 패턴을 반복하는 경우.

    구현: 두 개의 정규분포를 (1-high_mix) : high_mix 비율로 혼합.
      · 저예가 집단: N(srate_center - high_shift/2, srate_std)
      · 고예가 집단: N(srate_center + high_shift, srate_std * 0.7)

    Args:
        high_mix:   고예가 집단 비율 (0~1, 기본 0.30)
        high_shift: 저→고 예가 중심 이동 폭 (기본 0.008 = 0.8%p)
    """
    if rng is None:
        rng = np.random.default_rng(42)

    sigma = max(0.002, min(srate_std, 0.010))
    n_high = int(n_sim * high_mix)
    n_low  = n_sim - n_high

    center_low  = srate_center - high_shift * 0.4
    center_high = srate_center + high_shift * 0.6

    def _draw(n: int, center: float, sig: float) -> np.ndarray:
        cands = rng.normal(loc=center, scale=sig, size=(n, 15))
        cands = np.clip(cands, srate_center - 0.028, srate_center + 0.028)
        if pos_weights is not None:
            log_w  = np.log(np.maximum(pos_weights, 1e-9))
            gumbel = rng.gumbel(size=(n, 15))
            idx    = np.argsort(log_w + gumbel, axis=1)[:, -4:]
        else:
            idx = np.argsort(rng.random((n, 15)), axis=1)[:, :4]
        return cands[np.arange(n)[:, None], idx].mean(axis=1)

    parts = []
    if n_low  > 0: parts.append(_draw(n_low,  center_low,  sigma))
    if n_high > 0: parts.append(_draw(n_high, center_high, sigma * 0.75))
    result = np.concatenate(parts)
    rng.shuffle(result)
    return result


def simulate_yejung(
    base_amount: int,
    srate_center: float,
    srate_std: float,
    n_sim: int = 30_000,
    rng: Optional[np.random.Generator] = None,
    pos_weights: Optional[List[float]] = None,
) -> np.ndarray:
    """
    복수예가 추첨 시뮬레이션 -> 사정률 분포 반환.

    나라장터 실제 메커니즘:
      예가 후보 15개 생성 -> 4개 무작위 추첨 -> 평균 = 예정가격/기초금액

    시뮬레이션 근사:
      각 예가 ~ N(srate_center, sigma), ±2.8% 클램프
      n_sim 회 반복: 15개 샘플 후 4개 추첨(위치 가중치 적용) -> 평균

    Args:
        pos_weights: 15개 위치별 추첨 가중치 (합=1.0). None이면 균등.

    Returns:
        shape (n_sim,) 사정률 배열
    """
    if rng is None:
        rng = np.random.default_rng(42)

    sigma = max(0.002, min(srate_std, 0.010))

    # inpo21c 실측 spread: p02=-2.77%, p98=2.76% → ±2.8% 클램프
    candidates = rng.normal(loc=srate_center, scale=sigma, size=(n_sim, 15))
    candidates = np.clip(candidates, srate_center - 0.028, srate_center + 0.028)

    # 4개 위치 선택 — pos_weights 있으면 Gumbel-max trick (가중 비복원 추첨)
    if pos_weights is not None:
        log_w = np.log(np.maximum(pos_weights, 1e-9))  # 0-weight 방지
        gumbel = rng.gumbel(size=(n_sim, 15))
        idx = np.argsort(log_w + gumbel, axis=1)[:, -4:]
    else:
        noise = rng.random((n_sim, 15))
        idx = np.argsort(noise, axis=1)[:, :4]

    selected = candidates[np.arange(n_sim)[:, None], idx]
    return selected.mean(axis=1)


def monte_carlo_win_prob(
    our_bid_rate: float,
    floor_rate_pct: float,
    srate_dist: np.ndarray,
    competitor_means: List[float],
    competitor_stds: List[float],
    n_sim: int = 50_000,
    rng: Optional[np.random.Generator] = None,
) -> dict:
    """
    Monte Carlo 낙찰확률 계산.

    낙찰 성공 조건:
      1. our_bid_rate >= floor_rate_pct           (낙찰하한율 이상 — 기초금액 대비)
      2. our_bid_rate <= srate_dist[i]             (예정가격 이하)
      3. our_bid_rate >= max(경쟁사 유효 투찰률)    (최고가 낙찰 — 예정가격에 가장 근접)

    Parameters:
        our_bid_rate    : 우리 투찰률 (기초금액 대비, 예: 0.8800)
        floor_rate_pct  : 낙찰하한율 (예: 0.87745)
        srate_dist      : simulate_yejung() 반환 사정률 분포 (예정가격/기초금액)
        competitor_means: 경쟁사별 평균 투찰률 (기초금액 대비)
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
        srates = srate_dist[:n_sim]

    # 유효성: 낙찰하한율 × 사정율 = 실제 낙찰하한가/기초금액 ≤ 투찰률 ≤ 사정율
    effective_floor = floor_rate_pct * srates
    valid       = (our_bid_rate >= effective_floor) & (our_bid_rate <= srates)
    valid_ratio = float(valid.mean())

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

    # 복수예가: 유효 범위 내 최고가 낙찰 (예정가격에 가장 근접한 아래 입찰)
    # 무효 입찰(하한 미만·예정가 초과)은 -inf로 마스킹 → max 연산에서 자동 제외
    comp_valid    = (comp_bids >= floor_rate_pct * srates[:, None]) & (comp_bids <= srates[:, None])
    comp_bids_eff = np.where(comp_valid, comp_bids, -np.inf)
    comp_max      = comp_bids_eff.max(axis=1)  # 경쟁자 중 최고 유효 입찰

    win_mask = valid & (our_bid_rate >= comp_max)   # 내가 유효하고 경쟁자보다 높으면 낙찰
    win_prob = float(win_mask.mean())

    if valid.any():
        # 순위: 나보다 높은 유효 경쟁자 수 + 1 (1위=낙찰)
        comp_above = (comp_bids[valid] > our_bid_rate) & comp_valid[valid]
        avg_rank   = float((comp_above.sum(axis=1) + 1).mean())
    else:
        avg_rank = float(n_comp + 1)

    return {
        "win_prob":    round(win_prob,    4),
        "avg_rank":    round(avg_rank,    2),
        "valid_ratio": round(valid_ratio, 4),
    }


def monte_carlo_win_prob_empirical(
    our_bid_rate: float,
    floor_rate_pct: float,
    srate_dist: np.ndarray,
    empirical_comp_rates: np.ndarray,
    n_comp: int,
    n_sim: int = 50_000,
    rng: Optional[np.random.Generator] = None,
) -> dict:
    """
    Monte Carlo 낙찰확률 계산 (inpo21c 실증 경쟁사 분포).

    합성 정규분포 대신 inpo21c 실제 관측 투찰률 풀에서 경쟁사를 샘플링.
    실제 클러스터링·비대칭 분포를 그대로 반영해 확률 정확도를 높인다.
    """
    if rng is None:
        rng = np.random.default_rng(42)

    n = len(srate_dist)
    if n_sim != n:
        idx    = rng.integers(0, n, size=n_sim)
        srates = srate_dist[idx]
    else:
        srates = srate_dist[:n_sim]

    effective_floor = floor_rate_pct * srates
    valid       = (our_bid_rate >= effective_floor) & (our_bid_rate <= srates)
    valid_ratio = float(valid.mean())

    if len(empirical_comp_rates) < 5 or n_comp == 0:
        return {"win_prob": round(valid_ratio, 4), "avg_rank": 1.0,
                "valid_ratio": round(valid_ratio, 4)}

    n_comp_eff = min(n_comp, 150)
    comp_bids  = rng.choice(empirical_comp_rates, size=(n_sim, n_comp_eff), replace=True)

    # 복수예가: 유효 범위 내 최고가 낙찰
    comp_valid    = (comp_bids >= floor_rate_pct * srates[:, None]) & (comp_bids <= srates[:, None])
    comp_bids_eff = np.where(comp_valid, comp_bids, -np.inf)
    comp_max      = comp_bids_eff.max(axis=1)

    win_mask = valid & (our_bid_rate >= comp_max)
    win_prob = float(win_mask.mean())

    if valid.any():
        comp_above = (comp_bids[valid] > our_bid_rate) & comp_valid[valid]
        avg_rank   = float((comp_above.sum(axis=1) + 1).mean())
    else:
        avg_rank = float(n_comp_eff + 1)

    return {
        "win_prob":    round(win_prob,    4),
        "avg_rank":    round(avg_rank,    2),
        "valid_ratio": round(valid_ratio, 4),
    }

def monte_carlo_win_prob_gmm(
    our_bid_rate: float,
    floor_rate_pct: float,
    srate_dist: np.ndarray,
    n_competitors: int,
    n_sim: int = 50_000,
    rng: Optional[np.random.Generator] = None,
    gmm_params: Optional[dict] = None,
    agency_bias: float = 0.0,
) -> dict:
    """
    Monte Carlo 낙찰확률 (GMM 3-cluster 경쟁사 분포 사용).

    inpo21c 실측 데이터로 피팅한 GMM에서 경쟁사 투찰률을 샘플링.
    공격형(floor 근처) / 균형형 / 안정형 3그룹이 자연스럽게 반영된다.
    """
    from .competitor_cluster import sample_competitor_rates, get_cluster_params

    if rng is None:
        rng = np.random.default_rng(42)

    params = gmm_params or get_cluster_params()
    n = len(srate_dist)
    if n_sim != n:
        idx    = rng.integers(0, n, size=n_sim)
        srates = srate_dist[idx]
    else:
        srates = srate_dist[:n_sim]

    effective_floor = floor_rate_pct * srates
    valid       = (our_bid_rate >= effective_floor) & (our_bid_rate <= srates)
    valid_ratio = float(valid.mean())

    n_comp_eff = max(1, min(n_competitors, 150))
    # GMM은 ip.bid_rate(= base_ratio = 투찰/기초) 기준으로 피팅됨 → 변환 불필요
    comp_bids = sample_competitor_rates(n_comp_eff, n_sim, rng, params, agency_bias)

    # 복수예가: 유효 범위 내 최고가 낙찰 (예정가격에 가장 근접한 아래 입찰)
    comp_valid    = (comp_bids >= floor_rate_pct * srates[:, None]) & (comp_bids <= srates[:, None])
    comp_bids_eff = np.where(comp_valid, comp_bids, -np.inf)
    comp_max      = comp_bids_eff.max(axis=1)

    win_mask = valid & (our_bid_rate >= comp_max)
    win_prob = float(win_mask.mean())

    if valid.any():
        comp_above = (comp_bids[valid] > our_bid_rate) & comp_valid[valid]
        avg_rank   = float((comp_above.sum(axis=1) + 1).mean())
    else:
        avg_rank = float(n_comp_eff + 1)

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
    n_sim: int = 50_000,
    empirical_comp_rates: Optional[np.ndarray] = None,
    expected_n_comp: int = 0,
    pos_weights: Optional[List[float]] = None,
) -> dict:
    """
    Monte Carlo 기반 4전략 추천.

    전략 (투찰률 = 투찰금액/기초금액):
      공격형(aggressive)          : 낙찰하한율 직상 (최저 유효 투찰, 낙찰확률 최우선)
      균형형(balanced)            : 역대 낙찰 집중 구간 (낙찰하한율 + 0.5%)
      안정형(conservative)        : 앙상블 추천 상단 (리스크 최소)
      경쟁회피형(avoid_competition): 경쟁사 군집 아래 포지션

    Returns:
        strategies        : 4전략별 {rate, win_prob, avg_rank, target, risk, note}
        win_probabilities : 4전략 낙찰확률 요약
        simulation        : 시뮬레이션 메타데이터
    """
    rng = np.random.default_rng(42)
    floor_rate_pct = get_floor_rate(industry_name)

    srate_dist    = simulate_yejung(base_amount, srate_center, srate_std, n_sim, rng, pos_weights)
    floor_abs_p50 = float(np.percentile(srate_dist, 50)) * floor_rate_pct

    # ── 4전략 투찰률 설계: 실효 낙찰하한가 = floor_rate_pct × srate_median 기준
    srate_median = float(np.percentile(srate_dist, 50))
    eff_floor = floor_rate_pct * srate_median  # 실제 낙찰하한가 / 기초금액

    # 공격형: 하한 직상 — 최고 낙찰확률 (마진 최소)
    # 공격형: 실효하한 직상 — 최고 낙찰확률
    rate_aggressive = round(eff_floor + 0.0003, 4)

    # 균형형: 하한+0.15% — 낙찰확률·마진 균형 (통상 50-70% 확률)
    # 균형형: 실효하한+0.15% — 확률·마진 균형
    rate_balanced = round(eff_floor + 0.0015, 4)
    rate_balanced = max(rate_balanced, rate_aggressive + 0.0005)

    # 안정형: 하한+0.30% — 마진 우선 (통상 20-40% 확률)
    # 안정형: 실효하한+0.30% — 마진 우선
    rate_conservative = round(eff_floor + 0.003, 4)
    rate_conservative = max(rate_conservative, rate_balanced + 0.0005)

    # 회피형: 경쟁사 군집(하위 25%) 아래 포지션
    if competitor_means:
        comp_p25 = float(np.percentile(competitor_means, 25))
        rate_avoid = max(round(comp_p25 - 0.0005, 4), rate_aggressive)
    else:
        rate_avoid = rate_balanced
    rate_avoid = round(rate_avoid, 4)

    def _wp(rate: float) -> dict:
        if empirical_comp_rates is not None and expected_n_comp > 0:
            return monte_carlo_win_prob_empirical(
                rate, floor_rate_pct, srate_dist,
                empirical_comp_rates, expected_n_comp, n_sim, rng,
            )
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
            "eff_floor":      round(eff_floor, 4),
            "srate_median":   round(srate_median, 4),
            "empirical_used": empirical_comp_rates is not None and expected_n_comp > 0,
            "srate_p10":      round(float(np.percentile(srate_dist, 10)), 4),
            "srate_p25":      round(float(np.percentile(srate_dist, 25)), 4),
            "srate_median":   round(float(np.percentile(srate_dist, 50)), 4),
            "srate_p75":      round(float(np.percentile(srate_dist, 75)), 4),
            "srate_p90":      round(float(np.percentile(srate_dist, 90)), 4),
            "floor_abs_p50":  round(floor_abs_p50, 4),
        },
    }


def simulate_yejung_from_real(
    yega_values: List[int],
    base_amount: int,
) -> np.ndarray:
    """
    실측 15개 예비가격으로 C(15,4)=1,365 정확 사정률 분포 계산.
    Monte Carlo 근사가 아닌 전수 열거 — 실측 입력 시 최대 정확도.

    Args:
        yega_values : 실제 15개 예비가격 금액 (원)
        base_amount : 기초금액 (원)

    Returns:
        shape (1365,) 사정률 배열 — 각 C(15,4) 조합의 평균 / 기초금액
    """
    vals = np.array(yega_values, dtype=np.float64)
    n = len(vals)
    avgs = np.array([vals[list(c)].mean() for c in combinations(range(n), 4)])
    return avgs / base_amount


def scan_zones_from_dist(
    srate_dist: np.ndarray,
    floor_rate_pct: float,
    base_amount: int,
    inpo_rates: Optional[np.ndarray] = None,
    expected_n_comp: int = 0,
    scan_start: Optional[float] = None,
    scan_end: Optional[float] = None,
    scan_step: float = 0.0005,
    n_sim: int = 10_000,
    gmm_params: Optional[dict] = None,
) -> tuple[list[dict], list[dict]]:
    """
    사정률 분포로 투찰구간별 낙찰확률 스캔 (기초금액 대비 투찰률 기준).

    우선순위: GMM > inpo21c 실증(단위변환 필수) > valid_ratio 하한 추정

    scan_start/end를 지정하지 않으면 srate_dist에서 동적 산출:
      start = floor_rate_pct × p10(srate) × 0.995
      end   = p95(srate) × 1.005

    Returns:
        (all_zones, top10)
    """
    rng = np.random.default_rng(42)
    srate_p10  = float(np.percentile(srate_dist, 10))
    srate_p95  = float(np.percentile(srate_dist, 95))
    srate_med  = float(np.median(srate_dist))
    eff_floor_abs = floor_rate_pct * srate_med

    if scan_start is None:
        scan_start = round(floor_rate_pct * srate_p10 * 0.995, 3)
    if scan_end is None:
        scan_end = round(srate_p95 * 1.005, 3)

    # 스텝 수가 너무 많으면 step 조정
    n_steps = int((scan_end - scan_start) / scan_step) + 2
    if n_steps > 200:
        scan_step = round((scan_end - scan_start) / 150, 4)

    # inpo_rates: get_inpo_raw_rates() 반환값 — 이미 base_ratio(투찰/기초) 단위
    inpo_base: Optional[np.ndarray] = None
    if inpo_rates is not None and len(inpo_rates) >= 5:
        inpo_base = np.asarray(inpo_rates, dtype=np.float64)

    zones: list[dict] = []
    rate = scan_start
    while rate <= scan_end + 1e-9:
        rate_r = round(rate, 4)
        floor_ok = rate_r >= eff_floor_abs

        if gmm_params is not None and expected_n_comp > 0:
            wp = monte_carlo_win_prob_gmm(
                rate_r, floor_rate_pct, srate_dist, expected_n_comp, n_sim, rng, gmm_params,
            )
        elif inpo_base is not None and expected_n_comp > 0:
            wp = monte_carlo_win_prob_empirical(
                rate_r, floor_rate_pct, srate_dist, inpo_base, expected_n_comp, n_sim, rng,
            )
        else:
            # 경쟁사 데이터 없음 — valid_ratio를 상한으로 사용 (불확실 구간 표시용)
            n = len(srate_dist)
            idx    = rng.integers(0, n, size=n_sim)
            srates = srate_dist[idx]
            eff_fl = floor_rate_pct * srates
            valid  = (rate_r >= eff_fl) & (rate_r <= srates)
            vr     = float(valid.mean())
            # 경쟁사 없으면 win_prob는 매우 불확실 — 0.5를 최대치로 스케일
            wp = {"win_prob": round(vr * 0.5, 4), "avg_rank": 1.0, "valid_ratio": round(vr, 4)}

        zones.append({
            "rate":        rate_r,
            "amount":      int(round(rate_r * base_amount)),
            "win_prob":    wp["win_prob"],
            "valid_ratio": wp["valid_ratio"],
            "floor_ok":    floor_ok,
        })
        rate += scan_step

    valid_zones = [z for z in zones if z["floor_ok"]]
    top10 = sorted(valid_zones, key=lambda z: z["win_prob"], reverse=True)[:10]
    return zones, top10


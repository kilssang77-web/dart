"""
프리즘 2.0 — 구간별 낙찰확률 스캔 (0.860~0.930, SCAN_STEP=0.0005, 140구간)
inpo21c 실증 분포 기반 Monte Carlo win_prob 계산, 상위 10개 추출.

★ 용어 정의 (이 모듈의 "rate" 의미)
  - rate (zones 내부)   : bid_rate = 투찰금액 / 기초금액  (범위: 0.860~0.930)
  - srate_center/std    : assessment_rate = 예정가격 / 기초금액 (simulation 입력값)
  - win_prob            : P(우리 bid_rate ≤ assessment_rate AND bid_rate ≥ 유효 경쟁사 최고)
"""
import time
import numpy as np
from typing import Optional
from sqlalchemy.orm import Session

_prism_cache: dict = {}
_PRISM_TTL = 3600  # 1시간 캐시

from .simulation import simulate_yejung, monte_carlo_win_prob_empirical, monte_carlo_win_prob
from .a_value import calc_floor_rate
from .assessment import load_srate_stats, predict_srate
from .rank_model import get_inpo_raw_rates
from .yega import load_inpo21c_yega_stats

SCAN_START = 0.860   # base_ratio(투찰/기초) 유효 구간 — srate_center≈0.885 기준 [floor*srate, srate] 포함
SCAN_END   = 0.930
SCAN_STEP  = 0.0005  # 0.001→0.0005: 140구간으로 2배 정밀도 (n_sim 절반으로 속도 보전)
TOP_N      = 10


def scan_prism_zones(
    base_amount: int,
    industry_name: str,
    agency_id: int,
    industry_id: int,
    db: Session,
    n_sim: int = 10_000,
) -> tuple[list[dict], list[dict]]:
    """
    0.860~0.930 구간을 0.001 단위로 스캔, 낙찰확률 계산.

    각 구간: {rate, win_prob, floor_ok, amount, rank_est}
    floor 미달 구간은 top10에서 제외.

    Returns:
        (all_zones, top10): 전체 71구간 목록(0.860~0.930 포함), 낙찰확률 상위 10개
    """
    cache_key = (base_amount, industry_name, agency_id, industry_id)
    now = time.monotonic()
    cached = _prism_cache.get(cache_key)
    if cached is not None:
        result, ts = cached
        if now - ts < _PRISM_TTL:
            return result

    result = _compute_prism_zones(base_amount, industry_name, agency_id, industry_id, db, n_sim)
    _prism_cache[cache_key] = (result, now)
    return result


def _compute_prism_zones(
    base_amount: int,
    industry_name: str,
    agency_id: int,
    industry_id: int,
    db: Session,
    n_sim: int = 10_000,
) -> tuple[list[dict], list[dict]]:
    rng = np.random.default_rng(42)
    floor_rate_pct = calc_floor_rate(industry_name)

    features = load_srate_stats(db, agency_id, industry_id, 0, base_amount)
    ep = predict_srate(features, base_amount)
    srate_center = ep["srate_range"]["center"]
    srate_std = (
        features.get("agency_srate_std")
        or features.get("global_srate_std")
        or 0.012
    )

    # 데이터 품질 레벨 (agency/industry/region/global)
    _dql = features.get("data_quality_level", "global")

    # 예상 경쟁사 수 (bid_results 실측 기반, 없으면 전국 평균, 최종 fallback=8)
    expected_n = int(
        features.get("expected_competitor_count")
        or features.get("global_comp_count")
        or 8
    )

    # inpo21c 위치 가중치 로드
    _yega_stats  = load_inpo21c_yega_stats(db, agency_id) if agency_id else {}
    _pos_weights = _yega_stats.get("pos_weights")

    # 사정율 분포 시뮬레이션 (1회만 — 모든 구간 공유)
    srate_dist = simulate_yejung(base_amount, srate_center, srate_std, n_sim, rng, _pos_weights)

    # inpo21c 실증 분포
    inpo_rates: Optional[np.ndarray] = None
    try:
        inpo_rates = get_inpo_raw_rates(db, expected_n)
    except Exception:
        pass

    # 사정율 샘플링 (n_sim 개)
    idx = rng.integers(0, len(srate_dist), size=n_sim)
    srates = srate_dist[idx]  # (n_sim,)

    # 낙찰하한율 기반 실효하한 (중앙값 기준)
    srate_median = float(np.percentile(srate_dist, 50))
    eff_floor_abs = floor_rate_pct * srate_median

    # 경쟁사 투찰률 행렬 & 유효 최댓값 사전 계산
    # 복수예가: 예정가격 이하 최고 투찰자 낙찰 → 유효 경쟁사 최고 rate보다 높아야 승리
    n_comp_eff = min(expected_n, 20)
    if inpo_rates is not None and len(inpo_rates) >= 5:
        comp_bids = rng.choice(inpo_rates, size=(n_sim, n_comp_eff), replace=True)
        # 경쟁사 유효성: floor*srate <= comp <= srate
        eff_floor_per_sim = floor_rate_pct * srates  # (n_sim,)
        comp_valid = (
            (comp_bids >= eff_floor_per_sim[:, None])
            & (comp_bids <= srates[:, None])
        )
        # 유효 경쟁사 최고 rate (-inf: 유효 경쟁사 없음 → 자동 낙찰)
        comp_bids_eff = np.where(comp_valid, comp_bids, np.NINF)
        comp_max = comp_bids_eff.max(axis=1)  # (n_sim,)
    else:
        comp_bids = None
        comp_valid = None
        comp_max = np.full(n_sim, np.NINF)  # 경쟁사 없으면 항상 최고
        eff_floor_per_sim = floor_rate_pct * srates

    # 동적 스캔 범위 — srate_dist 분포 기반 (복수예가/고정방식 자동 대응)
    srate_p5  = float(np.percentile(srate_dist, 5))
    srate_p97 = float(np.percentile(srate_dist, 97))
    dyn_start = round(max(0.840, floor_rate_pct * srate_p5 * 0.997), 3)
    dyn_end   = round(min(1.010, srate_p97 * 1.003), 3)
    n_steps   = int((dyn_end - dyn_start) / SCAN_STEP) + 1
    dyn_step  = SCAN_STEP if n_steps <= 300 else round((dyn_end - dyn_start) / 200, 4)
    rates = np.round(np.arange(dyn_start, dyn_end + dyn_step / 2, dyn_step), 4)
    all_zones: list[dict] = []

    for rate_raw in rates:
        rate = round(float(rate_raw), 4)
        floor_ok = rate >= eff_floor_abs

        # 투찰 유효성: floor*srate <= rate <= srate
        valid = (rate >= eff_floor_per_sim) & (rate <= srates)  # (n_sim,)

        if floor_ok:
            if comp_bids is not None:
                # 복수예가: 유효 경쟁사 최고 rate 이상이어야 승리
                win_mask = valid & (rate >= comp_max)
                win_prob = round(float(win_mask.mean()), 4)
            else:
                win_prob = round(float(valid.mean()), 4)
        else:
            win_prob = 0.0

        # 예상 순위 (유효 시뮬레이션에서 우리보다 높은 유효 경쟁사 수 + 1)
        if comp_bids is not None and valid.any():
            comp_higher = (comp_bids[valid] > rate) & comp_valid[valid]
            avg_rank = round(float((comp_higher.sum(axis=1) + 1).mean()), 2)
        else:
            avg_rank = 1.0

        all_zones.append({
            "rate":         rate,
            "win_prob":     win_prob,
            "floor_ok":     floor_ok,
            "amount":       round(base_amount * rate),
            "rank_est":     avg_rank,
            "data_quality": _dql,
        })

    # 상위 10개: floor_ok=True & win_prob 내림차순
    valid_zones = [z for z in all_zones if z["floor_ok"]]
    top10 = sorted(valid_zones, key=lambda x: x["win_prob"], reverse=True)[:TOP_N]

    return all_zones, top10

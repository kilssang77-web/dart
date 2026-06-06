"""
프리즘 2.0 — 구간별 낙찰확률 스캔 (0.860~0.930 × 0.001 = 70구간)
inpo21c 실증 분포 기반 Monte Carlo win_prob 계산, 상위 10개 추출.
"""
import numpy as np
from typing import Optional
from sqlalchemy.orm import Session

from .simulation import simulate_yejung, monte_carlo_win_prob_empirical, monte_carlo_win_prob
from .a_value import calc_floor_rate
from .assessment import load_srate_stats, predict_srate
from .rank_model import get_inpo_raw_rates
from .yega import load_inpo21c_yega_stats

SCAN_START = 0.860
SCAN_END   = 0.930
SCAN_STEP  = 0.001
TOP_N      = 10


def scan_prism_zones(
    base_amount: int,
    industry_name: str,
    agency_id: int,
    industry_id: int,
    db: Session,
    n_sim: int = 20_000,
) -> tuple[list[dict], list[dict]]:
    """
    0.860~0.930 구간을 0.001 단위로 스캔, 낙찰확률 계산.

    각 구간: {rate, win_prob, floor_ok, amount, rank_est}
    floor 미달 구간은 top10에서 제외.

    Returns:
        (all_zones, top10): 전체 71구간 목록(0.860~0.930 포함), 낙찰확률 상위 10개
    """
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

    # 예상 경쟁사 수
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

    # 경쟁사 투찰률 행렬 & 유효 최솟값 사전 계산
    n_comp_eff = min(expected_n, 20)
    if inpo_rates is not None and len(inpo_rates) >= 5:
        comp_bids = rng.choice(inpo_rates, size=(n_sim, n_comp_eff), replace=True)
        # 경쟁사 유효성: floor*srate <= comp <= srate
        eff_floor_per_sim = floor_rate_pct * srates  # (n_sim,)
        comp_valid = (
            (comp_bids >= eff_floor_per_sim[:, None])
            & (comp_bids <= srates[:, None])
        )
        comp_bids_eff = np.where(comp_valid, comp_bids, np.inf)
        comp_min = comp_bids_eff.min(axis=1)  # (n_sim,)
    else:
        comp_bids = None
        comp_valid = None
        comp_min = srates  # 경쟁사 없으면 사정율이 상한
        eff_floor_per_sim = floor_rate_pct * srates

    # 70개 구간 스캔
    rates = np.round(np.arange(SCAN_START, SCAN_END + SCAN_STEP / 2, SCAN_STEP), 3)
    all_zones: list[dict] = []

    for rate_raw in rates:
        rate = round(float(rate_raw), 3)
        floor_ok = rate >= eff_floor_abs

        # 투찰 유효성: floor*srate <= rate <= srate
        valid = (rate >= eff_floor_per_sim) & (rate <= srates)  # (n_sim,)

        if floor_ok:
            if comp_bids is not None:
                win_mask = valid & (rate <= comp_min)
                win_prob = round(float(win_mask.mean()), 4)
            else:
                win_prob = round(float(valid.mean()), 4)
        else:
            win_prob = 0.0

        # 예상 순위 (유효 시뮬레이션에서 우리보다 낮은 유효 경쟁사 수 + 1)
        if comp_bids is not None and valid.any():
            comp_lower = (comp_bids[valid] < rate) & comp_valid[valid]
            avg_rank = round(float((comp_lower.sum(axis=1) + 1).mean()), 2)
        else:
            avg_rank = 1.0

        all_zones.append({
            "rate":     rate,
            "win_prob": win_prob,
            "floor_ok": floor_ok,
            "amount":   round(base_amount * rate),
            "rank_est": avg_rank,
        })

    # 상위 10개: floor_ok=True & win_prob 내림차순
    valid_zones = [z for z in all_zones if z["floor_ok"]]
    top10 = sorted(valid_zones, key=lambda x: x["win_prob"], reverse=True)[:TOP_N]

    return all_zones, top10

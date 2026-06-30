"""
경쟁사 GMM 3-클러스터 모델 — 입찰 성향 기반 군집화.

나라장터 입찰자들은 투찰률 분포상 크게 3그룹으로 분류:
  · Group 0 (공격형): 0.870~0.888  — floor 근처, 낙찰하한선 공략
  · Group 1 (균형형): 0.888~0.905  — 평균 시장 투찰률
  · Group 2 (안정형): 0.905~0.925  — 높은 투찰, 실적 위주

사용처: monte_carlo 시뮬레이션에서 더 현실적인 경쟁사 분포 샘플링.
"""
import logging
import numpy as np

logger = logging.getLogger(__name__)

# ── 사전 정의 GMM 파라미터 (데이터 기반 초기값, fit 후 업데이트)
_DEFAULT_PARAMS = {
    "weights": [0.35, 0.42, 0.23],
    "means":   [0.8790, 0.8940, 0.9120],
    "stds":    [0.0045, 0.0038, 0.0042],
}

_fitted_params: dict = dict(_DEFAULT_PARAMS)


def fit_competitor_clusters(rates: np.ndarray) -> dict:
    """
    실측 투찰률 배열로 GMM 3-클러스터 피팅.

    Args:
        rates: 투찰률 배열 (예: inpo21c_participants.bid_rate), float array
    Returns:
        weights, means, stds dict
    """
    rates = np.asarray(rates, dtype=float)
    rates = rates[(rates >= 0.83) & (rates <= 0.98)]
    if len(rates) < 30:
        logger.warning("GMM 피팅 데이터 부족 — 기본값 사용")
        return dict(_DEFAULT_PARAMS)

    try:
        from sklearn.mixture import GaussianMixture
        gm = GaussianMixture(
            n_components=3,
            covariance_type="full",
            max_iter=200,
            random_state=42,
            init_params="kmeans",
        )
        gm.fit(rates.reshape(-1, 1))
        order = np.argsort(gm.means_.ravel())
        params = {
            "weights": [float(gm.weights_[i]) for i in order],
            "means":   [float(gm.means_[i, 0]) for i in order],
            "stds":    [float(np.sqrt(gm.covariances_[i, 0, 0])) for i in order],
        }
        global _fitted_params
        _fitted_params = params
        logger.info(f"GMM 피팅 완료: weights={[round(w,3) for w in params['weights']]} "
                    f"means={[round(m,4) for m in params['means']]}")
        return params
    except Exception as e:
        logger.warning(f"GMM 피팅 실패: {e} — 기본값 사용")
        return dict(_DEFAULT_PARAMS)


def get_cluster_params() -> dict:
    """현재 GMM 파라미터 반환."""
    return dict(_fitted_params)


def sample_competitor_rates(
    n_competitors: int,
    n_sim: int,
    rng: np.random.Generator,
    params: dict | None = None,
    agency_bias: float = 0.0,
) -> np.ndarray:
    """
    GMM에서 경쟁사 투찰률 샘플링.

    Args:
        n_competitors: 경쟁사 수 (per simulation)
        n_sim: 시뮬레이션 반복 수
        rng: numpy RNG
        params: GMM 파라미터 (None이면 피팅된 _fitted_params 사용)
        agency_bias: 기관별 사정률 편향 (기본 0.0)

    Returns:
        shape (n_sim, n_competitors) 투찰률 배열
    """
    p = params or _fitted_params
    weights = np.array(p["weights"], dtype=float)
    weights /= weights.sum()
    means = np.array(p["means"], dtype=float) + agency_bias
    stds  = np.array(p["stds"], dtype=float)

    n_comps = len(weights)
    total = n_sim * n_competitors

    # 클러스터 배정 (벡터화)
    cluster_ids = rng.choice(n_comps, size=total, p=weights)
    samples = means[cluster_ids] + stds[cluster_ids] * rng.standard_normal(size=total)
    samples = np.clip(samples, 0.840, 0.980)
    return samples.reshape(n_sim, n_competitors)


def fit_from_db(db) -> dict:
    """
    GMM 피팅 — inpo21c_participants + bid_results 통합 소스.

    [Task #17] bid_results도 사용해 데이터 범위 확대:
      1. inpo21c_participants (복수예가 건, 최대 30K)
      2. competitor_stats avg_bid_rate (pre-computed 연간 평균, 최대 20K)
    합산 후 GMM 3-클러스터 피팅. 결과 파일 캐시.
    """
    import os, json
    from pathlib import Path

    cache_path = Path(os.getenv("ML_MODELS_PATH", "/app/ml_models")) / "gmm_params.json"

    try:
        from sqlalchemy import text

        # inpo21c_participants 전참여자 실증 투찰률 (winner + non-winner 모두)
        # bid_results는 93% winner-only → GMM 편향 유발로 제외
        inpo_rows = db.execute(text("""
            SELECT ip.bid_rate::float
            FROM inpo21c_participants ip
            JOIN inpo21c_bids ib ON ib.inpo21c_bid_id = ip.inpo21c_bid_id
            WHERE ip.bid_rate BETWEEN 0.83 AND 0.98
              AND ib.yega_ratio BETWEEN 87 AND 105
              AND ABS(ib.yega_ratio - 90.91) > 1.0
            ORDER BY random()
            LIMIT 50000
        """)).fetchall()

        if len(inpo_rows) < 30:
            if cache_path.exists():
                with open(cache_path) as f:
                    return json.load(f)
            return dict(_DEFAULT_PARAMS)

        rates  = np.array([r[0] for r in inpo_rows], dtype=float)
        params = fit_competitor_clusters(rates)
        logger.info("GMM 피팅 소스: inpo21c=%d건", len(inpo_rows))

        with open(cache_path, "w") as f:
            json.dump(params, f)

        return params
    except Exception as e:
        logger.warning(f"DB GMM 피팅 실패: {e}")
        if cache_path.exists():
            try:
                with open(cache_path) as f:
                    return json.load(f)
            except Exception:
                pass
        return dict(_DEFAULT_PARAMS)

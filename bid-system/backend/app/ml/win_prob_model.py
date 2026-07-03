"""
실증 낙찰확률 모델 v2 — inpo21c_participants 기반 LightGBM 이진 분류.

v2 개선사항:
  · bid_z_score: 입찰 내 상대 위치 → 가장 강력한 예측자
  · inv_n_comp : 1/n_competitors → 경쟁 강도를 직접 인코딩, n_comp 불변 문제 해결
  · META_PATH  : 학습 통계 저장 → inference 시 z_score 동일 스케일 적용

Features:
  bid_rate      : 투찰금액 / 예정금액
  bid_z_score   : (bid_rate - 입찰평균) / 입찰표준편차  ← 경쟁 내 상대 위치
  inv_n_comp    : 1 / n_competitors  ← 경쟁 강도 역수 (많을수록 낮아짐)
  srate         : 사정율 = 예정금액 / 기초금액
  bid_vs_floor  : bid_rate - (낙찰하한율 × srate)
"""
import json
import logging
import os
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

MODEL_DIR    = Path(os.getenv("ML_MODELS_PATH", "/app/ml_models"))
MODEL_DIR.mkdir(parents=True, exist_ok=True)
MODEL_PATH    = MODEL_DIR / "win_prob_lgbm.pkl"
IMPUTER_PATH  = MODEL_DIR / "win_prob_imputer.pkl"
META_PATH     = MODEL_DIR / "win_prob_meta.json"
RESULT_PATH   = MODEL_DIR / "win_prob_result.json"   # 학습 결과 영구 저장
CALIB_PATH    = MODEL_DIR / "win_prob_calibrator.pkl" # Isotonic 캘리브레이터

FEATURE_COLS = [
    "bid_rate",
    "inv_n_comp",     # 1/n_competitors → 경쟁 강도 역수
    "srate",
    "bid_vs_floor",
    "win_rank_est",   # GMM CDF at bid_rate ≈ 경쟁자 대비 상위 비율 (학습/추론 일관)
]

_DEFAULT_FLOOR = 0.8745
_DEFAULT_META  = {
    "median_n_comp": 20.0,
    "gmm_weights":   [0.35, 0.42, 0.23],
    "gmm_means":     [0.8790, 0.8940, 0.9120],
    "gmm_stds":      [0.0045, 0.0038, 0.0042],
}


def _load_meta() -> dict:
    if META_PATH.exists():
        try:
            with open(META_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return dict(_DEFAULT_META)


def train(db, floor_rate: float = _DEFAULT_FLOOR) -> dict:
    """
    inpo21c 복수예가 데이터로 낙찰확률 모델 v2 학습.

    변경점:
      · per-bid avg/std → bid_z_score 계산
      · inv_n_comp 피처 추가
      · scale_pos_weight^0.5 완화 (과도한 positive 쏠림 방지)
      · early_stopping=100, n_estimators=2000 (충분한 학습 보장)

    Returns:
        dict: success, n_train, n_pos, auc, feature_importance, meta
    """
    try:
        import lightgbm as lgb
        import joblib
        import pandas as pd
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import roc_auc_score, average_precision_score
        from sklearn.impute import SimpleImputer
        from sqlalchemy import text
    except ImportError as e:
        return {"success": False, "error": str(e)}

    rows = db.execute(text("""
        SELECT
            ip.bid_rate::float                                      AS bid_rate,
            cnt.n_competitors,
            ib.yega_ratio / 100.0                                  AS srate,
            ip.is_winner::int                                      AS won,
            cnt.avg_bid_rate,
            cnt.std_bid_rate
        FROM inpo21c_participants ip
        JOIN inpo21c_bids ib ON ib.inpo21c_bid_id = ip.inpo21c_bid_id
        JOIN (
            SELECT
                inpo21c_bid_id,
                COUNT(*)                AS n_competitors,
                AVG(bid_rate::float)    AS avg_bid_rate,
                STDDEV(bid_rate::float) AS std_bid_rate
            FROM inpo21c_participants
            WHERE bid_rate BETWEEN 0.80 AND 1.05
              AND company_name != '유찰'
            GROUP BY inpo21c_bid_id
            HAVING COUNT(*) BETWEEN 3 AND 100
        ) cnt ON cnt.inpo21c_bid_id = ip.inpo21c_bid_id
        WHERE ip.bid_rate BETWEEN 0.80 AND 1.05
          AND ip.company_name != '유찰'
          AND ib.yega_ratio BETWEEN 87 AND 105
          AND ABS(ib.yega_ratio - 90.91) > 1.0
    """)).fetchall()

    if len(rows) < 200:
        return {"success": False, "error": f"데이터 부족: {len(rows)}건 (최소 200건)"}

    df = _build_features(rows, floor_rate)

    n_pos = int(df["won"].sum())
    n_neg = int(len(df) - n_pos)
    if n_pos < 50:
        return {"success": False, "error": f"낙찰 샘플 부족: {n_pos}건"}

    # GMM 피팅 후 win_rank_est를 올바른 값으로 업데이트
    from .competitor_cluster import fit_competitor_clusters
    gmm = fit_competitor_clusters(df["bid_rate"].values)
    meta = {
        "median_n_comp": float(np.median(df["n_competitors"])),
        "gmm_weights":   gmm["weights"],
        "gmm_means":     gmm["means"],
        "gmm_stds":      gmm["stds"],
    }
    with open(META_PATH, "w") as f:
        json.dump(meta, f)

    # win_rank_est: GMM CDF 배치 계산 (학습 분포와 추론 분포 일치)
    df["win_rank_est"] = df["bid_rate"].apply(lambda r: _gmm_cdf(r, meta))

    X = df[FEATURE_COLS].values
    y = df["won"].values

    imputer = SimpleImputer(strategy="median")
    X_imp = imputer.fit_transform(X)
    X_tr, X_val, y_tr, y_val = train_test_split(
        X_imp, y, test_size=0.2, random_state=42, stratify=y
    )

    # scale_pos_weight 제곱근: 과도한 positive 집중 방지
    spw = (n_neg / max(n_pos, 1)) ** 0.5

    model = lgb.LGBMClassifier(
        objective="binary",
        n_estimators=2000,
        num_leaves=15,
        learning_rate=0.01,
        min_child_samples=20,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=spw,
        verbosity=-1,
        random_state=42,
    )
    model.fit(
        X_tr, y_tr,
        eval_set=[(X_val, y_val)],
        callbacks=[
            lgb.early_stopping(100, verbose=False),
            lgb.log_evaluation(-1),
        ],
    )

    y_pred = model.predict_proba(X_val)[:, 1]
    auc = float(roc_auc_score(y_val, y_pred))
    pr_auc = float(average_precision_score(y_val, y_pred))

    # Lift@K: 상위 K% 예측에서 실제 낙찰률 / 전체 낙찰률
    k_pct = 0.10  # 상위 10%
    k = max(1, int(len(y_val) * k_pct))
    top_k_idx = np.argsort(y_pred)[::-1][:k]
    lift_at_10 = float(y_val[top_k_idx].mean() / (y_val.mean() + 1e-9))

    # ── Isotonic Regression 캘리브레이션 ──────────────────────────────────
    # raw LightGBM probability → 실제 낙찰률로 보정 (ECE 개선 목표)
    from sklearn.isotonic import IsotonicRegression
    calibrator = IsotonicRegression(out_of_bounds="clip")
    calibrator.fit(y_pred, y_val)

    # 캘리브레이션 전후 ECE 비교
    def _ece(probs, labels, n_bins=10):
        bins = np.linspace(0, 1, n_bins + 1)
        ece_val = 0.0
        for i in range(n_bins):
            mask = (probs >= bins[i]) & (probs < bins[i + 1])
            if mask.sum() == 0:
                continue
            bin_acc  = labels[mask].mean()
            bin_conf = probs[mask].mean()
            ece_val += mask.sum() / len(probs) * abs(bin_acc - bin_conf)
        return float(ece_val)

    ece_before = _ece(y_pred, y_val)
    y_calib = calibrator.predict(y_pred)
    ece_after  = _ece(y_calib, y_val)

    joblib.dump(model, MODEL_PATH)
    joblib.dump(imputer, IMPUTER_PATH)
    joblib.dump(calibrator, CALIB_PATH)

    fi = dict(zip(FEATURE_COLS, model.feature_importances_.tolist()))

    import time as _time
    result = {
        "success":            True,
        "n_train":            len(df),
        "n_pos":              n_pos,
        "n_neg":              n_neg,
        "auc":                round(auc, 4),
        "pr_auc":             round(pr_auc, 4),
        "lift_at_10":         round(lift_at_10, 2),
        "best_iteration":     model.best_iteration_,
        "feature_importance": fi,
        "trained_at":         _time.time(),
        "meta":               meta,
        "ece_before":         round(ece_before, 4),
        "ece_after":          round(ece_after, 4),
    }
    # 학습 결과 영구 저장 → model_info() 에서 조회 가능
    with open(RESULT_PATH, "w") as f:
        json.dump(result, f)

    logger.info(
        f"win_prob_model v3 학습 완료: n={len(df)}, pos={n_pos}, neg={n_neg}, "
        f"ROC-AUC={auc:.4f}, PR-AUC={pr_auc:.4f}, Lift@10%={lift_at_10:.2f}x, "
        f"best_iter={model.best_iteration_}"
    )
    return result


def _load_calibrator():
    """캘리브레이터 로드 (없으면 None 반환)."""
    if not CALIB_PATH.exists():
        return None
    try:
        import joblib
        return joblib.load(CALIB_PATH)
    except Exception:
        return None


def predict(
    bid_rate:      float,
    srate:         float,
    n_competitors: int,
    floor_rate:    float = _DEFAULT_FLOOR,
) -> float:
    """
    단일 투찰율에 대한 낙찰확률 반환 (캘리브레이션 적용).
    모델 미존재 시 -1.0 (호출측에서 fallback 처리).
    """
    if not MODEL_PATH.exists() or not IMPUTER_PATH.exists():
        return -1.0
    try:
        import joblib
        model      = joblib.load(MODEL_PATH)
        imputer    = joblib.load(IMPUTER_PATH)
        calibrator = _load_calibrator()
        meta       = _load_meta()
        row   = _make_row(bid_rate, n_competitors, srate, floor_rate, meta)
        X     = np.array([row], dtype=float)
        X_imp = imputer.transform(X)
        prob  = float(model.predict_proba(X_imp)[0, 1])
        if calibrator is not None:
            prob = float(calibrator.predict([prob])[0])
        return round(prob, 6)
    except Exception as e:
        logger.warning(f"win_prob 예측 실패: {e}")
        return -1.0


def predict_curve(
    srate:         float,
    n_competitors: int,
    floor_rate:    float = _DEFAULT_FLOOR,
    n_points:      int   = 60,
) -> list[dict]:
    """
    bid_rate 구간별 낙찰확률 곡선 반환.
    TenderDecisionPage 승률 곡선 시각화에 사용.
    """
    if not MODEL_PATH.exists() or not IMPUTER_PATH.exists():
        return []
    try:
        import joblib
        model      = joblib.load(MODEL_PATH)
        imputer    = joblib.load(IMPUTER_PATH)
        calibrator = _load_calibrator()
        meta       = _load_meta()

        lo = max(floor_rate * 0.97, 0.83)
        hi = min(floor_rate * 1.08, 0.98)
        rates = np.linspace(lo, hi, n_points)
        rows  = [_make_row(r, n_competitors, srate, floor_rate, meta) for r in rates]
        X     = np.array(rows, dtype=float)
        X_imp = imputer.transform(X)
        probs = model.predict_proba(X_imp)[:, 1]
        if calibrator is not None:
            probs = calibrator.predict(probs)

        return [
            {"bid_rate": round(float(r), 5), "win_prob": round(float(p), 5)}
            for r, p in zip(rates, probs)
        ]
    except Exception as e:
        logger.warning(f"win_prob 곡선 생성 실패: {e}")
        return []


def model_info() -> dict:
    """학습된 모델 메타 정보 (RESULT_PATH 우선 조회)."""
    if not MODEL_PATH.exists():
        return {"trained": False, "model_path": str(MODEL_PATH)}
    try:
        # 학습 결과 파일이 있으면 그 정보를 우선 사용
        if RESULT_PATH.exists():
            with open(RESULT_PATH) as f:
                result = json.load(f)
            return {
                "trained":            True,
                "best_iteration":     result.get("best_iteration"),
                "n_train":            result.get("n_train"),
                "n_pos":              result.get("n_pos"),
                "auc":                result.get("auc"),
                "pr_auc":             result.get("pr_auc"),
                "lift_at_10":         result.get("lift_at_10"),
                "feature_importance": result.get("feature_importance"),
                "feature_cols":       FEATURE_COLS,
                "model_path":         str(MODEL_PATH),
                "trained_at":         result.get("trained_at"),
                "ece_before":         result.get("ece_before"),
                "ece_after":          result.get("ece_after"),
                "calibrated":         CALIB_PATH.exists(),
            }
        # fallback: 모델 파일 직접 로드
        import joblib
        model    = joblib.load(MODEL_PATH)
        stat     = MODEL_PATH.stat()
        return {
            "trained":        True,
            "best_iteration": getattr(model, "best_iteration_", None),
            "n_estimators":   getattr(model, "n_estimators_", None),
            "model_path":     str(MODEL_PATH),
            "trained_at":     stat.st_mtime,
            "feature_cols":   FEATURE_COLS,
        }
    except Exception:
        return {"trained": False, "model_path": str(MODEL_PATH)}


# ── 내부 헬퍼 ────────────────────────────────────────────────

def _gmm_cdf(bid_rate: float, meta: dict) -> float:
    """
    GMM CDF at bid_rate = P(competitor < bid_rate).
    학습/추론 모두 동일한 GMM 분포 사용 → 분포 불일치 없음.
    """
    from scipy.stats import norm as _norm
    weights = meta.get("gmm_weights", _DEFAULT_META["gmm_weights"])
    means   = meta.get("gmm_means",   _DEFAULT_META["gmm_means"])
    stds    = meta.get("gmm_stds",    _DEFAULT_META["gmm_stds"])
    cdf = sum(
        w * float(_norm.cdf(bid_rate, loc=m, scale=s))
        for w, m, s in zip(weights, means, stds)
    )
    return float(np.clip(cdf, 0.0, 1.0))


def _make_row(
    bid_rate:      float,
    n_competitors: int,
    srate:         float,
    floor_rate:    float,
    meta:          dict,
) -> list[float]:
    inv_n        = 1.0 / max(n_competitors, 1)
    win_rank_est = _gmm_cdf(bid_rate, meta)   # P(경쟁자 < my_bid) — 높을수록 상위
    return [
        bid_rate,
        inv_n,
        srate,
        bid_rate - (floor_rate * srate),
        win_rank_est,
    ]


def _build_features(rows, floor_rate: float):
    import pandas as pd
    df = pd.DataFrame(
        rows,
        columns=["bid_rate", "n_competitors", "srate", "won", "avg_bid_rate", "std_bid_rate"],
    )
    for col in ["bid_rate", "n_competitors", "srate", "won", "avg_bid_rate", "std_bid_rate"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["bid_rate", "n_competitors", "won"])

    df["inv_n_comp"]   = 1.0 / df["n_competitors"].clip(lower=1)
    df["bid_vs_floor"] = df["bid_rate"] - (floor_rate * df["srate"].fillna(0.90))
    # win_rank_est는 GMM 피팅 후 batch 계산 (train()에서 호출 시점에 GMM 확정)
    df["win_rank_est"] = 0.5   # 초기값; train()에서 GMM 피팅 후 덮어씀

    return df

"""
로컬 ML 추천 엔진 — 상용 AI 없이 XGBoost + LightGBM + SHAP 으로 구동.
데이터 부족 시 규칙 기반 폴백 자동 적용.
"""
import os
import math
import json
import joblib
import logging
import warnings
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

MODEL_DIR = Path(os.getenv("ML_MODELS_PATH", "/app/ml_models"))
MODEL_DIR.mkdir(parents=True, exist_ok=True)

FEATURE_COLS = [
    "agency_avg_rate_12m", "agency_win_rate_12m", "agency_bid_count_12m",
    "agency_avg_rate_3m", "agency_avg_rate_6m",       # 단기 추세 피처
    "region_avg_rate_12m", "industry_avg_rate_12m",
    "expected_competitor_count", "competitor_strength_score",
    "season_index", "amount_log10", "amount_bucket",
    "similar_bid_count", "similar_avg_rate", "similar_std_rate",
    "month_of_year", "is_q4", "has_region_restriction",
    "yega_top3_freq", "yega_entropy", "yega_mode_bucket",  # 복수예가 패턴 피처
    "our_bid_rate",  # 낙찰 분류기 전용 — 실제 투찰 후보율 (재학습 필요)
]

FEATURE_LABELS = {
    "agency_avg_rate_12m":       "발주기관 최근 낙찰 평균율",
    "agency_win_rate_12m":       "발주기관 낙찰률",
    "agency_avg_rate_3m":        "발주기관 3개월 낙찰 평균율",
    "agency_avg_rate_6m":        "발주기관 6개월 낙찰 평균율",
    "similar_avg_rate":          "유사 입찰 낙찰 평균율",
    "expected_competitor_count": "예상 경쟁업체 수",
    "competitor_strength_score": "경쟁사 공격성 점수",
    "amount_bucket":             "공사 규모 구간",
    "is_q4":                     "4분기 집중 시기",
    "region_avg_rate_12m":       "지역 평균 투찰률",
    "industry_avg_rate_12m":     "공종 평균 투찰률",
    "similar_bid_count":         "유사 사례 수",
    "season_index":              "계절 지수",
    "amount_log10":              "공사 금액(로그)",
    "agency_bid_count_12m":      "기관 연간 입찰 건수",
    "yega_top3_freq":            "복수예가 상위3 선택 집중도",
    "yega_entropy":              "복수예가 선택 다양성",
    "yega_mode_bucket":          "복수예가 우세 구간",
}

# ──────────────────────────────────────────────────
# 피처 생성
# ──────────────────────────────────────────────────

def build_features(
    agency_id: int,
    industry_id: int,
    region_id: int,
    base_amount: int,
    construction_period: Optional[int],
    region_restriction: bool,
    bid_open_date: Optional[datetime],
    historical_df: pd.DataFrame,
    yega_features: Optional[dict] = None,
) -> dict:
    dt = bid_open_date or datetime.now()
    features = {}

    # 금액 피처
    log_amt = math.log10(max(base_amount, 1))
    features["amount_log10"] = round(log_amt, 4)
    features["amount_bucket"] = _amount_bucket(base_amount)

    # 시계열 피처
    features["month_of_year"] = dt.month
    features["season_index"]  = (dt.month - 1) // 3 + 1
    features["is_q4"]         = int(dt.month >= 10)

    # 기본 피처
    features["has_region_restriction"] = int(region_restriction)

    if historical_df.empty:
        return {**features, **_zero_context_features()}

    # 기관 피처
    agency_hist = historical_df[historical_df["agency_id"] == agency_id]
    features.update(_agg_features(agency_hist, "agency"))

    # 단기 추세 피처 (3개월 / 6개월)
    if not agency_hist.empty and "bid_open_date" in agency_hist.columns:
        try:
            cutoff_3m = dt - timedelta(days=90)
            cutoff_6m = dt - timedelta(days=180)
            ah3 = agency_hist[pd.to_datetime(agency_hist["bid_open_date"]) >= cutoff_3m]
            ah6 = agency_hist[pd.to_datetime(agency_hist["bid_open_date"]) >= cutoff_6m]
            features["agency_avg_rate_3m"] = float(ah3["winner_rate"].mean()) if not ah3.empty and ah3["winner_rate"].notna().any() else None
            features["agency_avg_rate_6m"] = float(ah6["winner_rate"].mean()) if not ah6.empty and ah6["winner_rate"].notna().any() else None
        except Exception:
            features["agency_avg_rate_3m"] = None
            features["agency_avg_rate_6m"] = None
    else:
        features["agency_avg_rate_3m"] = None
        features["agency_avg_rate_6m"] = None

    # 지역 피처
    region_hist = historical_df[historical_df["region_id"] == region_id]
    features["region_avg_rate_12m"] = float(region_hist["winner_rate"].mean()) if not region_hist.empty else None

    # 공종 피처
    ind_hist = historical_df[historical_df["industry_id"] == industry_id]
    features["industry_avg_rate_12m"] = float(ind_hist["winner_rate"].mean()) if not ind_hist.empty else None

    # 유사 입찰 피처
    similar = historical_df[
        (historical_df["industry_id"] == industry_id) &
        (historical_df["region_id"] == region_id) &
        (historical_df["base_amount"].between(base_amount * 0.6, base_amount * 1.4))
    ].tail(30)
    features.update(_similar_features(similar))

    # 경쟁 피처
    features["expected_competitor_count"] = (
        int(agency_hist["competitor_count"].mean()) if not agency_hist.empty and agency_hist["competitor_count"].notna().any() else 10
    )
    features["competitor_strength_score"] = 5.0  # 기본값 (알려진 경쟁사 없을 때)

    # 복수예가 패턴 피처
    _yf = yega_features or {}
    features["yega_top3_freq"]   = _yf.get("top3_freq")
    features["yega_entropy"]     = _yf.get("entropy")
    features["yega_mode_bucket"] = _yf.get("mode_bucket")

    return features


def _amount_bucket(amount: int) -> int:
    if amount < 1e8:     return 1
    elif amount < 5e8:   return 2
    elif amount < 1e9:   return 3
    elif amount < 5e9:   return 4
    else:                return 5


def _agg_features(df: pd.DataFrame, prefix: str) -> dict:
    if df.empty:
        return {
            f"{prefix}_avg_rate_12m": None,
            f"{prefix}_win_rate_12m": None,
            f"{prefix}_bid_count_12m": 0,
        }
    return {
        f"{prefix}_avg_rate_12m":  float(df["winner_rate"].mean()),
        f"{prefix}_win_rate_12m":  float(df["winner_rate"].notna().mean()),
        f"{prefix}_bid_count_12m": len(df),
    }


def _similar_features(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"similar_bid_count": 0, "similar_avg_rate": None, "similar_std_rate": None}
    rates = df["winner_rate"].dropna()
    return {
        "similar_bid_count": len(df),
        "similar_avg_rate":  float(rates.mean()) if not rates.empty else None,
        "similar_std_rate":  float(rates.std())  if len(rates) > 1 else 0.002,
    }


def _zero_context_features() -> dict:
    return {
        "agency_avg_rate_12m": None,  "agency_win_rate_12m": None,
        "agency_bid_count_12m": 0,    "agency_avg_rate_3m": None,
        "agency_avg_rate_6m": None,   "region_avg_rate_12m": None,
        "industry_avg_rate_12m": None, "expected_competitor_count": 10,
        "competitor_strength_score": 5.0, "similar_bid_count": 0,
        "similar_avg_rate": None,     "similar_std_rate": None,
        "yega_top3_freq": None, "yega_entropy": None, "yega_mode_bucket": None,
        "our_bid_rate": None,
    }


# ──────────────────────────────────────────────────
# 모델 학습
# ──────────────────────────────────────────────────

def train_models(df: pd.DataFrame, clf_df: Optional["pd.DataFrame"] = None) -> dict:
    """
    df     : 낙찰 레코드 (feature_cols + target_rate + is_winner=True) — 분위수 회귀 전용
    clf_df : 전체 참가자 레코드 (winners + non-winners) — 분류기 전용.
             None 이면 df 를 그대로 사용(하위 호환).
    반환: 학습된 모델 정보 dict
    """
    import xgboost as xgb
    import lightgbm as lgb
    from sklearn.model_selection import train_test_split
    from sklearn.impute import SimpleImputer

    logger.info(f"모델 학습 시작 - 낙찰={len(df)}건, 분류={len(clf_df) if clf_df is not None else len(df)}건")

    winner_df = df[df["is_winner"] == True].copy()
    if len(winner_df) < 20:
        logger.warning("낙찰 데이터 부족 — 규칙 기반 모드 유지")
        return {}

    # imputer: 전체 데이터(clf_df)로 fit → 더 넓은 값 범위 커버
    # keep_empty_features=True: 전체 NaN 피처(예: yega_*)도 컬럼 수 유지 → win_model 피처 수 일치 보장
    all_for_imputer = clf_df if clf_df is not None else df
    imputer = SimpleImputer(strategy="median", keep_empty_features=True)
    imputer.fit(all_for_imputer[FEATURE_COLS].copy())

    # ── 분위수 회귀 (XGBoost) — 낙찰 레코드만 사용
    X_w   = imputer.transform(df[FEATURE_COLS].copy())
    y_rate = df["target_rate"].astype(float)
    X_tr_w, X_val_w, yr_tr, yr_val = train_test_split(X_w, y_rate, test_size=0.2, random_state=42)

    import os as _os
    _n_jobs = max(1, int(_os.cpu_count() or 4) // 2)  # CPU 절반만 사용

    rate_models = {}
    for q in [0.05, 0.25, 0.50, 0.75, 0.95]:
        m = xgb.XGBRegressor(
            n_estimators=200, max_depth=5, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8, min_child_weight=10,
            objective="reg:quantileerror", quantile_alpha=q,
            tree_method="hist", random_state=42, verbosity=0,
            nthread=_n_jobs,
        )
        m.fit(X_tr_w, yr_tr, eval_set=[(X_val_w, yr_val)],
              verbose=False, early_stopping_rounds=30)
        rate_models[q] = m
    logger.info("분위수 회귀 학습 완료")

    # ── 낙찰 분류기 (LightGBM) — winners + non-winners 필요
    win_model = None
    clf_source = clf_df if clf_df is not None else df
    X_c  = imputer.transform(clf_source[FEATURE_COLS].copy())
    y_win = clf_source["is_winner"].astype(int).values

    pos = int(y_win.sum())
    neg = len(y_win) - pos
    if neg >= 5 and pos >= 5:
        X_tr_c, X_val_c, yw_tr, yw_val = train_test_split(X_c, y_win, test_size=0.2, random_state=42, stratify=y_win)
        scale = neg / pos
        win_model = lgb.LGBMClassifier(
            n_estimators=200, num_leaves=31, learning_rate=0.05,
            min_child_samples=10, scale_pos_weight=scale,
            subsample=0.8, colsample_bytree=0.8, verbosity=-1, random_state=42,
            n_jobs=_n_jobs,
        )
        win_model.fit(X_tr_c, yw_tr, eval_set=[(X_val_c, yw_val)],
                      callbacks=[lgb.early_stopping(30, verbose=False),
                                  lgb.log_evaluation(-1)])
        logger.info(f"낙찰 분류기 학습 완료 — pos={pos} neg={neg}")
    else:
        logger.info(f"낙찰 분류기 스킵 — pos={pos} neg={neg} (비낙찰 데이터 부족, Monte Carlo 사용)")

    # 저장
    version = datetime.now().strftime("%Y%m%d_%H%M")
    joblib.dump(rate_models, MODEL_DIR / "rate_models.pkl")
    if win_model is not None:
        joblib.dump(win_model, MODEL_DIR / "win_model.pkl")
    else:
        # win_model 스킵 시 구버전 파일 삭제 — 피처 수 불일치 방지
        win_path = MODEL_DIR / "win_model.pkl"
        if win_path.exists():
            win_path.unlink()
    joblib.dump(imputer,     MODEL_DIR / "imputer.pkl")
    with open(MODEL_DIR / "meta.json", "w") as f:
        json.dump({"version": version, "train_size": len(df),
                   "winner_size": len(winner_df), "clf_size": len(clf_source),
                   "has_win_model": win_model is not None}, f)

    logger.info(f"모델 학습 완료 — 버전: {version}")
    return {"version": version, "train_size": len(df)}


def train_models_temporal(
    df: pd.DataFrame,
    clf_df: Optional[pd.DataFrame] = None,
    val_weeks: int = 4,
    date_col: str = "bid_open_date",
) -> dict:
    """
    C-3: 시간적 교차검증 기반 모델 학습.

    랜덤 분할 대신 최근 val_weeks주를 검증셋으로 사용.
    미래 데이터 누수를 방지해 실전 성능 추정의 신뢰도를 높인다.

    Returns: train_models() 결과 + temporal_val_metrics 포함
    """
    from datetime import timedelta

    result = {}

    if date_col not in df.columns or df[date_col].isna().all():
        logger.warning("temporal CV: 날짜 컬럼 없음 — 일반 학습으로 폴백")
        return train_models(df, clf_df)

    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.sort_values(date_col)

    cutoff = df[date_col].max() - timedelta(weeks=val_weeks)
    train_mask = df[date_col] < cutoff
    val_mask   = df[date_col] >= cutoff

    df_train = df[train_mask].copy()
    df_val   = df[val_mask].copy()

    if len(df_train) < 20 or len(df_val) < 5:
        # 날짜 분포가 좁아 시간 기반 분할 실패 → 행 순서 기반 80/20 폴백
        n = len(df)
        split_idx = int(n * 0.80)
        df_train = df.iloc[:split_idx].copy()
        df_val   = df.iloc[split_idx:].copy()
        cutoff   = df_train[date_col].max()
        logger.info(
            f"temporal CV: 날짜분포 좁음({df[date_col].min().date()}~{df[date_col].max().date()}) "
            f"→ 80/20 폴백: train={len(df_train)}, val={len(df_val)}, cutoff={cutoff.date()}"
        )

    # clf_df도 동일 날짜 기준으로 분할
    clf_train = None
    if clf_df is not None and date_col in clf_df.columns:
        clf_df_copy = clf_df.copy()
        clf_df_copy[date_col] = pd.to_datetime(clf_df_copy[date_col], errors="coerce")
        clf_train = clf_df_copy[clf_df_copy[date_col] < cutoff].copy()

    logger.info(f"Temporal CV: train={len(df_train)}건 ({df_train[date_col].min().date()}~{cutoff.date()}) "
                f"val={len(df_val)}건 ({cutoff.date()}~{df_val[date_col].max().date()})")

    # 훈련
    result = train_models(df_train, clf_train)

    # 검증 지표 계산
    try:
        import xgboost as xgb
        from sklearn.impute import SimpleImputer
        import joblib

        rate_models = joblib.load(MODEL_DIR / "rate_models.pkl")
        imputer     = joblib.load(MODEL_DIR / "imputer.pkl")

        X_val = imputer.transform(df_val[FEATURE_COLS].copy())
        y_val = df_val["target_rate"].astype(float).values

        pred_center = rate_models[0.50].predict(X_val)
        mae  = float(np.mean(np.abs(y_val - pred_center)))
        rmse = float(np.sqrt(np.mean((y_val - pred_center) ** 2)))
        bias = float(np.mean(pred_center - y_val))

        # 분위수 커버리지
        pred_low  = rate_models[0.25].predict(X_val)
        pred_high = rate_models[0.75].predict(X_val)
        coverage_50 = float(np.mean((y_val >= pred_low) & (y_val <= pred_high)))

        temporal_metrics = {
            "val_weeks":     val_weeks,
            "val_size":      len(df_val),
            "train_size":    len(df_train),
            "mae":           round(mae, 6),
            "rmse":          round(rmse, 6),
            "bias":          round(bias, 6),
            "coverage_50pct": round(coverage_50, 4),
            "cutoff_date":   str(cutoff.date()),
        }

        # PR-AUC: win_model 분류 성능 측정
        pr_auc = None
        ece = None
        try:
            win_path = MODEL_DIR / "win_model.pkl"
            if win_path.exists() and clf_df is not None and date_col in clf_df.columns:
                from sklearn.metrics import average_precision_score
                clf_df_c = clf_df.copy()
                clf_df_c[date_col] = pd.to_datetime(clf_df_c[date_col], errors="coerce")
                clf_val = clf_df_c[clf_df_c[date_col] >= cutoff].copy()
                if len(clf_val) >= 10:
                    win_m = joblib.load(win_path)
                    X_clf_val = imputer.transform(clf_val[FEATURE_COLS].copy())
                    y_clf_val = clf_val["is_winner"].astype(int).values
                    if y_clf_val.sum() >= 2:
                        y_win_pred = win_m.predict_proba(X_clf_val)[:, 1]
                        pr_auc = round(float(average_precision_score(y_clf_val, y_win_pred)), 6)
                        # ECE: 10-bin 캘리브레이션 오차
                        bins = np.linspace(0, 1, 11)
                        ece_val = 0.0
                        for i in range(10):
                            mask = (y_win_pred >= bins[i]) & (y_win_pred < bins[i + 1])
                            if mask.sum() > 0:
                                ece_val += mask.sum() / len(y_win_pred) * abs(
                                    float(y_clf_val[mask].mean()) - float(y_win_pred[mask].mean())
                                )
                        ece = round(ece_val, 6)
                        temporal_metrics["pr_auc"] = pr_auc
                        temporal_metrics["calibration_ece"] = ece
        except Exception as _prc_e:
            logger.warning("PR-AUC 계산 실패: %s", _prc_e)

        result["temporal_val_metrics"] = temporal_metrics
        logger.info(f"Temporal 검증: MAE={mae:.5f} RMSE={rmse:.5f} Bias={bias:.5f} "
                    f"Coverage(50%)={coverage_50:.3f}"
                    + (f" PR-AUC={pr_auc:.4f}" if pr_auc is not None else "")
                    + (f" ECE={ece:.4f}" if ece is not None else ""))

        # 메타 파일에 temporal 지표 추가
        import json
        meta_path = MODEL_DIR / "meta.json"
        if meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)
            meta.update(temporal_metrics)
            with open(meta_path, "w") as f:
                json.dump(meta, f)
    except Exception as e:
        logger.warning(f"Temporal 검증 지표 계산 실패: {e}")

    return result


# ──────────────────────────────────────────────────
# 추천 엔진
# ──────────────────────────────────────────────────

class RecommendEngine:
    """단일 인스턴스로 재사용. 모델 없으면 규칙 기반 폴백."""

    def __init__(self):
        self._rate_models = None
        self._rate_models = None
        self._win_model   = None
        self._explainer   = None
        self._imputer     = None
        self._version     = "rule-based"
        self._load_models()

    def _load_models(self):
        try:
            if (MODEL_DIR / "rate_models.pkl").exists():
                rate_models = joblib.load(MODEL_DIR / "rate_models.pkl")
                imputer     = joblib.load(MODEL_DIR / "imputer.pkl")
                # 피처 수 호환성 검사 — 불일치 시 재학습 필요
                if hasattr(imputer, "n_features_in_") and imputer.n_features_in_ != len(FEATURE_COLS):
                    logger.warning(
                        f"모델 피처 수 불일치 (저장={imputer.n_features_in_}, 현재={len(FEATURE_COLS)}) "
                        "— 규칙 기반 폴백, 재학습 필요"
                    )
                    return
                self._rate_models = rate_models
                self._imputer     = imputer
                win_path = MODEL_DIR / "win_model.pkl"
                if win_path.exists():
                    _wm = joblib.load(win_path)
                    # win_model 피처 수 호환성 검사 — 불일치 시 무시 (Monte Carlo 사용)
                    if hasattr(_wm, "n_features_in_") and _wm.n_features_in_ != len(FEATURE_COLS):
                        logger.warning(
                            f"win_model 피처 수 불일치 (저장={_wm.n_features_in_}, 현재={len(FEATURE_COLS)}) "
                            "— win_model 무시, Monte Carlo 사용"
                        )
                        self._win_model = None
                    else:
                        self._win_model = _wm
                else:
                    self._win_model = None
                with open(MODEL_DIR / "meta.json") as f:
                    meta = json.load(f)
                self._version = meta.get("version", "unknown")
                logger.info(f"ML 모델 로드 완료 — {self._version} (win_model={'O' if self._win_model else 'X'})")
                try:
                    import shap
                    self._explainer = shap.TreeExplainer(self._rate_models[0.50])
                    logger.info("SHAP explainer 초기화 완료")
                except Exception as _se:
                    logger.debug(f"SHAP 사전초기화 실패: {_se}")
                    self._explainer = None
        except Exception as e:
            logger.warning(f"모델 로드 실패, 규칙 기반 사용: {e}")

    def reload(self):
        self._load_models()

    def recommend(self, features: dict) -> dict:
        if self._rate_models is None:
            return self._rule_based(features)
        return self._ml_based(features)

    def _prepare_x(self, features: dict) -> np.ndarray:
        row = [features.get(c) for c in FEATURE_COLS]
        X = np.array(row, dtype=float).reshape(1, -1)
        return self._imputer.transform(X)

    def _ml_based(self, features: dict) -> dict:
        X = self._prepare_x(features)

        rate_range = {
            q: float(m.predict(X)[0])
            for q, m in self._rate_models.items()
        }

        win_probs = {}
        our_bid_idx = FEATURE_COLS.index("our_bid_rate")
        for label, rate_key in [("at_lower",0.25),("at_center",0.50),("at_upper",0.75)]:
            if self._win_model is not None:
                X_r = X.copy()
                X_r[0, our_bid_idx] = rate_range[rate_key]
                win_probs[label] = float(self._win_model.predict_proba(X_r)[0][1])
            else:
                win_probs[label] = None

        # SHAP 설명
        shap_vals, narrative = self._explain(X, features)

        return {
            "rate_range": {
                "safe_lower": rate_range[0.05], "lower": rate_range[0.25],
                "center": rate_range[0.50],     "upper": rate_range[0.75],
                "safe_upper": rate_range[0.95],
            },
            "win_probabilities": win_probs,
            "shap_values": shap_vals,
            "narrative_ko": narrative,
            "model_version": self._version,
        }

    def _explain(self, X: np.ndarray, features: dict) -> tuple:
        try:
            if self._explainer is None:
                import shap
                self._explainer = shap.TreeExplainer(self._rate_models[0.50])
            sv = self._explainer.shap_values(X)[0]
            shap_dict = {FEATURE_COLS[i]: float(sv[i]) for i in range(len(FEATURE_COLS))}

            top3 = sorted(shap_dict.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
            parts = []
            for feat, val in top3:
                label = FEATURE_LABELS.get(feat, feat)
                direction = "높이는" if val > 0 else "낮추는"
                fval = features.get(feat, "")
                if fval is not None:
                    parts.append(f"'{label}({fval if isinstance(fval, str) else round(float(fval),4) if fval else fval})'이(가) 추천 투찰률을 {direction} 주요 요인입니다.")
            return shap_dict, " ".join(parts)
        except Exception as e:
            logger.debug(f"SHAP 계산 오류: {e}")
            return {}, self._fallback_narrative(features)

    def _fallback_narrative(self, features: dict) -> str:
        parts = []
        avg = features.get("agency_avg_rate_12m") or features.get("similar_avg_rate")
        if avg:
            parts.append(f"발주기관 최근 평균 낙찰률({avg:.4f})을 기준으로 추천하였습니다.")
        cnt = features.get("expected_competitor_count", 10)
        if cnt > 15:
            parts.append(f"경쟁사 {cnt}개사 예상으로 경쟁이 치열합니다.")
        elif cnt < 8:
            parts.append(f"경쟁사 {cnt}개사로 상대적으로 경쟁이 낮습니다.")
        if features.get("is_q4"):
            parts.append("4분기 집중 시기로 투찰률이 다소 높아질 수 있습니다.")
        return " ".join(parts) if parts else "유사 입찰 이력 기반으로 추천하였습니다."

    def _rule_based(self, features: dict) -> dict:
        """ML 모델 없을 때 규칙 기반 추천."""
        candidates = [v for k, v in features.items()
                      if "rate" in k and v is not None and 0.8 < v < 1.0]
        base = float(np.mean(candidates)) if candidates else 0.8793

        comp_cnt = features.get("expected_competitor_count", 10)
        comp_adj = -(comp_cnt - 10) * 0.0003  # 경쟁사 많을수록 낮게
        q4_adj   = 0.0005 if features.get("is_q4") else 0.0

        center = round(base + comp_adj + q4_adj, 6)
        spread = 0.004 + (comp_cnt / 100) * 0.002

        def wp(rate_offset: float) -> float:
            rate = center + rate_offset
            if comp_cnt <= 5:   base_p = 0.35
            elif comp_cnt <= 10: base_p = 0.22
            elif comp_cnt <= 15: base_p = 0.15
            else:               base_p = 0.10
            proximity = 1.0 - abs(rate - center) / spread
            return min(0.95, max(0.02, base_p * proximity * 1.5))

        narrative = self._fallback_narrative(features)
        narrative += " (데이터 축적 중 — 규칙 기반 추천)"

        return {
            "rate_range": {
                "safe_lower": round(center - spread * 2, 6),
                "lower":      round(center - spread, 6),
                "center":     round(center, 6),
                "upper":      round(center + spread, 6),
                "safe_upper": round(center + spread * 2, 6),
            },
            "win_probabilities": {
                "at_lower":  round(wp(-spread), 4),
                "at_center": round(wp(0), 4),
                "at_upper":  round(wp(spread), 4),
            },
            "shap_values": {},
            "narrative_ko": narrative,
            "model_version": "rule-based-v1",
        }


def get_model_meta() -> dict:
    """현재 로드된 모델의 메타데이터 반환."""
    try:
        with open(MODEL_DIR / "meta.json") as f:
            return json.load(f)
    except Exception:
        return {"version": "unknown"}


# 싱글턴
_engine: Optional[RecommendEngine] = None


def get_engine() -> RecommendEngine:
    global _engine
    if _engine is None:
        _engine = RecommendEngine()
    return _engine

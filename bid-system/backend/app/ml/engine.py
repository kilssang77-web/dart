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
    }


# ──────────────────────────────────────────────────
# 모델 학습
# ──────────────────────────────────────────────────

def train_models(df: pd.DataFrame) -> dict:
    """
    df 컬럼: feature_cols + target_rate + is_winner
    반환: 학습된 모델 정보 dict
    """
    import xgboost as xgb
    import lightgbm as lgb
    from sklearn.model_selection import train_test_split
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline

    logger.info(f"모델 학습 시작 - 데이터 {len(df)}건")

    winner_df = df[df["is_winner"] == True].copy()
    if len(winner_df) < 20:
        logger.warning("낙찰 데이터 부족 — 규칙 기반 모드 유지")
        return {}

    X = df[FEATURE_COLS].copy()
    y_rate = df["target_rate"].astype(float)
    y_win  = df["is_winner"].astype(int)

    imputer = SimpleImputer(strategy="median")
    X_imp = imputer.fit_transform(X)

    X_tr, X_val, yr_tr, yr_val, yw_tr, yw_val = train_test_split(
        X_imp, y_rate, y_win, test_size=0.2, random_state=42
    )

    # 투찰률 분위수 모델 (XGBoost)
    rate_models = {}
    for q in [0.05, 0.25, 0.50, 0.75, 0.95]:
        m = xgb.XGBRegressor(
            n_estimators=200, max_depth=5, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8, min_child_weight=10,
            objective="reg:quantileerror", quantile_alpha=q,
            tree_method="hist", random_state=42, verbosity=0,
        )
        m.fit(X_tr, yr_tr, eval_set=[(X_val, yr_val)],
              verbose=False, early_stopping_rounds=30)
        rate_models[q] = m

    # 낙찰확률 모델 (LightGBM) — 비낙찰 데이터가 있을 때만 학습
    pos = int(yw_tr.sum())
    neg = len(yw_tr) - pos
    win_model = None
    if neg >= 5 and pos >= 5:
        scale = neg / pos
        win_model = lgb.LGBMClassifier(
            n_estimators=200, num_leaves=31, learning_rate=0.05,
            min_child_samples=10, scale_pos_weight=scale,
            subsample=0.8, colsample_bytree=0.8, verbosity=-1, random_state=42,
        )
        win_model.fit(X_tr, yw_tr, eval_set=[(X_val, yw_val)],
                      callbacks=[lgb.early_stopping(30, verbose=False),
                                  lgb.log_evaluation(-1)])
    else:
        logger.info(f"낙찰 분류기 스킵 — pos={pos} neg={neg} (비낙찰 데이터 부족, Monte Carlo 사용)")

    # 저장
    version = datetime.now().strftime("%Y%m%d_%H%M")
    joblib.dump(rate_models, MODEL_DIR / "rate_models.pkl")
    if win_model is not None:
        joblib.dump(win_model, MODEL_DIR / "win_model.pkl")
    joblib.dump(imputer,     MODEL_DIR / "imputer.pkl")
    with open(MODEL_DIR / "meta.json", "w") as f:
        json.dump({"version": version, "train_size": len(df),
                   "winner_size": len(winner_df), "has_win_model": win_model is not None}, f)

    logger.info(f"모델 학습 완료 — 버전: {version}")
    return {"version": version, "train_size": len(df)}


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
        for label, rate_key in [("at_lower",0.25),("at_center",0.50),("at_upper",0.75)]:
            if self._win_model is not None:
                X_r = X.copy()
                X_r[0, FEATURE_COLS.index("similar_avg_rate")] = rate_range[rate_key]
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

        center = round(base + comp_adj + q4_adj, 4)
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
                "safe_lower": round(center - spread * 2, 4),
                "lower":      round(center - spread, 4),
                "center":     center,
                "upper":      round(center + spread, 4),
                "safe_upper": round(center + spread * 2, 4),
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


# 싱글턴
_engine: Optional[RecommendEngine] = None


def get_engine() -> RecommendEngine:
    global _engine
    if _engine is None:
        _engine = RecommendEngine()
    return _engine

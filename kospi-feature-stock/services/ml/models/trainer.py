import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import (
    accuracy_score, brier_score_loss, f1_score,
    precision_score, recall_score, roc_auc_score,
)

logger = logging.getLogger(__name__)

_BASE_PARAMS = {
    "boosting_type": "gbdt",
    "num_leaves": 48,
    "max_depth": 7,
    "learning_rate": 0.03,
    "n_estimators": 3000,
    "min_child_samples": 50,
    "feature_fraction": 0.7,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "reg_alpha": 0.2,
    "reg_lambda": 0.2,
    "min_split_gain": 0.01,
    "random_state": 42,
    "n_jobs": -1,
    "verbose": -1,
}


class LGBMTrainer:

    def train_entry(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame,
        y_val: pd.Series,
        model_dir: str = "/models/lgbm",
        use_smote: bool = False,
    ) -> lgb.LGBMClassifier:
        pos_count = int(y_train.sum())
        neg_count = int((y_train == 0).sum())
        scale_pos = neg_count / max(pos_count, 1)
        logger.info(
            f"[Trainer] Entry class: pos={pos_count} neg={neg_count} "
            f"ratio={pos_count/max(pos_count+neg_count,1):.3f} scale_pos_weight={scale_pos:.2f}"
        )

        X_tr, y_tr = X_train, y_train

        if use_smote and pos_count >= 10:
            try:
                from imblearn.over_sampling import SMOTE
                sm = SMOTE(random_state=42, k_neighbors=min(5, pos_count - 1))
                X_tr, y_tr = sm.fit_resample(X_train, y_train)
                scale_pos  = 1.0
                logger.info(f"[Trainer] SMOTE applied: {X_train.shape} → {X_tr.shape}")
            except ImportError:
                logger.warning("[Trainer] imbalanced-learn not installed, skipping SMOTE")
            except Exception as e:
                logger.warning(f"[Trainer] SMOTE failed: {e}")

        params = dict(_BASE_PARAMS)
        params["objective"] = "binary"
        params["metric"] = ["binary_logloss", "auc"]
        params["scale_pos_weight"] = scale_pos

        model = lgb.LGBMClassifier(**params)
        model.fit(
            X_tr, y_tr,
            eval_set=[(X_val, y_val)],
            callbacks=[
                lgb.early_stopping(150, verbose=False),
                lgb.log_evaluation(200),
            ],
        )

        raw_proba = model.predict_proba(X_val)[:, 1]
        auc = roc_auc_score(y_val, raw_proba)
        logger.info(f"Entry model AUC: {auc:.4f}")

        Path(model_dir).mkdir(parents=True, exist_ok=True)
        model.booster_.save_model(f"{model_dir}/entry_model.lgb")

        # ── Isotonic calibration ──────────────────────────────
        cal = IsotonicRegression(out_of_bounds="clip")
        cal.fit(raw_proba, np.array(y_val))
        joblib.dump(cal, f"{model_dir}/entry_calibrator.pkl")

        # ── 피처 컬럼 목록 저장 (단일 소스 오브 트루스) ──────
        feature_cols = list(X_train.columns)
        with open(f"{model_dir}/feature_columns.json", "w") as fp:
            json.dump(feature_cols, fp)
        logger.info(f"feature_columns.json saved ({len(feature_cols)} features)")

        # ── 모델 성능 지표 저장 ───────────────────────────────
        cal_proba = np.clip(cal.predict(raw_proba), 0.0, 1.0)
        y_pred    = (cal_proba >= 0.5).astype(int)
        fi = dict(zip(X_train.columns, model.feature_importances_.tolist()))
        top_fi = dict(sorted(fi.items(), key=lambda x: -x[1])[:30])
        metrics = {
            "model_type":   "LightGBM (Entry)",
            "trained_at":   datetime.now(timezone.utc).isoformat(),
            "n_features":   len(feature_cols),
            "n_train":      len(X_train),
            "n_val":        len(X_val),
            "auc":          round(float(auc), 4),
            "f1":           round(float(f1_score(y_val, y_pred, zero_division=0)), 4),
            "precision":    round(float(precision_score(y_val, y_pred, zero_division=0)), 4),
            "recall":       round(float(recall_score(y_val, y_pred, zero_division=0)), 4),
            "accuracy":     round(float(accuracy_score(y_val, y_pred)), 4),
            "brier_score":  round(float(brier_score_loss(y_val, cal_proba)), 4),
            "feature_importance": top_fi,
        }
        with open(f"{model_dir}/model_metrics.json", "w") as fp:
            json.dump(metrics, fp, indent=2)
        logger.info(f"model_metrics.json saved: AUC={auc:.4f}")

        return model

    def train_risk(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame,
        y_val: pd.Series,
        model_dir: str = "/models/lgbm",
        use_smote: bool = False,
    ) -> lgb.LGBMClassifier:
        pos_count = int(y_train.sum())
        neg_count = int((y_train == 0).sum())
        scale_pos = neg_count / max(pos_count, 1)
        logger.info(
            f"[Trainer] Risk class: pos={pos_count} neg={neg_count} "
            f"ratio={pos_count/max(pos_count+neg_count,1):.3f} scale_pos_weight={scale_pos:.2f}"
        )

        X_tr, y_tr = X_train, y_train

        if use_smote and pos_count >= 10:
            try:
                from imblearn.over_sampling import SMOTE
                sm = SMOTE(random_state=42, k_neighbors=min(5, pos_count - 1))
                X_tr, y_tr = sm.fit_resample(X_train, y_train)
                scale_pos  = 1.0
                logger.info(f"[Trainer] SMOTE applied: {X_train.shape} → {X_tr.shape}")
            except ImportError:
                logger.warning("[Trainer] imbalanced-learn not installed, skipping SMOTE")
            except Exception as e:
                logger.warning(f"[Trainer] SMOTE failed: {e}")

        params = dict(_BASE_PARAMS)
        params["objective"] = "binary"
        params["metric"] = "auc"
        params["scale_pos_weight"] = scale_pos

        model = lgb.LGBMClassifier(**params)
        model.fit(
            X_tr, y_tr,
            eval_set=[(X_val, y_val)],
            callbacks=[lgb.early_stopping(100, verbose=False)],
        )
        raw_proba = model.predict_proba(X_val)[:, 1]
        model.booster_.save_model(f"{model_dir}/risk_model.lgb")

        cal = IsotonicRegression(out_of_bounds="clip")
        cal.fit(raw_proba, np.array(y_val))
        joblib.dump(cal, f"{model_dir}/risk_calibrator.pkl")
        logger.info("Risk calibrator saved")

        return model

    @staticmethod
    def make_label_entry(df: pd.DataFrame, fwd: int = 5, thr: float = 0.05) -> pd.Series:
        return (df["close"].pct_change(fwd).shift(-fwd) >= thr).astype(int)

    @staticmethod
    def make_label_risk(df: pd.DataFrame, fwd: int = 5, loss: float = -0.05) -> pd.Series:
        return (df["close"].pct_change(fwd).shift(-fwd) <= loss).astype(int)
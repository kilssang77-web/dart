import logging
from pathlib import Path
import joblib
import pandas as pd
import lightgbm as lgb
import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_auc_score

logger = logging.getLogger(__name__)

_BASE_PARAMS = {
    "boosting_type": "gbdt",
    "num_leaves": 63,
    "max_depth": -1,
    "learning_rate": 0.05,
    "n_estimators": 2000,
    "min_child_samples": 30,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "reg_alpha": 0.1,
    "reg_lambda": 0.1,
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
                scale_pos  = 1.0   # SMOTE already balanced
                logger.info(f"[Trainer] SMOTE applied: {X_train.shape} → {X_tr.shape}")
            except ImportError:
                logger.warning("[Trainer] imbalanced-learn not installed, skipping SMOTE")
            except Exception as e:
                logger.warning(f"[Trainer] SMOTE failed: {e}")

        # Merge scale_pos_weight into params
        params = dict(_BASE_PARAMS)
        params["objective"] = "binary"
        params["metric"] = ["binary_logloss", "auc"]
        params["scale_pos_weight"] = scale_pos

        model = lgb.LGBMClassifier(**params)
        model.fit(
            X_tr, y_tr,
            eval_set=[(X_val, y_val)],
            callbacks=[
                lgb.early_stopping(100, verbose=False),
                lgb.log_evaluation(200),
            ],
        )

        raw_proba = model.predict_proba(X_val)[:, 1]
        auc = roc_auc_score(y_val, raw_proba)
        logger.info(f"Entry model AUC: {auc:.4f}")

        Path(model_dir).mkdir(parents=True, exist_ok=True)
        model.booster_.save_model(f"{model_dir}/entry_model.lgb")

        cal = IsotonicRegression(out_of_bounds="clip")
        cal.fit(raw_proba, np.array(y_val))
        joblib.dump(cal, f"{model_dir}/entry_calibrator.pkl")
        logger.info("Entry calibrator saved")

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
                scale_pos  = 1.0   # SMOTE already balanced
                logger.info(f"[Trainer] SMOTE applied: {X_train.shape} → {X_tr.shape}")
            except ImportError:
                logger.warning("[Trainer] imbalanced-learn not installed, skipping SMOTE")
            except Exception as e:
                logger.warning(f"[Trainer] SMOTE failed: {e}")

        # Merge scale_pos_weight into params
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

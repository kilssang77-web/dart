import logging
from pathlib import Path
import pandas as pd
import lightgbm as lgb
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
    ) -> lgb.LGBMClassifier:
        params = {**_BASE_PARAMS, "objective": "binary", "metric": ["binary_logloss", "auc"]}
        model = lgb.LGBMClassifier(**params)
        model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            callbacks=[
                lgb.early_stopping(100, verbose=False),
                lgb.log_evaluation(200),
            ],
        )

        auc = roc_auc_score(y_val, model.predict_proba(X_val)[:, 1])
        logger.info(f"Entry model AUC: {auc:.4f}")

        Path(model_dir).mkdir(parents=True, exist_ok=True)
        model.booster_.save_model(f"{model_dir}/entry_model.lgb")
        return model

    def train_risk(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame,
        y_val: pd.Series,
        model_dir: str = "/models/lgbm",
    ) -> lgb.LGBMClassifier:
        params = {**_BASE_PARAMS, "objective": "binary", "metric": "auc"}
        model = lgb.LGBMClassifier(**params)
        model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            callbacks=[lgb.early_stopping(100, verbose=False)],
        )
        model.booster_.save_model(f"{model_dir}/risk_model.lgb")
        return model

    @staticmethod
    def make_label_entry(df: pd.DataFrame, fwd: int = 5, thr: float = 0.05) -> pd.Series:
        return (df["close"].pct_change(fwd).shift(-fwd) >= thr).astype(int)

    @staticmethod
    def make_label_risk(df: pd.DataFrame, fwd: int = 5, loss: float = -0.05) -> pd.Series:
        return (df["close"].pct_change(fwd).shift(-fwd) <= loss).astype(int)

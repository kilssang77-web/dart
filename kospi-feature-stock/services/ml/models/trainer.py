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
    precision_recall_curve,
)

logger = logging.getLogger(__name__)

_BASE_PARAMS = {
    "boosting_type": "gbdt",
    "num_leaves": 127,         # 63 → 127: 더 복잡한 경계면 표현
    "max_depth": 7,            # 8 → 7: num_leaves로 복잡도 제어
    "learning_rate": 0.02,     # 0.03 → 0.02: 느린 학습 → 과적합 방지
    "n_estimators": 3000,      # 2000 → 3000: 느린 LR 보상
    "min_child_samples": 25,   # 40 → 25: 소수 양성 패턴 더 학습
    "feature_fraction": 0.7,   # 0.75 → 0.7: 더 강한 랜덤화
    "bagging_fraction": 0.75,  # 0.8 → 0.75
    "bagging_freq": 5,
    "reg_alpha": 0.1,          # 0.15 → 0.1: L1 완화
    "reg_lambda": 0.2,         # 0.15 → 0.2: L2 강화 (과적합 방지)
    "min_split_gain": 0.0,     # early_stopping이 분기 제어
    "random_state": 42,
    "n_jobs": -1,
    "verbose": -1,
}


class LGBMTrainer:

    def optimize_hyperparams(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame,
        y_val: pd.Series,
        n_trials: int = 30,
    ) -> dict:
        """Optuna 기반 하이퍼파라미터 탐색. 최적 파라미터 dict 반환."""
        try:
            import optuna
            optuna.logging.set_verbosity(optuna.logging.WARNING)
        except ImportError:
            logger.warning("[HPO] optuna not installed — skipping, using default params")
            return dict(_BASE_PARAMS)

        if y_val.nunique() < 2 or len(X_val) < 50:
            logger.warning("[HPO] Val set too small for HPO — using default params")
            return dict(_BASE_PARAMS)

        scale_pos = int((y_train == 0).sum()) / max(int(y_train.sum()), 1)

        def _objective(trial: "optuna.Trial") -> float:
            params = {
                "boosting_type": "gbdt",
                "objective": "binary",
                "metric": "auc",
                "num_leaves":        trial.suggest_int("num_leaves", 63, 255),
                "max_depth":         trial.suggest_int("max_depth", 5, 9),
                "learning_rate":     trial.suggest_float("learning_rate", 0.01, 0.05, log=True),
                "n_estimators":      3000,
                "min_child_samples": trial.suggest_int("min_child_samples", 10, 50),
                "feature_fraction":  trial.suggest_float("feature_fraction", 0.5, 0.9),
                "bagging_fraction":  trial.suggest_float("bagging_fraction", 0.6, 0.9),
                "bagging_freq":      trial.suggest_int("bagging_freq", 3, 7),
                "reg_alpha":         trial.suggest_float("reg_alpha", 0.0, 0.5),
                "reg_lambda":        trial.suggest_float("reg_lambda", 0.0, 0.5),
                "scale_pos_weight":  scale_pos,
                "random_state": 42,
                "n_jobs": -1,
                "verbose": -1,
            }
            m = lgb.LGBMClassifier(**params)
            m.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                callbacks=[lgb.early_stopping(50, verbose=False),
                           lgb.log_evaluation(-1)],
            )
            prob = m.predict_proba(X_val)[:, 1]
            return roc_auc_score(y_val, prob)

        study = optuna.create_study(direction="maximize",
                                    sampler=optuna.samplers.TPESampler(seed=42))
        study.optimize(_objective, n_trials=n_trials, show_progress_bar=False)
        logger.info(f"[HPO] Best AUC={study.best_value:.4f}  params={study.best_params}")

        result = dict(_BASE_PARAMS)
        result.update(study.best_params)
        return result

    def train_entry(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame,
        y_val: pd.Series,
        model_dir: str = "/models/lgbm",
        use_smote: bool = False,
        params_override: dict | None = None,
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

        params = dict(params_override if params_override else _BASE_PARAMS)
        params["objective"] = "binary"
        params["metric"] = ["binary_logloss", "auc"]
        params["scale_pos_weight"] = scale_pos

        model = lgb.LGBMClassifier(**params)
        has_val = len(X_val) >= 30 and len(y_val) >= 30 and y_val.nunique() >= 2
        if has_val:
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
        else:
            logger.warning(f"[Trainer] Val set insufficient (n={len(X_val)}, classes={y_val.nunique() if len(y_val)>0 else 0}) — training without early stopping (1000 rounds)")
            params_no_es = dict(params)
            params_no_es["n_estimators"] = 1000
            model = lgb.LGBMClassifier(**params_no_es)
            model.fit(X_tr, y_tr)
            raw_proba = np.array([])
            auc = 0.0
        logger.info(f"Entry model AUC: {auc:.4f}")

        Path(model_dir).mkdir(parents=True, exist_ok=True)
        model.booster_.save_model(f"{model_dir}/entry_model.lgb")

        feature_cols = list(X_train.columns)
        with open(f"{model_dir}/feature_columns.json", "w") as fp:
            json.dump(feature_cols, fp)
        logger.info(f"feature_columns.json saved ({len(feature_cols)} features)")

        cal = IsotonicRegression(out_of_bounds="clip")
        if has_val:
            cal.fit(raw_proba, np.array(y_val))
            cal_proba = np.clip(cal.predict(raw_proba), 0.0, 1.0)
            precs, recs, threshs = precision_recall_curve(np.array(y_val), cal_proba)
            recall_25_mask = recs[:-1] >= 0.25
            if recall_25_mask.any():
                best_idx = int(np.argmax(precs[:-1][recall_25_mask]))
                opt_thresh = float(threshs[recall_25_mask][best_idx])
            else:
                opt_thresh = float(threshs[int(np.argmax(recs[:-1]))])
            opt_thresh = round(max(0.10, min(0.90, opt_thresh)), 4)
            y_pred_05  = (cal_proba >= 0.5).astype(int)
            y_pred_opt = (cal_proba >= opt_thresh).astype(int)
            val_metrics = {
                "auc":               round(float(auc), 4),
                "f1":                round(float(f1_score(y_val, y_pred_05, zero_division=0)), 4),
                "precision":         round(float(precision_score(y_val, y_pred_05, zero_division=0)), 4),
                "recall":            round(float(recall_score(y_val, y_pred_05, zero_division=0)), 4),
                "accuracy":          round(float(accuracy_score(y_val, y_pred_05)), 4),
                "brier_score":       round(float(brier_score_loss(y_val, cal_proba)), 4),
                "optimal_threshold": opt_thresh,
                "opt_f1":            round(float(f1_score(y_val, y_pred_opt, zero_division=0)), 4),
                "opt_precision":     round(float(precision_score(y_val, y_pred_opt, zero_division=0)), 4),
                "opt_recall":        round(float(recall_score(y_val, y_pred_opt, zero_division=0)), 4),
            }
        else:
            # val 없음 — train 예측으로 calibrator 피팅, 임계값 기본값 사용
            tr_proba = model.predict_proba(X_tr)[:, 1]
            cal.fit(tr_proba, np.array(y_tr))
            opt_thresh = 0.30
            val_metrics = {
                "auc": 0.0, "f1": 0.0, "precision": 0.0, "recall": 0.0,
                "accuracy": 0.0, "brier_score": 0.0,
                "optimal_threshold": opt_thresh,
                "opt_f1": 0.0, "opt_precision": 0.0, "opt_recall": 0.0,
            }
        joblib.dump(cal, f"{model_dir}/entry_calibrator.pkl")

        fi = dict(zip(X_train.columns, model.feature_importances_.tolist()))
        top_fi = dict(sorted(fi.items(), key=lambda x: -x[1])[:30])
        metrics = {
            "model_type": "LightGBM (Entry)",
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "n_features": len(feature_cols),
            "n_train":    len(X_train),
            "n_val":      len(X_val),
            "feature_importance": top_fi,
            **val_metrics,
        }
        with open(f"{model_dir}/model_metrics.json", "w") as fp:
            json.dump(metrics, fp, indent=2)
        logger.info(
            f"model_metrics.json saved: AUC={metrics['auc']:.4f}  "
            f"opt_threshold={val_metrics['optimal_threshold']:.3f}  "
            f"opt_recall={val_metrics['opt_recall']:.3f}  "
            f"opt_precision={val_metrics['opt_precision']:.3f}"
        )

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
        has_val = len(X_val) >= 30 and len(y_val) >= 30 and y_val.nunique() >= 2
        if has_val:
            model.fit(
                X_tr, y_tr,
                eval_set=[(X_val, y_val)],
                callbacks=[lgb.early_stopping(100, verbose=False)],
            )
            raw_proba = model.predict_proba(X_val)[:, 1]
        else:
            logger.warning(f"[Trainer] Risk val set insufficient (n={len(X_val)}) — training without early stopping (800 rounds)")
            params_no_es = dict(params)
            params_no_es["n_estimators"] = 800
            model = lgb.LGBMClassifier(**params_no_es)
            model.fit(X_tr, y_tr)
            raw_proba = model.predict_proba(X_tr)[:, 1]

        model.booster_.save_model(f"{model_dir}/risk_model.lgb")

        cal = IsotonicRegression(out_of_bounds="clip")
        cal.fit(raw_proba, np.array(y_val if has_val else y_tr))
        joblib.dump(cal, f"{model_dir}/risk_calibrator.pkl")
        logger.info("Risk calibrator saved")

        return model

    @staticmethod
    def make_label_entry(df: pd.DataFrame, fwd: int = 5, thr: float = 0.05) -> pd.Series:
        return (df["close"].pct_change(fwd).shift(-fwd) >= thr).astype(int)

    @staticmethod
    def make_label_risk(df: pd.DataFrame, fwd: int = 5, loss: float = -0.05) -> pd.Series:
        return (df["close"].pct_change(fwd).shift(-fwd) <= loss).astype(int)

    @staticmethod
    def make_labels_bulk(
        feat_df: pd.DataFrame,
        raw_df: pd.DataFrame,
        entry_pct: float = 5.0,
        risk_pct: float = 5.0,
    ) -> "tuple[pd.Series, pd.Series]":
        """멀티코드 DataFrame용 5일 선행 수익률 레이블 (데이터 누수 없음)."""
        rdf = raw_df[["code", "date", "close"]].copy()
        rdf["date"] = pd.to_datetime(rdf["date"])
        rdf = rdf.sort_values(["code", "date"])
        rdf["fwd5_close"] = rdf.groupby("code")["close"].shift(-5)
        rdf["ret5"] = (rdf["fwd5_close"] / rdf["close"].replace(0, np.nan) - 1) * 100

        if feat_df.empty or "__date" not in feat_df.columns:
            empty = pd.Series(dtype="float64")
            return empty, empty

        fdf = feat_df[["__date", "__code"]].copy()
        fdf["date"] = pd.to_datetime(fdf["__date"])
        fdf["code"] = fdf["__code"]

        merged = fdf[["code", "date"]].merge(
            rdf[["code", "date", "ret5"]],
            on=["code", "date"],
            how="left",
        )
        ret = merged["ret5"]
        entry_labels = pd.Series(
            np.where(ret.notna(), (ret >= entry_pct).astype(float), np.nan),
            dtype="float64",
        )
        risk_labels = pd.Series(
            np.where(ret.notna(), (ret <= -risk_pct).astype(float), np.nan),
            dtype="float64",
        )
        return entry_labels, risk_labels

    @staticmethod
    def make_labels_target_hit(
        feat_df: pd.DataFrame,
        raw_df: pd.DataFrame,
        fwd: int = 5,
        target_pct: float = 10.0,
        stop_pct: float = 5.0,
    ) -> "tuple[pd.Series, pd.Series]":
        """
        현실적 레이블: 다음 fwd 거래일 내 고가(high)가 목표가 달성 + 저가(low)가 손절 미발생.
        - entry_label = 1 if max(high[i+1..i+fwd]) >= close[i] * (1+target_pct%) AND
                           min(low[i+1..i+fwd])  >= close[i] * (1-stop_pct%)
        - risk_label  = 1 if min(low[i+1..i+fwd]) <= close[i] * (1-stop_pct%)
        high/low 컬럼 없으면 close로 대체.
        """
        rdf = raw_df[["code", "date", "close"]].copy()
        rdf["high"] = raw_df["high"] if "high" in raw_df.columns else raw_df["close"]
        rdf["low"]  = raw_df["low"]  if "low"  in raw_df.columns else raw_df["close"]
        rdf["date"] = pd.to_datetime(rdf["date"])
        rdf = rdf.sort_values(["code", "date"]).reset_index(drop=True)

        grp_high = rdf.groupby("code", sort=False)["high"]
        grp_low  = rdf.groupby("code", sort=False)["low"]

        # 다음 fwd 바의 고가 최대 / 저가 최소 (코드 내 shift → 누수 없음)
        max_fwd_high = pd.DataFrame(
            {k: grp_high.shift(-k) for k in range(1, fwd + 1)}
        ).max(axis=1)
        min_fwd_low = pd.DataFrame(
            {k: grp_low.shift(-k) for k in range(1, fwd + 1)}
        ).min(axis=1)

        target_price = rdf["close"] * (1 + target_pct / 100)
        stop_price   = rdf["close"] * (1 - stop_pct / 100)

        rdf["entry_label"] = np.where(
            max_fwd_high.notna() & min_fwd_low.notna(),
            ((max_fwd_high >= target_price) & (min_fwd_low >= stop_price)).astype(float),
            np.nan,
        )
        rdf["risk_label"] = np.where(
            min_fwd_low.notna(),
            (min_fwd_low <= stop_price).astype(float),
            np.nan,
        )

        if feat_df.empty or "__date" not in feat_df.columns:
            empty = pd.Series(dtype="float64")
            return empty, empty

        fdf = feat_df[["__date", "__code"]].copy()
        fdf["date"] = pd.to_datetime(fdf["__date"])
        fdf["code"] = fdf["__code"]

        merged = fdf[["code", "date"]].merge(
            rdf[["code", "date", "entry_label", "risk_label"]],
            on=["code", "date"], how="left",
        )
        return (
            pd.Series(merged["entry_label"].values, dtype="float64"),
            pd.Series(merged["risk_label"].values, dtype="float64"),
        )

    @staticmethod
    def make_labels_relative(
        feat_df: pd.DataFrame,
        raw_df: pd.DataFrame,
        fwd: int = 5,
        top_pct: float = 0.20,
        min_abs_return: float = 0.01,
        bot_pct: float = 0.10,
        max_abs_loss: float = -0.02,
    ) -> "tuple[pd.Series, pd.Series]":
        """
        시장 국면 중립적 레이블 — 절대 임계값 대신 날짜별 상대 순위 사용.

        entry_label = 1  if 같은 날 전체 종목 중 상위 top_pct% AND 절대 수익 >= min_abs_return
        risk_label  = 1  if 같은 날 전체 종목 중 하위 bot_pct% AND 절대 손실 <= max_abs_loss

        강세장/약세장에 관계없이 양성 비율이 ~top_pct%로 안정적으로 유지됨.
        """
        rdf = raw_df[["code", "date", "close"]].copy()
        rdf["date"] = pd.to_datetime(rdf["date"])
        rdf = rdf.sort_values(["code", "date"])
        rdf["fwd_close"] = rdf.groupby("code")["close"].shift(-fwd)
        rdf["ret"] = rdf["fwd_close"] / rdf["close"].replace(0, np.nan) - 1

        # 날짜별 수익률 순위 (0~1)
        rdf["ret_rank"] = rdf.groupby("date")["ret"].rank(pct=True)

        if feat_df.empty or "__date" not in feat_df.columns:
            empty = pd.Series(dtype="float64")
            return empty, empty

        fdf = feat_df[["__date", "__code"]].copy()
        fdf["date"] = pd.to_datetime(fdf["__date"])
        fdf["code"] = fdf["__code"]

        merged = fdf[["code", "date"]].merge(
            rdf[["code", "date", "ret", "ret_rank"]],
            on=["code", "date"],
            how="left",
        )

        ret      = merged["ret"]
        ret_rank = merged["ret_rank"]

        entry_labels = pd.Series(
            np.where(
                ret.notna(),
                ((ret_rank >= (1 - top_pct)) & (ret >= min_abs_return)).astype(float),
                np.nan,
            ),
            dtype="float64",
        )
        risk_labels = pd.Series(
            np.where(
                ret.notna(),
                ((ret_rank <= bot_pct) & (ret <= max_abs_loss)).astype(float),
                np.nan,
            ),
            dtype="float64",
        )
        return entry_labels, risk_labels

    @staticmethod
    def add_event_type_features(df: pd.DataFrame) -> pd.DataFrame:  # noqa: E302
        """
        event_type 컬럼을 그룹별 one-hot + 순서형 인코딩으로 변환.
        walk_forward_train.py에서 feature DataFrame에 event_type 컬럼이 있을 때 호출.
        """
        if "event_type" not in df.columns:
            return df

        _EVENT_GROUPS = {
            "momentum":    {"VOLUME_SURGE", "AMOUNT_SURGE", "LONG_WHITE_CANDLE",
                            "MORNING_STAR", "HAMMER_CANDLE"},
            "breakout":    {"BREAKOUT_20D", "BREAKOUT_13W", "BREAKOUT_26W", "BREAKOUT_52W"},
            "fundamental": {"POST_DISCLOSURE_SURGE", "SUPPLY_ANOMALY"},
            "vi":          {"VI_TRIGGERED"},
        }
        _ALL_TYPES = sorted({t for ts in _EVENT_GROUPS.values() for t in ts})
        _TYPE_MAP  = {t: i for i, t in enumerate(_ALL_TYPES)}

        df = df.copy()
        for group, types in _EVENT_GROUPS.items():
            df[f"event_{group}"] = df["event_type"].isin(types).astype(int)
        df["event_type_enc"] = df["event_type"].map(_TYPE_MAP).fillna(-1).astype(int)
        return df


class XGBTrainer:
    """XGBoost Entry/Risk 모델 훈련 (LightGBM 앙상블 보완용)."""

    _BASE_PARAMS = {
        "n_estimators":     1000,
        "max_depth":        6,
        "learning_rate":    0.02,
        "subsample":        0.75,
        "colsample_bytree": 0.70,
        "reg_alpha":        0.1,
        "reg_lambda":       0.2,
        "min_child_weight": 25,
        "random_state":     42,
        "n_jobs":           -1,
        "eval_metric":      "auc",
        "early_stopping_rounds": 80,
        "verbosity":        0,
    }

    def train_entry(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val:   pd.DataFrame,
        y_val:   pd.Series,
        model_dir: str = "/models/lgbm",
    ):
        try:
            import xgboost as xgb
        except ImportError:
            logger.warning("[XGB] xgboost not installed — skipping")
            return None

        pos = int(y_train.sum())
        neg = int((y_train == 0).sum())
        scale_pos = neg / max(pos, 1)
        logger.info(f"[XGB] Entry: pos={pos} neg={neg} scale_pos_weight={scale_pos:.2f}")

        params = dict(self._BASE_PARAMS)
        params["scale_pos_weight"] = scale_pos
        params["objective"] = "binary:logistic"

        model = xgb.XGBClassifier(**params)
        has_val = len(X_val) >= 30 and y_val.nunique() >= 2
        if has_val:
            model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
            prob = model.predict_proba(X_val)[:, 1]
            auc  = roc_auc_score(y_val, prob)
        else:
            no_es = dict(params)
            no_es.pop("early_stopping_rounds", None)
            no_es["n_estimators"] = 500
            model = xgb.XGBClassifier(**no_es)
            model.fit(X_train, y_train, verbose=False)
            auc = 0.0

        logger.info(f"[XGB] Entry Val AUC={auc:.4f}")

        # calibrator
        cal = IsotonicRegression(out_of_bounds="clip")
        if has_val:
            cal.fit(model.predict_proba(X_val)[:, 1], np.array(y_val))
        else:
            cal.fit(model.predict_proba(X_train)[:, 1], np.array(y_train))

        Path(model_dir).mkdir(parents=True, exist_ok=True)
        joblib.dump(model, f"{model_dir}/xgb_entry_model.pkl")
        joblib.dump(cal,   f"{model_dir}/xgb_entry_calibrator.pkl")
        logger.info(f"[XGB] Entry model saved to {model_dir}/xgb_entry_model.pkl")
        return model

    def train_risk(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val:   pd.DataFrame,
        y_val:   pd.Series,
        model_dir: str = "/models/lgbm",
    ):
        try:
            import xgboost as xgb
        except ImportError:
            logger.warning("[XGB] xgboost not installed — skipping")
            return None

        pos = int(y_train.sum())
        neg = int((y_train == 0).sum())
        scale_pos = neg / max(pos, 1)
        logger.info(f"[XGB] Risk: pos={pos} neg={neg} scale_pos_weight={scale_pos:.2f}")

        params = dict(self._BASE_PARAMS)
        params["scale_pos_weight"] = scale_pos
        params["objective"] = "binary:logistic"

        model = xgb.XGBClassifier(**params)
        has_val = len(X_val) >= 30 and y_val.nunique() >= 2
        if has_val:
            model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
            prob = model.predict_proba(X_val)[:, 1]
            auc  = roc_auc_score(y_val, prob)
        else:
            no_es = dict(params)
            no_es.pop("early_stopping_rounds", None)
            no_es["n_estimators"] = 500
            model = xgb.XGBClassifier(**no_es)
            model.fit(X_train, y_train, verbose=False)
            auc = 0.0

        logger.info(f"[XGB] Risk Val AUC={auc:.4f}")

        cal = IsotonicRegression(out_of_bounds="clip")
        if has_val:
            cal.fit(model.predict_proba(X_val)[:, 1], np.array(y_val))
        else:
            cal.fit(model.predict_proba(X_train)[:, 1], np.array(y_train))

        joblib.dump(model, f"{model_dir}/xgb_risk_model.pkl")
        joblib.dump(cal,   f"{model_dir}/xgb_risk_calibrator.pkl")
        logger.info(f"[XGB] Risk model saved to {model_dir}/xgb_risk_model.pkl")
        return model
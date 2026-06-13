import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_MODEL_DIR      = os.environ.get("LGBM_MODEL_DIR", "/models/lgbm")
_HOLD_SQUEEZE   = int(os.environ.get("LGBM_HOLD_SQUEEZE_DAYS", "3"))
_HOLD_VOL_HIGH  = float(os.environ.get("LGBM_VOL_HIGH_THRESH", "15.0"))
_HOLD_DEFAULT   = int(os.environ.get("LGBM_HOLD_DEFAULT_DAYS", "5"))
_RET_SCALE      = float(os.environ.get("LGBM_RET_SCALE", "20.0"))

# 기본값 — feature_columns.json 로드 성공 시 동적으로 교체됨
FEATURE_COLUMNS = [
    "return_1d", "return_3d", "return_5d",
    "ma5_ratio", "ma20_ratio", "ma60_ratio",
    "ma5_slope", "ma20_slope",
    "vol_ratio_5d", "vol_ratio_20d", "vol_surge",
    "amount_ratio",
    "atr_ratio",
    "rsi14", "rsi_oversold", "rsi_overbought",
    "macd_hist", "macd_golden_cross",
    "bb_pct", "bb_width", "bb_squeeze",
    "body_size", "is_bullish", "upper_wick", "lower_wick",
    "is_new_high_20d", "is_new_high_52d", "is_new_high_260d",
    "pos_52w",
    "foreign_cumnet_5d", "foreign_cumnet_20d",
    "inst_cumnet_5d", "inst_cumnet_20d",
    "dual_buy", "dual_buy_3d",
    "short_ratio", "short_increasing",
    "disclosure_sentiment", "has_favorable_disclosure",
    "kospi_return_1d", "kospi_return_5d",
    "rel_strength_5d",
    "market_vol_ratio",
    "return_10d", "return_20d",
    "price_accel",
    "gap_pct",
    "consec_up", "consec_down",
    "vol_up_down_ratio",
    "ma5_ma20_cross", "ma20_ma60_cross",
    "foreign_net_ratio", "inst_net_ratio",
    "dow_sin", "dow_cos",
    "month_sin", "month_cos",
    "news_sentiment_7d", "news_count_7d",
]


@dataclass
class PredictionResult:
    code: str
    success_prob: float
    entry_score: float
    risk_score: float
    expected_return: float
    hold_days: int
    confidence: float
    model_loaded: bool = False


class LGBMPredictor:

    def __init__(self, model_dir: str | None = None):
        self.model_dir = Path(model_dir or _MODEL_DIR)
        self._entry: Optional[lgb.Booster] = None
        self._risk:  Optional[lgb.Booster] = None
        self._entry_cal = None
        self._risk_cal  = None
        self.optimal_threshold: float = 0.5  # updated from model_metrics.json after load()

    def load(self) -> bool:
        global FEATURE_COLUMNS

        # ── feature_columns.json (단일 소스 오브 트루스) ──────
        fc_path = self.model_dir / "feature_columns.json"
        if fc_path.exists():
            try:
                with open(fc_path) as f:
                    cols = json.load(f)
                if cols:
                    FEATURE_COLUMNS = cols
                    logger.info(f"feature_columns.json loaded: {len(FEATURE_COLUMNS)} features")
            except Exception as e:
                logger.warning(f"Failed to load feature_columns.json: {e}")

        # ── model_metrics.json — optimal_threshold 로드 ──────
        metrics_path = self.model_dir / "model_metrics.json"
        if metrics_path.exists():
            try:
                with open(metrics_path) as f:
                    m = json.load(f)
                t = float(m.get("optimal_threshold", 0.5))
                self.optimal_threshold = max(0.10, min(0.90, t))
                logger.info(f"optimal_threshold loaded: {self.optimal_threshold:.3f} "
                            f"(opt_recall={m.get('opt_recall', '?')}  "
                            f"opt_precision={m.get('opt_precision', '?')})")
            except Exception as e:
                logger.warning(f"Failed to load model_metrics.json: {e}")

        loaded = False
        for name, attr in [("entry_model.lgb", "_entry"), ("risk_model.lgb", "_risk")]:
            path = self.model_dir / name
            if path.exists():
                try:
                    setattr(self, attr, lgb.Booster(model_file=str(path)))
                    logger.info(f"Model loaded: {path}")
                    loaded = True
                except Exception as e:
                    logger.error(f"Failed to load {path}: {e}")
            else:
                logger.warning(f"Model file not found: {path}")

        for name, attr in [("entry_calibrator.pkl", "_entry_cal"), ("risk_calibrator.pkl", "_risk_cal")]:
            path = self.model_dir / name
            if path.exists():
                try:
                    setattr(self, attr, joblib.load(str(path)))
                    logger.info(f"Calibrator loaded: {path}")
                except Exception as e:
                    logger.warning(f"Failed to load calibrator {path}: {e}")

        return loaded

    def is_ready(self) -> bool:
        return self._entry is not None

    def predict_one(self, features: dict) -> PredictionResult:
        code       = features.get("code", "")
        event_type = features.get("event_type", "")
        row  = pd.DataFrame([features])
        X    = self._prepare(row)

        prob       = self._infer(self._entry, self._entry_cal, X, default=0.5)
        risk       = self._infer(self._risk,  self._risk_cal,  X, default=0.4)
        confidence = float(X.notna().mean().mean())
        hold       = self._hold_days(X, event_type)

        exp_ret = (prob - 0.5) * _RET_SCALE if self._entry else 0.0

        return PredictionResult(
            code=code,
            success_prob=round(float(prob), 4),
            entry_score=round(float(prob), 4),
            risk_score=round(float(risk), 4),
            expected_return=round(exp_ret, 2),
            hold_days=hold,
            confidence=round(confidence, 3),
            model_loaded=self._entry is not None,
        )

    def _infer(self, model: Optional[lgb.Booster], calibrator, X: pd.DataFrame, default: float) -> float:
        if model is None:
            return default
        try:
            raw = float(np.clip(model.predict(X)[0], 0.0, 1.0))
            if calibrator is not None:
                return float(np.clip(calibrator.predict([raw])[0], 0.0, 1.0))
            return raw
        except Exception as e:
            logger.warning(f"Inference error: {e}")
            return default

    def _prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        X = pd.DataFrame(index=df.index)
        for col in FEATURE_COLUMNS:
            X[col] = df[col] if col in df.columns else 0.0
        X = X.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        return X

    def _hold_days(self, X: pd.DataFrame, event_type: str = "") -> int:
        squeeze = int(X["bb_squeeze"].values[0]) if "bb_squeeze" in X.columns else 0
        vol     = float(X["vol_ratio_20d"].values[0]) if "vol_ratio_20d" in X.columns else 1.0

        _EVENT_HOLD = {
            "VI_TRIGGERED":          1,
            "VOLUME_SURGE":          2,
            "AMOUNT_SURGE":          2,
            "POST_DISCLOSURE_SURGE": 3,
            "SUPPLY_ANOMALY":        3,
            "HAMMER_CANDLE":         5,
            "MORNING_STAR":          5,
            "LONG_WHITE_CANDLE":     5,
            "BREAKOUT_20D":          7,
            "BREAKOUT_13W":         10,
            "BREAKOUT_26W":         15,
            "BREAKOUT_52W":         20,
        }
        base = _EVENT_HOLD.get(event_type, _HOLD_DEFAULT)

        if vol > _HOLD_VOL_HIGH:
            base = max(1, base // 2)
        if squeeze:
            base = _HOLD_SQUEEZE

        return base
"""
경량 LightGBM 추론 모듈 — pandas 미사용, numpy 전용
R2에서 모델 파일 다운로드 후 로컬 추론.

모델 파일 경로 (R2 기준):
  models/lgbm/entry_model.lgb
  models/lgbm/risk_model.lgb
  models/lgbm/entry_calibrator.pkl
  models/lgbm/risk_calibrator.pkl
  models/lgbm/feature_columns.json
  models/lgbm/model_metrics.json
"""
import asyncio
import json
import logging
import os
from pathlib import Path

import boto3
from botocore.config import Config

logger = logging.getLogger(__name__)

_MODEL_DIR     = Path(os.environ.get("LGBM_MODEL_DIR", "/tmp/models/lgbm"))
_R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "")
_R2_ACCESS_KEY = os.environ.get("R2_ACCESS_KEY", "")
_R2_SECRET_KEY = os.environ.get("R2_SECRET_KEY", "")
_R2_BUCKET     = os.environ.get("R2_BUCKET", "quant-eye-history")

_MODEL_FILES = [
    "entry_model.lgb",
    "risk_model.lgb",
    "entry_calibrator.pkl",
    "risk_calibrator.pkl",
    "feature_columns.json",
    "model_metrics.json",
]

# Lazy init 상태
_lock        = asyncio.Lock()
_initialized = False


def _r2():
    if not _R2_ACCOUNT_ID:
        return None
    return boto3.client(
        "s3",
        endpoint_url=f"https://{_R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=_R2_ACCESS_KEY,
        aws_secret_access_key=_R2_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def download_models() -> bool:
    """R2 -> /tmp/models/lgbm/ 다운로드. 실패 시 False 반환."""
    s3 = _r2()
    if s3 is None:
        logger.warning("R2 credentials not set — ML model not loaded")
        return False

    _MODEL_DIR.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    for fname in _MODEL_FILES:
        key  = f"models/lgbm/{fname}"
        dest = _MODEL_DIR / fname
        if dest.exists():
            downloaded += 1
            continue
        try:
            obj  = s3.get_object(Bucket=_R2_BUCKET, Key=key)
            data = obj["Body"].read()
            dest.write_bytes(data)
            downloaded += 1
            logger.info(f"Model downloaded: {fname}")
        except Exception as e:
            logger.warning(f"Model file not found in R2: {key} ({e})")

    logger.info(f"ML model files: {downloaded}/{len(_MODEL_FILES)}")
    return (downloaded >= 2)  # entry + risk 최소 필요


async def ensure_ready() -> bool:
    """첫 ML 요청 시에만 모델 다운로드 + 로드 (lazy init).

    asyncio.Lock으로 동시 초기화 방지.
    이미 초기화된 경우 즉시 반환(fast path).
    """
    global _initialized
    if _initialized:
        return get_predictor().is_ready()

    async with _lock:
        if _initialized:  # double-checked locking
            return get_predictor().is_ready()

        logger.info("ML 모델 lazy init 시작...")
        loop = asyncio.get_event_loop()
        ok = await loop.run_in_executor(None, download_models)
        if ok:
            get_predictor().load()
        _initialized = True
        logger.info(f"ML 모델 lazy init 완료 (ready={get_predictor().is_ready()})")
        return get_predictor().is_ready()


class LightPredictor:
    """pandas 없는 경량 LightGBM 추론기."""

    def __init__(self):
        self._entry     = None
        self._risk      = None
        self._entry_cal = None
        self._risk_cal  = None
        self._features: list[str] = []
        self.optimal_threshold: float = 0.30

    def load(self) -> bool:
        try:
            import lightgbm as lgb
            import joblib
        except ImportError:
            logger.error("lightgbm / joblib not installed")
            return False

        # feature columns
        fc_path = _MODEL_DIR / "feature_columns.json"
        if fc_path.exists():
            self._features = json.loads(fc_path.read_text())
            logger.info(f"Features loaded: {len(self._features)}")

        # metrics -> optimal_threshold
        mp = _MODEL_DIR / "model_metrics.json"
        if mp.exists():
            m = json.loads(mp.read_text())
            self.optimal_threshold = float(m.get("optimal_threshold", 0.30))

        loaded = False
        for fname, attr in [("entry_model.lgb", "_entry"), ("risk_model.lgb", "_risk")]:
            path = _MODEL_DIR / fname
            if path.exists():
                try:
                    setattr(self, attr, lgb.Booster(model_file=str(path)))
                    loaded = True
                except Exception as e:
                    logger.error(f"Failed to load {fname}: {e}")

        for fname, attr in [("entry_calibrator.pkl", "_entry_cal"),
                             ("risk_calibrator.pkl",  "_risk_cal")]:
            path = _MODEL_DIR / fname
            if path.exists():
                try:
                    setattr(self, attr, joblib.load(str(path)))
                except Exception:
                    pass

        logger.info(f"LightPredictor ready={loaded}, threshold={self.optimal_threshold}")
        return loaded

    def is_ready(self) -> bool:
        return self._entry is not None

    def predict(self, features: dict) -> dict:
        if not self.is_ready():
            return {"success_prob": None, "model_loaded": False}

        X = self._to_array(features)

        prob = self._infer(self._entry, self._entry_cal, X, 0.5)
        risk = self._infer(self._risk,  self._risk_cal,  X, 0.4)

        return {
            "success_prob":    round(prob, 4),
            "risk_score":      round(risk, 4),
            "model_loaded":    True,
            "threshold":       self.optimal_threshold,
        }

    def _to_array(self, features: dict):
        import numpy as np  # lazy — startup 메모리 절약
        row = np.array([[
            float(features.get(c, 0.0) or 0.0) for c in self._features
        ]], dtype=np.float32)
        row = np.where(np.isfinite(row), row, 0.0)
        return row

    def _infer(self, model, calibrator, X, default: float) -> float:
        import numpy as np  # lazy
        if model is None:
            return default
        try:
            raw = float(np.clip(model.predict(X)[0], 0.0, 1.0))
            if calibrator is not None:
                raw = float(np.clip(calibrator.predict([[raw]])[0], 0.0, 1.0))
            return raw
        except Exception as e:
            logger.warning(f"Inference error: {e}")
            return default


# 싱글턴
_predictor: LightPredictor | None = None


def get_predictor() -> LightPredictor:
    global _predictor
    if _predictor is None:
        _predictor = LightPredictor()
    return _predictor
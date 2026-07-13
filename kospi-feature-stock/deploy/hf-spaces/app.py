"""
HF Spaces ML 서비스 — FastAPI
───────────────────────────────
엔드포인트:
  GET  /health          — UptimeRobot 핑 대상
  POST /predict         — LightGBM 성공확률 추론 (Fly.io 데몬용)
  POST /embed           — sentence-transformers 임베딩 생성 (공시/뉴스용)
  GET  /metrics         — 모델 메트릭
  GET  /shap-explain    — SHAP 피처 기여도
"""
import os
import sys
import logging
from pathlib import Path

import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel

sys.path.insert(0, "/app/ml")
sys.path.insert(0, "/app/analyzer")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hf-ml")

app = FastAPI(title="Quant Eye ML Service")

# ── 모델 로딩 (시작 시 1회) ──────────────────────────────────
_MODEL_DIR = os.environ.get("LGBM_MODEL_DIR", "/app/models/lgbm")
_predictor = None
_embedder  = None


def _load_predictor():
    global _predictor
    try:
        from models.lgbm_predictor import LGBMPredictor
        _predictor = LGBMPredictor(model_dir=_MODEL_DIR)
        logger.info("LightGBM 모델 로드 완료")
    except Exception as e:
        logger.error(f"LightGBM 로드 실패: {e}")


def _load_embedder():
    global _embedder
    try:
        from sentence_transformers import SentenceTransformer
        model_name = os.environ.get("EMBEDDING_MODEL_NAME", "jhgan/ko-sroberta-multitask")
        _embedder = SentenceTransformer(model_name)
        logger.info(f"임베딩 모델 로드 완료: {model_name}")
    except Exception as e:
        logger.error(f"임베딩 모델 로드 실패: {e}")


@app.on_event("startup")
async def startup():
    _load_predictor()
    _load_embedder()


# ── 스키마 ────────────────────────────────────────────────────
class PredictRequest(BaseModel):
    code:         str
    event_type:   str
    price:        int
    change_rate:  float
    volume_ratio: float = 0.0
    features:     dict  = {}  # 추가 피처 (선택)


class EmbedRequest(BaseModel):
    texts: list[str]


# ── 엔드포인트 ────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status":    "ok",
        "predictor": _predictor is not None,
        "embedder":  _embedder is not None,
    }


@app.post("/predict")
async def predict(req: PredictRequest):
    if _predictor is None:
        return {"success_prob": None, "error": "model_not_loaded"}
    try:
        result = _predictor.predict_single(
            code=req.code,
            event_type=req.event_type,
            price=req.price,
            change_rate=req.change_rate,
            volume_ratio=req.volume_ratio,
            extra_features=req.features,
        )
        return result
    except Exception as e:
        logger.error(f"predict 오류: {e}")
        return {"success_prob": None, "error": str(e)}


@app.post("/embed")
async def embed(req: EmbedRequest):
    if _embedder is None:
        return {"embeddings": None, "error": "embedder_not_loaded"}
    try:
        vecs = _embedder.encode(req.texts, normalize_embeddings=True)
        return {"embeddings": vecs.tolist()}
    except Exception as e:
        logger.error(f"embed 오류: {e}")
        return {"embeddings": None, "error": str(e)}


@app.get("/metrics")
async def metrics():
    import json
    metrics_path = Path(_MODEL_DIR) / "model_metrics.json"
    if metrics_path.exists():
        return json.loads(metrics_path.read_text())
    return {"error": "metrics_not_found"}


@app.get("/shap-explain")
async def shap_explain():
    if _predictor is None:
        return {"error": "model_not_loaded"}
    try:
        result = _predictor.explain()
        return result
    except Exception as e:
        return {"error": str(e)}

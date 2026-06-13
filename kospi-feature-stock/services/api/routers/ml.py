import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends
import httpx
import redis.asyncio as redis_lib

from deps import get_redis

router = APIRouter()

_MODEL_DIR      = os.environ.get("LGBM_MODEL_DIR", "/models/lgbm")
_ML_SERVICE_URL = os.environ.get("ML_SERVICE_URL", "")
_LAG_TOPICS     = ["tick-data", "minute-bar", "feature-detected", "disclosure", "news"]


@router.get("/metrics")
async def get_model_metrics():
    """모델 메트릭 반환 — ML 서비스 HTTP 우선, 파일 직접 읽기 fallback."""
    # ML 서비스가 설정된 경우 HTTP 프록시
    if _ML_SERVICE_URL:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{_ML_SERVICE_URL}/metrics")
                if resp.status_code == 200:
                    return resp.json()
        except Exception:
            pass  # fallback to file read

    # 공유 볼륨 직접 읽기
    metrics_path = Path(_MODEL_DIR) / "model_metrics.json"
    if not metrics_path.exists():
        return None
    try:
        with open(metrics_path) as f:
            return json.load(f)
    except Exception:
        return None


@router.get("/shap")
async def get_shap():
    """ML 서비스 SHAP 설명 프록시 — 중립 샘플 기준 피처 기여도."""
    if _ML_SERVICE_URL:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{_ML_SERVICE_URL}/shap-explain")
                if resp.status_code == 200:
                    return resp.json()
        except Exception:
            pass
    return {"error": "ml_service_unavailable", "values": []}


@router.get("/kafka-lag")
async def get_kafka_lag(redis: redis_lib.Redis = Depends(get_redis)):
    """Redis에 저장된 Kafka 컨슈머 lag 반환 (detector가 30초마다 갱신)."""
    try:
        total_raw = await redis.get("kafka:lag:total")
        pipe = redis.pipeline()
        for topic in _LAG_TOPICS:
            pipe.get(f"kafka:lag:{topic}")
        vals = await pipe.execute()
        by_topic = {
            t: int(v) for t, v in zip(_LAG_TOPICS, vals) if v is not None
        }
        return {
            "total_lag": int(total_raw) if total_raw else 0,
            "by_topic":  by_topic,
        }
    except Exception as e:
        return {"total_lag": 0, "by_topic": {}, "error": str(e)}
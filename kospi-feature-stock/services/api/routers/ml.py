import json
import os
from pathlib import Path

from fastapi import APIRouter
import httpx

router = APIRouter()

_MODEL_DIR      = os.environ.get("LGBM_MODEL_DIR", "/models/lgbm")
_ML_SERVICE_URL = os.environ.get("ML_SERVICE_URL", "")


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
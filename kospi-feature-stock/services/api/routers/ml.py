import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends, Query
import httpx
import redis.asyncio as redis_lib
import asyncpg

from deps import get_redis, get_db

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


@router.get("/performance-trend")
async def performance_trend(
    days: int = Query(default=30, le=180),
    db: asyncpg.Pool = Depends(get_db),
):
    """일별 추천 승률·수익률 추이 (recommendation_performance 기반)."""
    rows = await db.fetch(
        """
        SELECT
            DATE(rec.created_at AT TIME ZONE 'Asia/Seoul') AS day,
            COUNT(*)                                        AS total,
            COUNT(*) FILTER (WHERE rp.is_success = TRUE)   AS wins,
            ROUND(AVG(rp.r_5d)::NUMERIC, 4)               AS avg_return_5d,
            ROUND(AVG(rp.r_1d)::NUMERIC, 4)               AS avg_return_1d
        FROM recommendations rec
        JOIN recommendation_performance rp ON rp.rec_id = rec.id
        WHERE rp.tracking_complete = TRUE
          AND rec.created_at >= NOW() - ($1 * INTERVAL '1 day')
        GROUP BY 1
        ORDER BY 1
        """,
        days,
    )
    return [
        {
            "day":           str(r["day"]),
            "total":         r["total"],
            "wins":          r["wins"],
            "win_rate":      round(r["wins"] / r["total"] * 100, 1) if r["total"] else 0.0,
            "avg_return_5d": float(r["avg_return_5d"] or 0),
            "avg_return_1d": float(r["avg_return_1d"] or 0),
        }
        for r in rows
    ]


@router.get("/event-performance")
async def event_performance(
    days: int = Query(default=90, le=365),
    db: asyncpg.Pool = Depends(get_db),
):
    """이벤트 유형별 추천 성과 비교."""
    rows = await db.fetch(
        """
        SELECT
            COALESCE(rp.event_type, 'UNKNOWN')              AS event_type,
            COUNT(*)                                         AS total,
            COUNT(*) FILTER (WHERE rp.is_success = TRUE)    AS wins,
            ROUND(AVG(rp.r_5d)::NUMERIC, 2)                AS avg_return_5d,
            ROUND(AVG(rp.r_1d)::NUMERIC, 2)                AS avg_return_1d,
            ROUND(AVG(rec.success_prob)::NUMERIC, 3)        AS avg_pred_prob
        FROM recommendation_performance rp
        JOIN recommendations rec ON rec.id = rp.rec_id
        WHERE rp.tracking_complete = TRUE
          AND rec.created_at >= NOW() - ($1 * INTERVAL '1 day')
        GROUP BY 1
        ORDER BY total DESC
        """,
        days,
    )
    return [
        {
            "event_type":    r["event_type"],
            "total":         r["total"],
            "wins":          r["wins"],
            "win_rate":      round(r["wins"] / r["total"] * 100, 1) if r["total"] else 0.0,
            "avg_return_5d": float(r["avg_return_5d"] or 0),
            "avg_return_1d": float(r["avg_return_1d"] or 0),
            "avg_pred_prob": float(r["avg_pred_prob"] or 0),
        }
        for r in rows
    ]


@router.post("/retrain")
async def trigger_retrain(redis: redis_lib.Redis = Depends(get_redis)):
    """수동 재학습 트리거."""
    if _ML_SERVICE_URL:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(f"{_ML_SERVICE_URL}/retrain")
                if resp.status_code == 200:
                    return resp.json()
        except Exception:
            pass
    # Fallback: Redis 플래그
    await redis.set("ml:retrain_needed", "1", ex=86400)
    await redis.set("ml:retrain_status", "pending", ex=86400)
    return {"status": "queued"}


@router.get("/retrain-status")
async def get_retrain_status(redis: redis_lib.Redis = Depends(get_redis)):
    """재학습 진행 상태 조회."""
    if _ML_SERVICE_URL:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{_ML_SERVICE_URL}/retrain-status")
                if resp.status_code == 200:
                    return resp.json()
        except Exception:
            pass
    pipe = redis.pipeline()
    pipe.get("ml:retrain_status")
    pipe.get("ml:retrain_started_at")
    pipe.get("ml:retrain_finished_at")
    s, started, finished = await pipe.execute()
    return {
        "status":      s.decode() if s else "idle",
        "started_at":  started.decode() if started else None,
        "finished_at": finished.decode() if finished else None,
    }


@router.get("/model-history")
async def model_history(
    db: asyncpg.Pool = Depends(get_db),
):
    """ML 모델 버전 이력 (ml_models 테이블)."""
    rows = await db.fetch(
        """
        SELECT id, model_type, version, trained_at, metrics, is_active
        FROM ml_models
        ORDER BY trained_at DESC
        LIMIT 20
        """,
    )
    result = []
    for r in rows:
        metrics = r["metrics"]
        if isinstance(metrics, str):
            try:
                metrics = json.loads(metrics)
            except Exception:
                metrics = {}
        result.append({
            "id":         r["id"],
            "model_type": r["model_type"],
            "version":    r["version"],
            "trained_at": r["trained_at"].isoformat() if r["trained_at"] else None,
            "metrics":    metrics or {},
            "is_active":  r["is_active"],
        })
    return result
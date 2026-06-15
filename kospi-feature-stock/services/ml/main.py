import asyncio
import logging
import os
import asyncpg
import redis.asyncio as redis_lib
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Counter, Gauge, Histogram
from models.lgbm_predictor import LGBMPredictor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("ml-service")

KST = timezone(timedelta(hours=9))
_MODEL_DIR = os.environ.get("LGBM_MODEL_DIR", "/models/lgbm")

# Prometheus 비즈니스 메트릭
ML_PREDICTIONS_TOTAL = Counter("fstock_ml_predictions_total", "ML 추론 누적 수")
ML_RETRAIN_TOTAL     = Counter("fstock_ml_retrain_total",     "모델 재학습 누적 수")
ML_ENTRY_AUC         = Gauge("fstock_ml_entry_auc",           "Entry 모델 최근 AUC")
ML_RISK_AUC          = Gauge("fstock_ml_risk_auc",            "Risk 모델 최근 AUC")
ML_PREDICT_LATENCY   = Histogram("fstock_ml_predict_latency_seconds", "추론 레이턴시")
ML_RETRAIN_PENDING   = Gauge("fstock_ml_retrain_pending",     "ml:retrain_needed Redis 플래그 (1=대기중)")
ML_MODEL_READY       = Gauge("fstock_ml_model_ready",         "모델 로드 상태 (1=정상)")

# 전역 predictor (HTTP API + 내부 루프 공유)
_predictor: LGBMPredictor | None = None
_db_pool: asyncpg.Pool | None = None
_redis: redis_lib.Redis | None = None


# ── Pydantic 스키마 ────────────────────────────────────────────
class PredictRequest(BaseModel):
    features: dict[str, Any]

class PredictResponse(BaseModel):
    success_prob: float
    risk_score: float
    expected_return: float
    hold_days: int
    confidence: float
    model_used: bool


# ── FastAPI 앱 ─────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _predictor, _db_pool, _redis
    _db_pool = await asyncpg.create_pool(
        dsn=os.environ["POSTGRES_DSN"].replace("+asyncpg", ""),
        min_size=3, max_size=10,
    )
    _redis = redis_lib.from_url(os.environ["REDIS_URL"])
    _predictor = LGBMPredictor()
    _predictor.load()
    logger.info("ML service ready")

    # 백그라운드 루프 시작
    asyncio.create_task(_result_update_loop(_db_pool))
    asyncio.create_task(_weekly_retrain_loop(_db_pool, _predictor))
    asyncio.create_task(_redis_retrain_loop(_db_pool, _predictor, _redis))
    yield
    if _db_pool:
        await _db_pool.close()
    if _redis:
        await _redis.aclose()


app = FastAPI(lifespan=lifespan)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


@app.get("/health")
async def health():
    retrain_pending = False
    if _redis:
        try:
            retrain_pending = bool(await _redis.get("ml:retrain_needed"))
        except Exception:
            pass
    model_ready = _predictor.is_ready() if _predictor else False
    ML_RETRAIN_PENDING.set(1 if retrain_pending else 0)
    ML_MODEL_READY.set(1 if model_ready else 0)
    return {
        "status": "ok",
        "model_loaded":    model_ready,
        "retrain_pending": retrain_pending,
    }


@app.post("/predict", response_model=PredictResponse)
async def predict(req: PredictRequest):
    """피처 딕셔너리 → ML 추론 결과."""
    if _predictor is None or not _predictor.is_ready():
        return PredictResponse(
            success_prob=0.5, risk_score=0.4,
            expected_return=0.0, hold_days=5,
            confidence=0.0, model_used=False,
        )
    import time
    with ML_PREDICT_LATENCY.time():
        result = _predictor.predict_one(req.features)
    ML_PREDICTIONS_TOTAL.inc()
    return PredictResponse(
        success_prob=result.success_prob,
        risk_score=result.risk_score,
        expected_return=result.expected_return,
        hold_days=result.hold_days,
        confidence=result.confidence,
        model_used=result.model_loaded,
    )


@app.get("/metrics")
async def get_metrics():
    """학습된 모델 메트릭 반환 (model_metrics.json)."""
    import json
    metrics_path = Path(_MODEL_DIR) / "model_metrics.json"
    if not metrics_path.exists():
        return {"error": "model_metrics.json not found", "model_loaded": False}
    try:
        with open(metrics_path) as f:
            return json.load(f)
    except Exception as e:
        return {"error": str(e)}

@app.post("/reload")
async def reload_model():
    """재학습 완료 후 모델 핫스왑 (atomic)."""
    if _predictor is None:
        return {"status": "error", "message": "predictor not initialized"}
    loaded = _predictor.load()
    logger.info(f"[API] Model reloaded: {loaded}")
    return {"status": "ok", "model_loaded": loaded}


@app.get("/shap-explain")
async def shap_explain():
    """entry 모델 기준 SHAP 피처 기여도 — 중립 샘플(all-zero) 기준."""
    if _predictor is None or not _predictor.is_ready():
        return {"error": "model_not_loaded", "values": []}
    try:
        import shap
        import numpy as np
        import pandas as pd
        from models.lgbm_predictor import FEATURE_COLUMNS

        # 중립 샘플: RSI·MA ratio 등 중립값 설정, 나머지 0
        neutral = {col: 0.0 for col in FEATURE_COLUMNS}
        neutral.update({
            "rsi14":       50.0,
            "ma5_ratio":   1.0,
            "ma20_ratio":  1.0,
            "ma60_ratio":  1.0,
            "bb_pct":      0.5,
            "pos_52w":     0.5,
        })
        X = pd.DataFrame([neutral])[FEATURE_COLUMNS].fillna(0.0)

        explainer  = shap.TreeExplainer(_predictor._entry)
        shap_vals  = explainer.shap_values(X)
        # TreeExplainer returns ndarray (n_samples, n_features) for binary
        if isinstance(shap_vals, list):
            shap_arr = shap_vals[1][0]    # positive class
        else:
            shap_arr = shap_vals[0]

        base_value = float(
            explainer.expected_value[1]
            if isinstance(explainer.expected_value, (list, np.ndarray))
            else explainer.expected_value
        )

        items = [
            {"feature": f, "shap": round(float(v), 6)}
            for f, v in zip(FEATURE_COLUMNS, shap_arr)
        ]
        items.sort(key=lambda x: abs(x["shap"]), reverse=True)
        return {
            "base_value": round(base_value, 6),
            "values":     items[:25],
            "note":       "neutral_sample",
        }
    except Exception as e:
        logger.warning(f"SHAP explain error: {e}")
        return {"error": str(e), "values": []}


async def run():
    import uvicorn
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("ML_API_PORT", "8001")),
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def _result_update_loop(pool: asyncpg.Pool):
    while True:
        try:
            await _update_event_results(pool)
        except Exception as e:
            logger.error(f"Result update error: {e}")
        await asyncio.sleep(3600)


async def _redis_retrain_loop(
    pool: asyncpg.Pool,
    predictor: LGBMPredictor,
    redis: redis_lib.Redis,
):
    """10분마다 ml:retrain_needed 플래그를 폴링하여 직접 재학습 트리거."""
    while True:
        await asyncio.sleep(600)  # 10분
        try:
            flag = await redis.get("ml:retrain_needed")
            if not flag:
                continue
            logger.info("[Redis] ml:retrain_needed 플래그 감지 — 재학습 시작")
            await redis.delete("ml:retrain_needed")  # 중복 트리거 방지
            try:
                await _run_retrain(pool, predictor)
                logger.info("[Redis] Redis 트리거 재학습 완료")
            except Exception as e:
                logger.error(f"[Redis] 재학습 실패: {e}")
        except Exception as e:
            logger.error(f"[Redis] 폴링 오류: {e}")


async def _weekly_retrain_loop(pool: asyncpg.Pool, predictor: LGBMPredictor):
    """매주 일요일 02:00 KST에 모델 재학습."""
    retrain_done_today = False
    while True:
        now = datetime.now(KST)
        # 일요일(weekday=6) 02:00에 1회 실행
        if now.weekday() == 6 and now.hour == 2 and not retrain_done_today:
            logger.info("Weekly retrain started")
            try:
                await _run_retrain(pool, predictor)
                retrain_done_today = True
            except Exception as e:
                logger.error(f"Weekly retrain failed, keeping existing model: {e}")
        elif now.weekday() != 6:
            retrain_done_today = False
        await asyncio.sleep(600)  # 10분마다 체크


async def _run_retrain(pool: asyncpg.Pool, predictor: LGBMPredictor):
    """walk_forward_train.py 서브프로세스를 실행하여 모델을 재학습.
    수동 학습(make train)과 동일한 파이프라인 사용 — feature schema 불일치 방지.
    """
    import subprocess
    import sys
    end_dt   = date.today()
    # walk-forward 분할: 최근 2년 train / 최근 6개월 val / 최근 90일 test
    train_end   = (end_dt - timedelta(days=180)).isoformat()
    val_start   = (end_dt - timedelta(days=180)).isoformat()
    val_end     = (end_dt - timedelta(days=90)).isoformat()
    test_start  = (end_dt - timedelta(days=90)).isoformat()
    test_end    = end_dt.isoformat()
    train_start = (end_dt - timedelta(days=730)).isoformat()

    cmd = [
        sys.executable, "/app/walk_forward_train.py",
        "--train-start", train_start, "--train-end", train_end,
        "--val-start",   val_start,   "--val-end",   val_end,
        "--test-start",  test_start,  "--test-end",  test_end,
        "--smote", "--model-dir", _MODEL_DIR, "--max-codes", "400",
    ]
    logger.info(f"[Retrain] walk_forward_train.py 시작: {train_start} ~ {test_end}")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    log_tail = (stdout or b"").decode(errors="replace").strip().splitlines()[-10:]
    for line in log_tail:
        logger.info(f"[Retrain] {line}")

    if proc.returncode != 0:
        logger.error(f"[Retrain] walk_forward_train.py 실패 (exit={proc.returncode})")
        return

    # 학습 완료 → 핫스왑
    if predictor is not None:
        loaded = predictor.load()
        logger.info(f"[Retrain] 모델 핫스왑: loaded={loaded}")

    # Prometheus 메트릭 업데이트 (model_metrics.json에서 읽기)
    import json as _json
    metrics_path = Path(_MODEL_DIR) / "model_metrics.json"
    if metrics_path.exists():
        try:
            m = _json.loads(metrics_path.read_text())
            ML_ENTRY_AUC.set(float(m.get("auc", 0)))
        except Exception:
            pass
    ML_RETRAIN_TOTAL.inc()
    logger.info("[Retrain] 완료")


async def _update_event_results(pool: asyncpg.Pool):
    """feature_events의 result_1d/3d/5d를 daily_bars 기준으로 계산."""
    intervals = [
        (1,  "result_1d"),
        (3,  "result_3d"),
        (5,  "result_5d"),
    ]

    total_updated = 0
    async with pool.acquire() as conn:
        for days, col in intervals:
            # 해당 일수 이상 경과했고 result가 NULL인 이벤트 (최대 1000개)
            rows = await conn.fetch(f"""
                SELECT fe.id, fe.code, fe.price AS entry_price, fe.detected_at
                FROM feature_events fe
                WHERE fe.detected_at <= NOW() - INTERVAL '{days} days'
                  AND fe.{col} IS NULL
                ORDER BY fe.detected_at DESC
                LIMIT 1000
            """)

            if not rows:
                continue

            updated = 0
            for row in rows:
                target_date = row['detected_at'] + timedelta(days=days)
                bar = await conn.fetchrow("""
                    SELECT close FROM daily_bars
                    WHERE code = $1 AND date <= $2
                    ORDER BY date DESC LIMIT 1
                """, row['code'], target_date.date())

                if bar and row['entry_price'] and row['entry_price'] > 0:
                    result_pct = (bar['close'] - row['entry_price']) / row['entry_price'] * 100
                    await conn.execute(
                        f"UPDATE feature_events SET {col} = $1 WHERE id = $2",
                        round(result_pct, 4), row['id']
                    )
                    updated += 1

            total_updated += updated
            if updated > 0:
                logger.info(f"result 업데이트: {col} {updated}개 완료")

    if total_updated > 0:
        logger.info(f"전체 result 업데이트 완료: {total_updated}개")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("ML_API_PORT", "8001")),
        log_level="info",
    )

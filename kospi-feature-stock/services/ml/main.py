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
from models.lgbm_predictor import LGBMPredictor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("ml-service")

KST = timezone(timedelta(hours=9))
_MODEL_DIR = os.environ.get("LGBM_MODEL_DIR", "/models/lgbm")

# 전역 predictor (HTTP API + 내부 루프 공유)
_predictor: LGBMPredictor | None = None
_db_pool: asyncpg.Pool | None = None


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
    global _predictor, _db_pool
    _db_pool = await asyncpg.create_pool(
        dsn=os.environ["POSTGRES_DSN"].replace("+asyncpg", ""),
        min_size=3, max_size=10,
    )
    _predictor = LGBMPredictor()
    _predictor.load()
    logger.info("ML service ready")

    # 백그라운드 루프 시작
    asyncio.create_task(_result_update_loop(_db_pool))
    asyncio.create_task(_weekly_retrain_loop(_db_pool, _predictor))
    yield
    if _db_pool:
        await _db_pool.close()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model_loaded": _predictor.is_ready() if _predictor else False,
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
    result = _predictor.predict_one(req.features)
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
    import sys
    sys.path.insert(0, "/app")
    import pandas as pd
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.metrics import roc_auc_score, brier_score_loss
    from features.technical import TechnicalFeatureExtractor
    from features.supply_demand import SupplyDemandFeatureExtractor
    from models.lgbm_predictor import FEATURE_COLUMNS
    from models.trainer import LGBMTrainer

    end_dt   = date.today()
    start_dt = end_dt - timedelta(days=730)  # 최근 2년

    rows = await pool.fetch(
        """
        SELECT
            db.date::TEXT AS date, db.code,
            db.open, db.high, db.low, db.close,
            db.volume, db.amount, db.change_rate,
            db.short_sell_vol,
            COALESCE(sd.foreign_net, db.foreign_net_buy) AS foreign_net,
            COALESCE(sd.inst_net,    db.inst_net_buy)    AS inst_net,
            COALESCE(sd.indiv_net,   db.indiv_net_buy)   AS indiv_net
        FROM daily_bars db
        LEFT JOIN supply_demand sd ON sd.code=db.code AND sd.date=db.date
        WHERE db.date BETWEEN $1 AND $2
        ORDER BY db.code, db.date
        """,
        start_dt, end_dt,
    )
    if not rows:
        logger.warning("No data for retrain, skipping")
        return

    raw = pd.DataFrame([dict(r) for r in rows])

    # KOSPI 지수 데이터 로드
    kospi_rows = await pool.fetch(
        "SELECT date::TEXT AS date, close, volume FROM daily_bars "
        "WHERE code='0001' AND date BETWEEN $1 AND $2 ORDER BY date",
        start_dt, end_dt,
    )
    kospi_close  = pd.Series({r["date"]: float(r["close"])  for r in kospi_rows}) if kospi_rows else pd.Series(dtype=float)
    market_vol   = pd.Series({r["date"]: float(r["volume"]) for r in kospi_rows}) if kospi_rows else pd.Series(dtype=float)

    logger.info(f"Retrain data: {len(raw)} rows, {raw['code'].nunique()} stocks, KOSPI={len(kospi_close)} days")

    tech = TechnicalFeatureExtractor()
    sd   = SupplyDemandFeatureExtractor()
    tr   = LGBMTrainer()

    all_feat, all_label_e, all_label_r = [], [], []
    for code, grp in raw.groupby("code"):
        grp = grp.sort_values("date").reset_index(drop=True)
        if len(grp) < 80:
            continue
        try:
            f = tech.extract(grp)
            f = sd.extract(f)
            if len(kospi_close) > 0:
                f = tech.inject_market_features(f, kospi_close, market_vol if len(market_vol) > 0 else None)
            f["code"] = code
            all_feat.append(f)
            all_label_e.append(tr.make_label_entry(f, fwd=5, thr=0.05))
            all_label_r.append(tr.make_label_risk(f,   fwd=5, loss=-0.05))
        except Exception as e:
            logger.debug(f"Feature error {code}: {e}")

    if not all_feat:
        logger.warning("No valid features for retrain")
        return

    df = pd.concat(all_feat).reset_index(drop=True)
    le = pd.concat(all_label_e).reset_index(drop=True)
    lr = pd.concat(all_label_r).reset_index(drop=True)

    mask = le.notna() & lr.notna()
    df, le, lr = df[mask], le[mask], lr[mask]
    for col in FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = 0.0
    X = df[FEATURE_COLUMNS].fillna(0)

    tscv = TimeSeriesSplit(n_splits=5)
    sp = list(tscv.split(X))
    ti, vi = sp[-1]
    X_tr, X_va = X.iloc[ti], X.iloc[vi]
    le_tr, le_va = le.iloc[ti], le.iloc[vi]
    lr_tr, lr_va = lr.iloc[ti], lr.iloc[vi]

    tmp_dir = Path(_MODEL_DIR) / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    entry_m = tr.train_entry(X_tr, le_tr, X_va, le_va, str(tmp_dir))
    risk_m  = tr.train_risk(X_tr,  lr_tr, X_va, lr_va, str(tmp_dir))

    entry_raw = entry_m.predict_proba(X_va)[:, 1]
    risk_raw  = risk_m.predict_proba(X_va)[:, 1]
    auc_e     = roc_auc_score(le_va, entry_raw)
    auc_r     = roc_auc_score(lr_va, risk_raw)
    brier_e   = brier_score_loss(le_va, entry_raw)
    brier_r   = brier_score_loss(lr_va, risk_raw)

    # atomic 교체 (tmp → 실제 경로)
    model_dir = Path(_MODEL_DIR)
    for fname in ["entry_model.lgb", "risk_model.lgb", "entry_calibrator.pkl", "risk_calibrator.pkl"]:
        src = tmp_dir / fname
        if src.exists():
            src.rename(model_dir / fname)

    # atomic 교체 완료 후 전역 predictor 핫스왑
    if _predictor is not None:
        _predictor.load()
    logger.info(f"Weekly retrain done, Entry AUC={auc_e:.4f} Brier={brier_e:.4f}, Risk AUC={auc_r:.4f} Brier={brier_r:.4f}")


async def _update_event_results(pool: asyncpg.Pool):
    """1시간마다 feature_events의 result_1d/3d/5d 사후 업데이트."""
    cutoff = datetime.now() - timedelta(hours=1)

    async with pool.acquire() as conn:
        events = await conn.fetch(
            """
            SELECT id, code, detected_at::TEXT AS dt
            FROM feature_events
            WHERE result_1d IS NULL
              AND detected_at < $1
            LIMIT 200
            """,
            cutoff,
        )
        for ev in events:
            code   = ev["code"]
            dt_obj = date.fromisoformat(ev["dt"][:10])
            rows = await conn.fetch(
                """
                SELECT date::TEXT, close
                FROM daily_bars
                WHERE code = $1 AND date >= $2
                ORDER BY date
                LIMIT 6
                """,
                code, dt_obj,
            )
            if len(rows) >= 2:
                entry = float(rows[0]["close"])
                def ret(n):
                    if len(rows) > n:
                        return round((float(rows[n]["close"]) - entry) / entry * 100, 2)
                    return None
                await conn.execute(
                    """
                    UPDATE feature_events
                    SET result_1d=$2, result_3d=$3, result_5d=$4
                    WHERE id=$1
                    """,
                    ev["id"], ret(1), ret(3), ret(5),
                )

    logger.info(f"Updated results for {len(events)} events")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("ML_API_PORT", "8001")),
        log_level="info",
    )

from fastapi import APIRouter, Depends, BackgroundTasks
import asyncpg
import redis.asyncio as redis_lib
import asyncio
import json
import logging
import os
from pathlib import Path
from deps import get_db, get_redis

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)

_MODEL_DIR = Path(os.environ.get("LGBM_MODEL_DIR", "/models/lgbm"))


@router.get("/system-status")
async def system_status(
    db: asyncpg.Pool = Depends(get_db),
    redis: redis_lib.Redis = Depends(get_redis),
):
    """전체 시스템 상태를 한 번에 반환 (ML 모델 상태 + 데이터 신선도 + 서비스 헬스)."""
    # ML 모델 파일 확인
    model_loaded  = (_MODEL_DIR / "entry_model.lgb").exists()
    model_metrics: dict = {}
    if (_MODEL_DIR / "model_metrics.json").exists():
        try:
            model_metrics = json.loads((_MODEL_DIR / "model_metrics.json").read_text())
        except Exception:
            pass

    # 데이터 신선도 + 카운트
    async with db.acquire() as conn:
        freshness = await conn.fetchrow("""
            SELECT
                (SELECT MAX(date)::TEXT            FROM daily_bars)                       AS latest_bar,
                (SELECT MAX(detected_at)::TEXT     FROM feature_events)                   AS latest_event,
                (SELECT MAX(created_at)::TEXT      FROM recommendations)                  AS latest_rec,
                (SELECT MAX(disclosed_at)::TEXT    FROM disclosures)                      AS latest_disc,
                (SELECT COUNT(*)                   FROM stocks      WHERE is_active)       AS stock_count,
                (SELECT COUNT(*)                   FROM daily_bars)                       AS bar_count,
                (SELECT COUNT(*)                   FROM feature_events)                   AS event_count,
                (SELECT COUNT(*) FROM feature_events WHERE pattern_vector IS NOT NULL)    AS vector_count,
                (SELECT COUNT(*)                   FROM recommendations)                  AS rec_count,
                (SELECT COUNT(*)                   FROM disclosures)                      AS disc_count
        """)

    ev  = int(freshness["event_count"] or 0)
    vec = int(freshness["vector_count"] or 0)
    bar_count = int(freshness["bar_count"] or 0)

    # Redis 연결 확인
    redis_ok = False
    try:
        await redis.ping()
        redis_ok = True
    except Exception:
        pass

    # Kafka lag (Redis에 탐지기가 기록한 값 사용)
    kafka_lags: dict = {}
    for topic in ["feature-detected", "recommendation", "disclosure", "minute-bar"]:
        try:
            v = await redis.get(f"kafka:lag:{topic}")
            kafka_lags[topic] = int(v or 0)
        except Exception:
            kafka_lags[topic] = -1

    return {
        "ml": {
            "model_loaded":   model_loaded,
            "model_dir":      str(_MODEL_DIR),
            "trained_at":     model_metrics.get("trained_at"),
            "auc":            model_metrics.get("auc"),
            "f1":             model_metrics.get("f1"),
            "optimal_threshold": model_metrics.get("optimal_threshold"),
        },
        "data": {
            "latest_daily_bar":       freshness["latest_bar"],
            "latest_feature_event":   freshness["latest_event"],
            "latest_recommendation":  freshness["latest_rec"],
            "latest_disclosure":      freshness["latest_disc"],
            "stock_count":            int(freshness["stock_count"] or 0),
            "bar_count":              bar_count,
            "event_count":            ev,
            "vector_count":           vec,
            "rec_count":              int(freshness["rec_count"] or 0),
            "disc_count":             int(freshness["disc_count"] or 0),
            "pattern_vector_coverage": round(vec / ev * 100, 1) if ev > 0 else 0.0,
        },
        "services": {
            "db":    True,
            "redis": redis_ok,
        },
        "kafka_lag": kafka_lags,
    }


@router.get("/bootstrap-status")
async def bootstrap_status(
    db: asyncpg.Pool = Depends(get_db),
    redis: redis_lib.Redis = Depends(get_redis),
):
    """Bootstrap 각 단계 완료 여부를 상세히 반환."""
    async with db.acquire() as conn:
        stats = await conn.fetchrow("""
            SELECT
                (SELECT COUNT(*) FROM stocks WHERE is_active)                              AS stock_count,
                (SELECT COUNT(*) FROM daily_bars
                 WHERE date >= NOW() - INTERVAL '365 days')                                AS bar_count,
                (SELECT COUNT(*) FROM daily_bars WHERE rsi14 IS NOT NULL)                  AS indicator_count,
                (SELECT COUNT(*) FROM feature_events)                                      AS event_count,
                (SELECT COUNT(*) FROM feature_events WHERE pattern_vector IS NOT NULL)     AS vector_count
        """)

    model_loaded  = (_MODEL_DIR / "entry_model.lgb").exists()
    model_metrics: dict = {}
    if (_MODEL_DIR / "model_metrics.json").exists():
        try:
            model_metrics = json.loads((_MODEL_DIR / "model_metrics.json").read_text())
        except Exception:
            pass

    sc  = int(stats["stock_count"]     or 0)
    bc  = int(stats["bar_count"]       or 0)
    ic  = int(stats["indicator_count"] or 0)
    ec  = int(stats["event_count"]     or 0)
    vc  = int(stats["vector_count"]    or 0)

    logs_raw = await redis.lrange("bootstrap:log", 0, 49)
    logs = [l.decode() if isinstance(l, bytes) else l for l in logs_raw]

    return {
        "steps": [
            {
                "id": "load_stocks", "label": "종목 마스터 로딩",
                "done": sc >= 1000, "count": sc, "target": 2500,
                "detail": f"{sc:,}개 종목 등록됨",
            },
            {
                "id": "fetch_bars", "label": "과거 일봉 수집 (1년)",
                "done": bc >= 500_000, "count": bc, "target": 1_000_000,
                "detail": f"{bc:,}개 봉 수집됨",
            },
            {
                "id": "compute_indicators", "label": "기술적 지표 계산",
                "done": ic >= bc * 0.85 if bc > 0 else False,
                "count": ic, "target": bc,
                "detail": f"{ic:,}개 완료",
            },
            {
                "id": "backfill_events", "label": "특징주 이벤트 역산",
                "done": ec >= 10_000, "count": ec, "target": 50_000,
                "detail": f"{ec:,}개 이벤트",
            },
            {
                "id": "train_model", "label": "ML 모델 학습",
                "done": model_loaded, "count": None, "target": None,
                "detail": (
                    f"AUC {model_metrics.get('auc','?')} / F1 {model_metrics.get('f1','?')}"
                    if model_loaded else "미학습"
                ),
            },
            {
                "id": "generate_vectors", "label": "패턴 벡터 생성",
                "done": ec > 0 and vc >= ec * 0.75,
                "count": vc, "target": ec,
                "detail": f"커버리지 {round(vc/max(ec,1)*100)}%",
            },
        ],
        "logs": logs,
        "overall_ok": sc >= 1000 and bc >= 500_000 and model_loaded and (ec > 0 and vc >= ec * 0.75),
    }


@router.post("/bootstrap/load-stocks")
async def run_load_stocks(
    background_tasks: BackgroundTasks,
    redis: redis_lib.Redis = Depends(get_redis),
):
    background_tasks.add_task(_run_make_target, redis, "load-stocks", "종목 데이터 로드")
    return {"status": "started", "step": "load-stocks"}


@router.post("/bootstrap/fetch-historical")
async def run_fetch_historical(
    background_tasks: BackgroundTasks,
    redis: redis_lib.Redis = Depends(get_redis),
):
    background_tasks.add_task(_run_make_target, redis, "stats", "과거 일봉 통계 수집")
    return {"status": "started", "step": "fetch-historical"}


@router.post("/bootstrap/train-model")
async def run_train_model(
    background_tasks: BackgroundTasks,
    redis: redis_lib.Redis = Depends(get_redis),
):
    background_tasks.add_task(_run_make_target, redis, "train", "ML 모델 학습")
    return {"status": "started", "step": "train-model"}


@router.post("/bootstrap/backfill-vectors")
async def run_backfill_vectors(
    background_tasks: BackgroundTasks,
    redis: redis_lib.Redis = Depends(get_redis),
):
    background_tasks.add_task(_run_backfill_vectors, redis)
    return {"status": "started", "step": "backfill-vectors"}


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

async def _log(redis: redis_lib.Redis, msg: str) -> None:
    from datetime import datetime
    entry = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    await redis.lpush("bootstrap:log", entry)
    await redis.ltrim("bootstrap:log", 0, 99)
    logger.info(msg)


async def _run_make_target(redis: redis_lib.Redis, target: str, label: str) -> None:
    await _log(redis, f"{label} 시작...")
    try:
        proc = await asyncio.create_subprocess_exec(
            "make", target,
            cwd="/app",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            await _log(redis, f"완료: {label}")
        else:
            await _log(redis, f"실패: {label} — {stdout.decode()[:200]}")
    except Exception as e:
        await _log(redis, f"오류: {label} — {str(e)[:200]}")


async def _run_backfill_vectors(redis: redis_lib.Redis) -> None:
    await _log(redis, "패턴 벡터 백필 시작...")
    try:
        proc = await asyncio.create_subprocess_exec(
            "python", "-m", "ml.scripts.backfill_vectors",
            cwd="/app",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            await _log(redis, "완료: 패턴 벡터 백필")
        else:
            await _log(redis, f"실패: 벡터 백필 — {stdout.decode()[:200]}")
    except Exception as e:
        await _log(redis, f"오류: 벡터 백필 — {str(e)[:200]}")

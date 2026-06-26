from fastapi import APIRouter, Depends, BackgroundTasks, Query
from pydantic import BaseModel
from typing import Optional
import asyncpg
import redis.asyncio as redis_lib
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
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
    """전체 시스템 상태 (ML 모델 + 데이터 신선도 + 서비스 헬스)."""
    model_loaded = (_MODEL_DIR / "entry_model.lgb").exists()
    model_metrics: dict = {}
    if (_MODEL_DIR / "model_metrics.json").exists():
        try:
            model_metrics = json.loads((_MODEL_DIR / "model_metrics.json").read_text())
        except Exception:
            pass

    # 데이터 신선도 — 대용량 테이블은 approximate_row_count() 사용 (TimescaleDB 통계 기반)
    async with db.acquire() as conn:
        freshness = await conn.fetchrow("""
            SELECT
                (SELECT MAX(date)::TEXT            FROM daily_bars)                       AS latest_bar,
                (SELECT MAX(detected_at)::TEXT     FROM feature_events)                   AS latest_event,
                (SELECT MAX(created_at)::TEXT      FROM recommendations)                  AS latest_rec,
                (SELECT MAX(disclosed_at)::TEXT    FROM disclosures)                      AS latest_disc,
                (SELECT COUNT(*)                   FROM stocks      WHERE is_active)       AS stock_count,
                approximate_row_count('daily_bars')                                        AS bar_count,
                approximate_row_count('feature_events')                                    AS event_count,
                (SELECT COUNT(*)                   FROM recommendations)                  AS rec_count,
                (SELECT COUNT(*)                   FROM disclosures)                      AS disc_count
        """)

    ev        = int(freshness["event_count"] or 0)
    bar_count = int(freshness["bar_count"] or 0)

    # DB health check (실제 ping)
    db_ok = False
    try:
        async with db.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_ok = True
    except Exception:
        pass

    # Redis 연결 확인
    redis_ok = False
    try:
        await redis.ping()
        redis_ok = True
    except Exception:
        pass

    # Redis 통계 키 카운트 + vector_count 캐시 조회 (SCAN 50k키 순회 제거)
    stats_key_count = 0
    vec = 0
    try:
        rc = await redis.get("stats:refresh_count")
        vc = await redis.get("stats:vector_count")
        stats_key_count = int(rc or 0)
        vec = int(vc or 0)
    except Exception:
        pass

    # Redis 재시작 등으로 stats:vector_count 키가 없으면 DB에서 직접 조회 후 캐시 복구
    if vec == 0 and ev > 0:
        try:
            vec_db = await db.fetchval(
                "SELECT COUNT(*) FROM feature_events WHERE pattern_vector IS NOT NULL"
            )
            vec = int(vec_db or 0)
            if vec > 0:
                await redis.set("stats:vector_count", vec, ex=60 * 60 * 72)
        except Exception as e:
            logger.warning(f"vector_count fallback failed: {e}")

    # ML 모드: 모델 로드 여부
    model_mode = "ml" if model_loaded else "fallback"

    # Kafka lag (Redis에 탐지기가 기록한 값)
    kafka_lags: dict = {}
    for topic in ["feature-detected", "recommendation", "disclosure", "minute-bar"]:
        try:
            v = await redis.get(f"kafka:lag:{topic}")
            kafka_lags[topic] = int(v or 0)
        except Exception:
            kafka_lags[topic] = -1

    return {
        "ml": {
            "model_loaded":      model_loaded,
            "model_mode":        model_mode,
            "model_dir":         str(_MODEL_DIR),
            "trained_at":        model_metrics.get("trained_at"),
            "auc":               model_metrics.get("auc"),
            "f1":                model_metrics.get("f1"),
            "optimal_threshold": model_metrics.get("optimal_threshold"),
        },
        "data": {
            "latest_daily_bar":        freshness["latest_bar"],
            "latest_feature_event":    freshness["latest_event"],
            "latest_recommendation":   freshness["latest_rec"],
            "latest_disclosure":       freshness["latest_disc"],
            "stock_count":             int(freshness["stock_count"] or 0),
            "bar_count":               bar_count,
            "event_count":             ev,
            "vector_count":            vec,
            "rec_count":               int(freshness["rec_count"] or 0),
            "disc_count":              int(freshness["disc_count"] or 0),
            "pattern_vector_coverage": round(vec / ev * 100, 1) if ev > 0 else 0.0,
            "redis_stats_count":       stats_key_count,
        },
        "services": {
            "db":    db_ok,
            "redis": redis_ok,
        },
        "kafka_lag": kafka_lags,
    }


@router.get("/bootstrap-status")
async def bootstrap_status(
    db: asyncpg.Pool = Depends(get_db),
    redis: redis_lib.Redis = Depends(get_redis),
):
    """Bootstrap 각 단계 완료 여부 (7단계)."""
    async with db.acquire() as conn:
        stats = await conn.fetchrow("""
            SELECT
                (SELECT COUNT(*) FROM stocks WHERE is_active)                              AS stock_count,
                (SELECT COUNT(*) FROM daily_bars
                 WHERE date >= NOW() - INTERVAL '365 days')                                AS bar_count,
                approximate_row_count('daily_bars')                                        AS indicator_count,
                approximate_row_count('feature_events')                                    AS event_count
        """)

    model_loaded = (_MODEL_DIR / "entry_model.lgb").exists()
    model_metrics: dict = {}
    if (_MODEL_DIR / "model_metrics.json").exists():
        try:
            model_metrics = json.loads((_MODEL_DIR / "model_metrics.json").read_text())
        except Exception:
            pass

    sc = int(stats["stock_count"]     or 0)
    bc = int(stats["bar_count"]       or 0)
    ic = int(stats["indicator_count"] or 0)
    ec = int(stats["event_count"]     or 0)

    # vector_count와 stats_key_count는 Redis 캐시에서 즉시 조회
    vc = 0
    stats_key_count = 0
    try:
        rc = await redis.get("stats:refresh_count")
        vc_v = await redis.get("stats:vector_count")
        stats_key_count = int(rc or 0)
        vc = int(vc_v or 0)
    except Exception:
        pass

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
                "id": "refresh_stats", "label": "Redis 탐지 통계 초기화",
                "done": stats_key_count >= 1000,
                "count": stats_key_count, "target": sc * 7 if sc > 0 else 17500,
                "detail": f"{stats_key_count:,}개 통계 키 적재됨 (종목당 7개)",
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
                    if model_loaded else "미학습 — 규칙 기반 fallback 운영 중"
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
        "overall_ok": (
            sc >= 1000 and bc >= 500_000 and
            stats_key_count >= 1000 and
            model_loaded and
            ec > 0 and vc >= ec * 0.75
        ),
    }


@router.get("/data-quality")
async def data_quality(
    db:    asyncpg.Pool    = Depends(get_db),
    redis: redis_lib.Redis = Depends(get_redis),
):
    """데이터 품질 대시보드: 일봉 완성도·수급 커버리지·ML 신뢰도.
    Redis에 5분 캐시하여 대용량 COUNT DISTINCT 쿼리 반복 수행을 방지."""
    _cache_key = "cache:data_quality"
    _model_dir = Path(os.environ.get("LGBM_MODEL_DIR", "/models/lgbm"))

    # Redis 캐시 확인
    try:
        cached = await redis.get(_cache_key)
        if cached:
            return json.loads(cached)
    except Exception:
        pass

    async with db.acquire() as conn:
        # 빠른 집계: approximate_row_count + COUNT DISTINCT (인덱스 활용)
        stats = await conn.fetchrow(
            """
            SELECT
                (SELECT COUNT(*) FROM stocks WHERE is_active)                                   AS active_stocks,
                (SELECT COUNT(DISTINCT code) FROM daily_bars WHERE date >= CURRENT_DATE - 7)    AS bars_last7d,
                (SELECT MAX(date)::TEXT FROM daily_bars)                                        AS latest_bar,
                (SELECT COUNT(DISTINCT code) FROM daily_bars WHERE date >= CURRENT_DATE - 1)    AS bars_today,
                (SELECT COUNT(DISTINCT code) FROM supply_demand WHERE date >= CURRENT_DATE - 7) AS sd_last7d,
                (SELECT COUNT(DISTINCT code) FROM supply_demand WHERE date >= CURRENT_DATE - 30)AS sd_last30d,
                (SELECT MAX(date)::TEXT FROM supply_demand)                                     AS latest_sd,
                approximate_row_count('feature_events')                                         AS event_count
            """
        )

        # 벡터 커버리지 — Redis 캐시(stats:vector_count) 우선, 없으면 approximate
        vec_count_raw = int(stats["event_count"] or 0)
        vec_count_filled_raw = await conn.fetchval(
            "SELECT COUNT(*) FROM feature_events WHERE pattern_vector IS NOT NULL LIMIT 5000"
        )

        sd_missing = None  # 아래에서 active - sd_30d 로 계산
        missing_bars: list = []  # 샘플은 별도 엔드포인트로 분리 (성능)

    active     = int(stats["active_stocks"] or 0)
    bars_7d    = int(stats["bars_last7d"]   or 0)
    bars_today = int(stats["bars_today"]    or 0)
    sd_7d      = int(stats["sd_last7d"]     or 0)
    sd_30d     = int(stats["sd_last30d"]    or 0)
    ev_count   = int(stats["event_count"]   or 0)
    vec_filled = int(vec_count_filled_raw or 0)
    vec_count  = int(vec_count_raw or 0)
    vec_pct    = round(vec_filled / min(vec_count, 5000) * 100, 1) if vec_count > 0 and vec_filled < 5000 else (100.0 if vec_filled >= 5000 else 0.0)

    # ML 신뢰도
    ml_metrics: dict = {}
    if (_model_dir / "model_metrics.json").exists():
        try:
            ml_metrics = json.loads((_model_dir / "model_metrics.json").read_text())
        except Exception:
            pass

    model_age_days: int | None = None
    if ml_metrics.get("trained_at"):
        try:
            trained = datetime.fromisoformat(ml_metrics["trained_at"].replace("Z", "+00:00"))
            model_age_days = (datetime.now(timezone.utc) - trained).days
        except Exception:
            pass

    result = {
        "bar_completeness": {
            "active_stocks":       active,
            "bars_last7d_stocks":  bars_7d,
            "bars_today_stocks":   bars_today,
            "coverage_7d_pct":     round(bars_7d / active * 100, 1) if active > 0 else 0.0,
            "coverage_today_pct":  round(bars_today / active * 100, 1) if active > 0 else 0.0,
            "latest_bar_date":     stats["latest_bar"],
            "missing_bars_sample": [],
            "missing_bars_count":  max(0, active - bars_7d),
        },
        "supply_coverage": {
            "coverage_7d_stocks":  sd_7d,
            "coverage_30d_stocks": sd_30d,
            "coverage_7d_pct":     round(sd_7d  / active * 100, 1) if active > 0 else 0.0,
            "coverage_30d_pct":    round(sd_30d / active * 100, 1) if active > 0 else 0.0,
            "latest_sd_date":      stats["latest_sd"],
            "missing_stocks":      max(0, active - sd_30d),
        },
        "ml_confidence": {
            "model_loaded":        (_model_dir / "entry_model.lgb").exists(),
            "auc":                 ml_metrics.get("auc"),
            "f1":                  ml_metrics.get("f1"),
            "trained_at":          ml_metrics.get("trained_at"),
            "model_age_days":      model_age_days,
            "feature_count":       ml_metrics.get("feature_count"),
            "train_samples":       ml_metrics.get("train_samples"),
            "threshold":           ml_metrics.get("optimal_threshold"),
            "vector_coverage_pct": vec_pct,
        },
    }
    try:
        await redis.set(_cache_key, json.dumps(result), ex=300)
    except Exception:
        pass
    return result


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


@router.post("/bootstrap/refresh-stats")
async def run_refresh_stats(
    background_tasks: BackgroundTasks,
    db: asyncpg.Pool = Depends(get_db),
    redis: redis_lib.Redis = Depends(get_redis),
):
    """Redis 탐지 통계 초기화 (daily_bars → Redis stats:{code}:*)."""
    background_tasks.add_task(_run_refresh_stats, db, redis)
    return {"status": "started", "step": "refresh-stats"}


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
    db: asyncpg.Pool = Depends(get_db),
    redis: redis_lib.Redis = Depends(get_redis),
):
    background_tasks.add_task(_run_backfill_vectors, redis, db)
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


async def _run_refresh_stats(db: asyncpg.Pool, redis: redis_lib.Redis) -> None:
    """daily_bars에서 탐지 통계 계산 → Redis 적재 (인라인 구현)."""
    from statistics import mean
    from datetime import datetime as _dt
    _TTL = 60 * 60 * 72

    async def _refresh_one(code: str) -> bool:
        rows = await db.fetch(
            "SELECT close, volume, amount, high, low FROM daily_bars "
            "WHERE code=$1 ORDER BY date DESC LIMIT 260", code
        )
        if len(rows) < 5:
            return False
        closes = [r["close"] for r in rows]
        vols   = [r["volume"] for r in rows]
        amts   = [r["amount"] for r in rows]
        highs  = [r["high"]   for r in rows]
        lows   = [r["low"]    for r in rows]
        avg_vol_20 = mean(vols[:20]) if len(vols) >= 20 else mean(vols)
        avg_amt_20 = mean(amts[:20]) if len(amts) >= 20 else mean(amts)
        high_20d = max(highs[:20])  if len(highs) >= 20  else max(highs)
        high_13w = max(highs[:65])  if len(highs) >= 65  else max(highs)
        high_26w = max(highs[:130]) if len(highs) >= 130 else max(highs)
        high_52w = max(highs[:260]) if len(highs) >= 260 else max(highs)
        tr_list  = [max(highs[j]-lows[j], abs(highs[j]-closes[j+1]), abs(lows[j]-closes[j+1]))
                    for j in range(min(14, len(rows)-1))]
        atr14 = mean(tr_list) if tr_list else (highs[0]-lows[0])
        pipe = redis.pipeline()
        pipe.set(f"stats:{code}:avg_vol_20d", int(avg_vol_20), ex=_TTL)
        pipe.set(f"stats:{code}:avg_amt_20d", int(avg_amt_20), ex=_TTL)
        pipe.set(f"stats:{code}:high_20d",    int(high_20d),   ex=_TTL)
        pipe.set(f"stats:{code}:high_13w",    int(high_13w),   ex=_TTL)
        pipe.set(f"stats:{code}:high_26w",    int(high_26w),   ex=_TTL)
        pipe.set(f"stats:{code}:high_52w",    int(high_52w),   ex=_TTL)
        pipe.set(f"stats:{code}:atr14",       round(atr14, 2), ex=_TTL)
        await pipe.execute()
        return True

    await _log(redis, "Redis 탐지 통계 초기화 시작...")
    try:
        codes_raw = await db.fetch("SELECT code FROM stocks WHERE is_active ORDER BY code")
        codes = [r["code"] for r in codes_raw]
        await _log(redis, f"{len(codes):,}개 종목 통계 계산 시작")
        total = 0
        for code in codes:
            try:
                ok = await _refresh_one(code)
                if ok:
                    total += 1
            except Exception:
                pass
        await redis.set("stats:last_refresh", _dt.utcnow().isoformat(), ex=_TTL)
        await redis.set("stats:refresh_count", total, ex=_TTL)
        await _log(redis, f"완료: Redis 통계 {total}/{len(codes):,}개 종목 × 7개 키 적재")
    except Exception as e:
        await _log(redis, f"오류: Redis 통계 초기화 — {str(e)[:300]}")


async def _run_backfill_vectors(redis: redis_lib.Redis, db: asyncpg.Pool | None = None) -> None:
    await _log(redis, "패턴 벡터 백필 시작...")
    try:
        proc = await asyncio.create_subprocess_exec(
            "python", "scripts/backfill_vectors.py",
            cwd="/ml",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            await _log(redis, "완료: 패턴 벡터 백필")
            # vector_count 캐시 갱신
            if db:
                try:
                    vc = await db.fetchval(
                        "SELECT COUNT(*) FROM feature_events WHERE pattern_vector IS NOT NULL"
                    )
                    await redis.set("stats:vector_count", int(vc or 0), ex=60 * 60 * 72)
                except Exception:
                    pass
        else:
            await _log(redis, f"실패: 벡터 백필 — {stdout.decode()[:200]}")
    except Exception as e:
        await _log(redis, f"오류: 벡터 백필 — {str(e)[:200]}")


@router.get("/pipeline-status")
async def pipeline_status(
    db: asyncpg.Pool = Depends(get_db),
    redis: redis_lib.Redis = Depends(get_redis),
):
    """데이터 파이프라인 전체 상태 (탐지, 공시, 뉴스, 추천)."""
    async with db.acquire() as conn:
        counts = await conn.fetchrow("""
            SELECT
                (SELECT COUNT(*) FROM feature_events
                 WHERE detected_at >= NOW() - INTERVAL '24 hours')          AS events_24h,
                (SELECT COUNT(*) FROM recommendations
                 WHERE created_at >= NOW() - INTERVAL '24 hours')           AS recs_24h,
                (SELECT COUNT(*) FROM disclosures
                 WHERE disclosed_at >= NOW() - INTERVAL '24 hours')         AS disclosures_24h,
                (SELECT COUNT(*) FROM news
                 WHERE published_at >= NOW() - INTERVAL '24 hours')         AS news_24h,
                0::BIGINT                                                    AS events_with_result,
                0::BIGINT                                                    AS events_with_vector,
                approximate_row_count('feature_events')                      AS total_events,
                (SELECT COUNT(*) FROM news
                 WHERE sentiment_score IS NOT NULL)                          AS news_with_sentiment
        """)

    # Redis 통계 키 수 — refresh_count 키로 즉시 조회 (SCAN 50k키 순회 제거)
    redis_stats_count = 0
    try:
        v = await redis.get("stats:refresh_count")
        redis_stats_count = int(v or 0)
    except Exception:
        pass

    # 뉴스 감성 Redis 키 수 — SCAN 제거, news:sentiment:count 캐시 키 사용
    news_sentiment_keys = 0
    try:
        v = await redis.get("news:sentiment:count")
        news_sentiment_keys = int(v or 0)
    except Exception:
        pass

    last_refresh = await redis.get("stats:last_refresh")

    # feature_events 대용량 COUNT는 Redis 캐시 우선, 없으면 approximate_row_count
    total = int(counts["total_events"] or 0)
    # with_result / with_vector: Redis 캐시 우선 (없으면 0 — 비필수 지표)
    with_result = 0
    with_vector = 0
    try:
        rr = await redis.get("stats:result_count")
        vc = await redis.get("stats:vector_count")
        with_result = int(rr or 0)
        with_vector = int(vc or 0)
    except Exception:
        pass

    return {
        "realtime": {
            "events_24h":       int(counts["events_24h"] or 0),
            "recs_24h":         int(counts["recs_24h"] or 0),
            "redis_stats_keys": redis_stats_count,
            "last_stats_refresh": (last_refresh.decode() if isinstance(last_refresh, bytes) else last_refresh),
            "status": "ok" if redis_stats_count > 1000 else "degraded",
        },
        "disclosures": {
            "count_24h": int(counts["disclosures_24h"] or 0),
            "status": "ok" if int(counts["disclosures_24h"] or 0) > 0 else "warning",
        },
        "news": {
            "count_24h":            int(counts["news_24h"] or 0),
            "with_sentiment":       int(counts["news_with_sentiment"] or 0),
            "sentiment_redis_keys": news_sentiment_keys,
            "status": "ok" if int(counts["news_24h"] or 0) > 0 else "warning",
        },
        "ml": {
            "events_with_result": with_result,
            "events_with_vector": with_vector,
            "total_events":       total,
            "result_coverage_pct": round(with_result / total * 100, 1) if total > 0 else 0.0,
            "vector_coverage_pct": round(with_vector / total * 100, 1) if total > 0 else 0.0,
        },
    }


@router.post("/force-refresh-stats")
async def force_refresh_stats(
    background_tasks: BackgroundTasks,
    db: asyncpg.Pool = Depends(get_db),
    redis: redis_lib.Redis = Depends(get_redis),
):
    """Redis 탐지 통계 즉시 강제 갱신 (관리자용)."""
    background_tasks.add_task(_run_refresh_stats, db, redis)
    return {"status": "started", "message": "Redis 탐지 통계 갱신이 백그라운드에서 시작되었습니다"}


# ── 백필 이력 / 스케줄 현황 ────────────────────────────────────────────────────

class BackfillJob(BaseModel):
    id: int
    job_type: str
    triggered_by: str
    status: str
    target_count: Optional[int]
    success_count: Optional[int]
    skip_count: Optional[int]
    fail_count: Optional[int]
    rows_added: Optional[int]
    started_at: str
    finished_at: Optional[str]
    error_msg: Optional[str]


class BackfillStatus(BaseModel):
    current_job: Optional[BackfillJob]
    last_completed: Optional[BackfillJob]
    last_run_redis: Optional[str]
    trigger_pending: bool


class ScheduleStatus(BaseModel):
    bars_backfill_last: Optional[str]
    financials_last: Optional[str]
    govdata_last: Optional[str]
    stats_last_refresh: Optional[str]


def _row_to_job(row) -> BackfillJob:
    """asyncpg Record → BackfillJob 변환."""
    def _iso(v):
        if v is None:
            return None
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v)

    return BackfillJob(
        id=row["id"],
        job_type=row["job_type"],
        triggered_by=row["triggered_by"],
        status=row["status"],
        target_count=row["target_count"],
        success_count=row["success_count"],
        skip_count=row["skip_count"],
        fail_count=row["fail_count"],
        rows_added=row["rows_added"],
        started_at=_iso(row["started_at"]) or "",
        finished_at=_iso(row["finished_at"]),
        error_msg=row["error_msg"],
    )


def _decode(v) -> Optional[str]:
    """Redis bytes → str 변환."""
    if v is None:
        return None
    return v.decode() if isinstance(v, bytes) else str(v)


@router.get("/backfill-status", response_model=BackfillStatus)
async def get_backfill_status(
    db: asyncpg.Pool = Depends(get_db),
    redis: redis_lib.Redis = Depends(get_redis),
):
    """현재 실행 중인 백필 작업 상태 + 마지막 완료 작업."""
    async with db.acquire() as conn:
        current_row = await conn.fetchrow(
            "SELECT * FROM backfill_history WHERE status IN ('running', 'pending') "
            "ORDER BY started_at DESC LIMIT 1"
        )
        last_row = await conn.fetchrow(
            "SELECT * FROM backfill_history WHERE status NOT IN ('running', 'pending') "
            "ORDER BY started_at DESC LIMIT 1"
        )

    current_job = _row_to_job(current_row) if current_row else None
    last_completed = _row_to_job(last_row) if last_row else None

    last_run_redis = _decode(await redis.get("bars_backfill:last_run"))
    trigger_pending = await redis.exists("backfill:trigger:bars") > 0

    return BackfillStatus(
        current_job=current_job,
        last_completed=last_completed,
        last_run_redis=last_run_redis,
        trigger_pending=trigger_pending,
    )


@router.get("/backfill-history", response_model=list[BackfillJob])
async def get_backfill_history(
    limit: int = Query(default=20, ge=1, le=100),
    db: asyncpg.Pool = Depends(get_db),
):
    """백필 작업 이력 최근 N개 조회."""
    async with db.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM backfill_history ORDER BY started_at DESC LIMIT $1",
            limit,
        )
    return [_row_to_job(r) for r in rows]


@router.post("/backfill/trigger")
async def trigger_backfill(
    job_type: str = Query(default="bars", description="백필 대상 (bars / financials / govdata)"),
    db: asyncpg.Pool = Depends(get_db),
    redis: redis_lib.Redis = Depends(get_redis),
):
    """수동 백필 트리거: Redis 키 설정 + DB에 pending 레코드 삽입."""
    # Redis 트리거 키 세팅 (워커가 폴링 후 실행)
    trigger_key = f"backfill:trigger:{job_type}"
    await redis.set(trigger_key, "1", ex=3600)

    # DB에 pending 레코드 삽입
    async with db.acquire() as conn:
        row_id = await conn.fetchval(
            """INSERT INTO backfill_history (job_type, triggered_by, status)
               VALUES ($1, 'manual', 'pending') RETURNING id""",
            job_type,
        )

    logger.info(f"Manual backfill triggered: job_type={job_type}, history_id={row_id}")
    return {
        "status": "triggered",
        "job_type": job_type,
        "history_id": row_id,
        "message": f"백필 트리거 전송 완료 (Redis key: {trigger_key})",
    }


@router.get("/schedule-status", response_model=ScheduleStatus)
async def get_schedule_status(
    redis: redis_lib.Redis = Depends(get_redis),
):
    """각 워커의 마지막 실행 시각 (Redis 키 기반)."""
    keys = [
        "bars_backfill:last_run",
        "financials:last_run",
        "govdata:last_run_date",
        "stats:last_refresh",
    ]
    vals = await redis.mget(*keys)

    return ScheduleStatus(
        bars_backfill_last=_decode(vals[0]),
        financials_last=_decode(vals[1]),
        govdata_last=_decode(vals[2]),
        stats_last_refresh=_decode(vals[3]),
    )

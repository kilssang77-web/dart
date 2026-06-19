from fastapi import APIRouter, Depends, Query, HTTPException
import asyncpg
import redis.asyncio as redis_lib
from deps import get_db, get_redis
from schemas.responses import RecommendationResponse, PerformanceStatsResponse, CodeSignalsResponse
from services.recommendation_service import RecommendationService

router = APIRouter()


def _svc(db: asyncpg.Pool = Depends(get_db), redis: redis_lib.Redis = Depends(get_redis)) -> RecommendationService:
    return RecommendationService(db, redis)


@router.get("", response_model=list[RecommendationResponse])
async def list_recommendations(
    action:   str | None = None,
    market:   str | None = None,
    code:     str | None = None,
    min_prob: float = Query(default=0.30, ge=0.30, le=1.0),
    hours:    int   = Query(default=72, le=168),
    limit:    int   = Query(default=30, le=100),
    dedupe:   bool  = Query(default=True, description="종목당 최고확률 1건만 반환"),
    svc: RecommendationService = Depends(_svc),
):
    return await svc.list_recommendations(action, market, code, min_prob, hours, limit, dedupe)


@router.get("/buy", response_model=list[RecommendationResponse])
async def get_buy_signals(
    min_prob: float = Query(default=0.30, ge=0.30, le=1.0),
    db: asyncpg.Pool = Depends(get_db),
):
    from services.recommendation_service import _parse_json_fields
    rows = await db.fetch(
        """
        SELECT
            r.id, (r.created_at AT TIME ZONE 'Asia/Seoul')::TEXT AS created_at, r.code,
            COALESCE(s.name, r.code)   AS name,
            COALESCE(NULLIF(s.market, 'UNKNOWN'), '-')    AS market,
            r.action,
            r.entry_price, r.target_price, r.stop_loss_price,
            r.success_prob, r.expected_return, r.risk_score,
            r.risk_reward_ratio, r.expected_hold_days,
            r.rationale, r.similar_cases
        FROM recommendations r
        LEFT JOIN stocks s ON s.code = r.code
        WHERE r.action = 'BUY'
          AND r.success_prob >= $1
          AND r.created_at >= NOW() - INTERVAL '72 hours'
        ORDER BY r.success_prob DESC
        LIMIT 20
        """,
        min_prob,
    )
    return [RecommendationResponse(**_parse_json_fields(dict(r))) for r in rows]


@router.get("/stats/performance", response_model=PerformanceStatsResponse)
async def performance_stats(
    days: int = Query(default=30, le=90),
    svc: RecommendationService = Depends(_svc),
):
    return await svc.performance_stats(days)


@router.get("/performance/active")
async def performance_active(
    db: asyncpg.Pool = Depends(get_db),
):
    """추적 중인 활성 추천 현황 (tracking_complete=FALSE)."""
    rows = await db.fetch(
        """
        SELECT
            rec.id, rec.code,
            COALESCE(s.name, rec.code) AS name,
            COALESCE(NULLIF(s.market,'UNKNOWN'),'-') AS market,
            rec.action, rec.entry_price, rec.target_price, rec.stop_loss_price,
            rec.success_prob,
            (rec.created_at AT TIME ZONE 'Asia/Seoul')::TEXT AS created_at,
            rp.r_1d, rp.r_3d, rp.r_5d,
            rp.hit_target, rp.hit_stop
        FROM recommendations rec
        JOIN recommendation_performance rp ON rp.rec_id = rec.id
        LEFT JOIN stocks s ON s.code = rec.code
        WHERE rp.tracking_complete = FALSE
          AND rec.action = 'BUY'
        ORDER BY rec.created_at DESC
        LIMIT 50
        """,
    )
    return [
        {
            "id":           r["id"],
            "code":         r["code"],
            "name":         r["name"],
            "market":       r["market"],
            "action":       r["action"],
            "entry_price":  float(r["entry_price"] or 0),
            "target_price": float(r["target_price"] or 0),
            "stop_loss_price": float(r["stop_loss_price"] or 0),
            "success_prob": float(r["success_prob"] or 0),
            "created_at":   r["created_at"],
            "r_1d":         float(r["r_1d"]) if r["r_1d"] is not None else None,
            "r_3d":         float(r["r_3d"]) if r["r_3d"] is not None else None,
            "r_5d":         float(r["r_5d"]) if r["r_5d"] is not None else None,
            "hit_target":   r["hit_target"],
            "hit_stop":     r["hit_stop"],
        }
        for r in rows
    ]


@router.get("/performance/history")
async def performance_history(
    days: int = Query(default=30, le=180),
    limit: int = Query(default=100, le=500),
    db: asyncpg.Pool = Depends(get_db),
):
    """완료된 추천 성과 이력."""
    rows = await db.fetch(
        """
        SELECT
            rec.id, rec.code,
            COALESCE(s.name, rec.code) AS name,
            COALESCE(NULLIF(s.market,'UNKNOWN'),'-') AS market,
            rec.action, rec.entry_price, rec.success_prob,
            rp.event_type,
            (rec.created_at AT TIME ZONE 'Asia/Seoul')::TEXT AS created_at,
            rp.r_1d, rp.r_3d, rp.r_5d, rp.r_10d,
            rp.max_return, rp.is_success, rp.hit_target, rp.hit_stop
        FROM recommendations rec
        JOIN recommendation_performance rp ON rp.rec_id = rec.id
        LEFT JOIN stocks s ON s.code = rec.code
        WHERE rp.tracking_complete = TRUE
          AND rec.created_at >= NOW() - ($1 * INTERVAL '1 day')
        ORDER BY rec.created_at DESC
        LIMIT $2
        """,
        days, limit,
    )
    return [
        {
            "id":           r["id"],
            "code":         r["code"],
            "name":         r["name"],
            "market":       r["market"],
            "action":       r["action"],
            "entry_price":  float(r["entry_price"] or 0),
            "success_prob": float(r["success_prob"] or 0),
            "event_type":   r["event_type"],
            "created_at":   r["created_at"],
            "r_1d":         float(r["r_1d"]) if r["r_1d"] is not None else None,
            "r_3d":         float(r["r_3d"]) if r["r_3d"] is not None else None,
            "r_5d":         float(r["r_5d"]) if r["r_5d"] is not None else None,
            "r_10d":        float(r["r_10d"]) if r["r_10d"] is not None else None,
            "max_return":   float(r["max_return"]) if r["max_return"] is not None else None,
            "is_success":   r["is_success"],
            "hit_target":   r["hit_target"],
            "hit_stop":     r["hit_stop"],
        }
        for r in rows
    ]


@router.get("/performance/summary")
async def performance_summary(
    days: int = Query(default=30, le=365),
    db: asyncpg.Pool = Depends(get_db),
):
    """추천 성과 집계 요약."""
    row = await db.fetchrow(
        """
        SELECT
            COUNT(*)                                         AS total,
            COUNT(*) FILTER (WHERE rp.is_success = TRUE)    AS wins,
            COUNT(*) FILTER (WHERE rp.hit_target = TRUE)    AS hit_target,
            COUNT(*) FILTER (WHERE rp.hit_stop = TRUE)      AS hit_stop,
            ROUND(AVG(rp.r_5d)::NUMERIC, 3)                AS avg_return_5d,
            ROUND(AVG(rp.max_return)::NUMERIC, 3)          AS avg_max_return,
            COUNT(*) FILTER (WHERE rp.tracking_complete = FALSE
                               AND rec.action = 'BUY')      AS active_count
        FROM recommendations rec
        JOIN recommendation_performance rp ON rp.rec_id = rec.id
        WHERE rec.created_at >= NOW() - ($1 * INTERVAL '1 day')
        """,
        days,
    )
    total = row["total"] or 0
    completed = total - (row["active_count"] or 0)
    return {
        "total":          total,
        "active_count":   row["active_count"] or 0,
        "completed":      completed,
        "wins":           row["wins"] or 0,
        "hit_target":     row["hit_target"] or 0,
        "hit_stop":       row["hit_stop"] or 0,
        "win_rate":       round((row["wins"] or 0) / completed * 100, 1) if completed else 0.0,
        "avg_return_5d":  float(row["avg_return_5d"] or 0),
        "avg_max_return": float(row["avg_max_return"] or 0),
        "days":           days,
    }


@router.get("/by-id/{rec_id}", response_model=RecommendationResponse)
async def get_by_id(rec_id: int, db: asyncpg.Pool = Depends(get_db)):
    """rec_id(recommendations.id) 기준 단건 조회 — 추천 성과 추적 팝업용."""
    from services.recommendation_service import _parse_json_fields
    row = await db.fetchrow(
        """
        SELECT
            r.id, (r.created_at AT TIME ZONE 'Asia/Seoul')::TEXT AS created_at, r.code,
            COALESCE(s.name, r.code)                              AS name,
            COALESCE(NULLIF(s.market, 'UNKNOWN'), '-')            AS market,
            r.action,
            r.entry_price, r.target_price, r.stop_loss_price,
            r.success_prob, r.expected_return, r.risk_score,
            r.risk_reward_ratio, r.expected_hold_days,
            r.rationale, r.similar_cases
        FROM recommendations r
        LEFT JOIN stocks s ON s.code = r.code
        WHERE r.id = $1
        """,
        rec_id,
    )
    if not row:
        raise HTTPException(404, "No recommendation found")
    return RecommendationResponse(**_parse_json_fields(dict(row)))


@router.get("/{code}/signals", response_model=CodeSignalsResponse)
async def code_signals(
    code:  str,
    hours: int = Query(default=168, le=720),
    svc: RecommendationService = Depends(_svc),
):
    return await svc.code_signals(code, hours)


@router.get("/{code}/latest", response_model=RecommendationResponse)
async def get_latest(code: str, db: asyncpg.Pool = Depends(get_db)):
    from services.recommendation_service import _parse_json_fields
    row = await db.fetchrow(
        """
        SELECT
            r.id, (r.created_at AT TIME ZONE 'Asia/Seoul')::TEXT AS created_at, r.code,
            COALESCE(s.name, r.code)   AS name,
            COALESCE(NULLIF(s.market, 'UNKNOWN'), '-')    AS market,
            r.action,
            r.entry_price, r.target_price, r.stop_loss_price,
            r.success_prob, r.expected_return, r.risk_score,
            r.risk_reward_ratio, r.expected_hold_days,
            r.rationale, r.similar_cases
        FROM recommendations r
        LEFT JOIN stocks s ON s.code = r.code
        WHERE r.code = $1
        ORDER BY r.created_at DESC
        LIMIT 1
        """,
        code,
    )
    if not row:
        raise HTTPException(404, "No recommendation found")
    return RecommendationResponse(**_parse_json_fields(dict(row)))

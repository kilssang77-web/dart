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
    min_prob: float = Query(default=0.20, ge=0.0, le=1.0),
    hours:    int   = Query(default=72, le=168),
    limit:    int   = Query(default=30, le=100),
    dedupe:   bool  = Query(default=True, description="종목당 최고확률 1건만 반환"),
    svc: RecommendationService = Depends(_svc),
):
    return await svc.list_recommendations(action, market, code, min_prob, hours, limit, dedupe)


@router.get("/buy", response_model=list[RecommendationResponse])
async def get_buy_signals(
    min_prob: float = Query(default=0.20, ge=0.0, le=1.0),
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
          AND r.created_at >= NOW() - INTERVAL '24 hours'
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

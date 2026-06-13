from fastapi import APIRouter, Depends, Query
import asyncpg
import redis.asyncio as redis_lib
from deps import get_db, get_redis
from services.feature_service import FeatureService, EVENT_TYPES

router = APIRouter()


def _svc(db: asyncpg.Pool = Depends(get_db), redis: redis_lib.Redis = Depends(get_redis)) -> FeatureService:
    return FeatureService(db, redis)


@router.get("")
async def list_features(
    event_type: str | None = None,
    code:       str | None = None,
    market:     str | None = None,
    min_score:  float = Query(default=0.5, ge=0.0, le=1.0),
    hours:      int   = Query(default=72, le=168),
    limit:      int   = Query(default=50, le=500),
    dedupe:     bool  = Query(default=False, description="종목당 최고점수 1건만 반환"),
    svc: FeatureService = Depends(_svc),
):
    return await svc.list_features(event_type, code, market, min_score, hours, limit, dedupe)


@router.get("/types")
async def get_event_types():
    return EVENT_TYPES


# /today/summary 는 /{event_id} 보다 반드시 먼저 선언해야 함
@router.get("/today/summary")
async def today_summary(svc: FeatureService = Depends(_svc)):
    return await svc.today_summary()


@router.get("/{event_id}/similar")
async def get_similar(
    event_id: int,
    top_k: int = Query(default=10, le=30),
    svc: FeatureService = Depends(_svc),
):
    return await svc.get_similar(event_id, top_k)


@router.get("/{event_id}")
async def get_feature(event_id: int, svc: FeatureService = Depends(_svc)):
    return await svc.get_by_id(event_id)

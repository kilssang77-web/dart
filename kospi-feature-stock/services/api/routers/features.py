from __future__ import annotations
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
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


@router.get("/{event_id}/similar-with-bars")
async def get_similar_with_bars(
    event_id:      int,
    top_k:         int = Query(default=5, le=10),
    window_before: int = Query(default=5, ge=3, le=20),
    window_after:  int = Query(default=15, ge=5, le=30),
    db:  asyncpg.Pool   = Depends(get_db),
    svc: FeatureService = Depends(_svc),
):
    event = await svc.get_by_id(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="이벤트 없음")

    cases = await svc.get_similar(event_id, top_k)

    async def _bars(code: str, detected_at) -> list[dict]:
        if hasattr(detected_at, 'date'):
            ev_date = detected_at.date()
        else:
            from datetime import datetime
            ev_date = datetime.fromisoformat(str(detected_at)[:19]).date()
        start = ev_date - timedelta(days=window_before)
        end   = ev_date + timedelta(days=window_after)
        rows  = await db.fetch(
            """SELECT date::text, open, high, low, close, volume, change_rate
               FROM daily_bars WHERE code = $1 AND date BETWEEN $2 AND $3
               ORDER BY date""",
            code, start, end,
        )
        return [dict(r) for r in rows]

    event_dict = dict(event)
    event_bars = await _bars(event_dict['code'], event_dict['detected_at'])

    enriched = []
    for c in cases:
        cd = dict(c)
        cd['bars'] = await _bars(cd['code'], cd['detected_at'])
        enriched.append(cd)

    return {
        'event':      event_dict,
        'event_bars': event_bars,
        'cases':      enriched,
    }


@router.get("/{event_id}")
async def get_feature(event_id: int, svc: FeatureService = Depends(_svc)):
    return await svc.get_by_id(event_id)

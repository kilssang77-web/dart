from __future__ import annotations
from collections import defaultdict
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

    event_dict = dict(event)

    # 이벤트 + 유사사례 bars를 단일 배치 쿼리로 조회 (N+1 → 1회)
    def _date_of(detected_at) -> object:
        if hasattr(detected_at, 'date'):
            return detected_at.date()
        from datetime import datetime
        return datetime.fromisoformat(str(detected_at)[:19]).date()

    all_items = [event_dict] + [dict(c) for c in cases]
    codes   = [it['code'] for it in all_items]
    ev_dates = [_date_of(it['detected_at']) for it in all_items]
    min_date = min(ev_dates) - timedelta(days=window_before)
    max_date = max(ev_dates) + timedelta(days=window_after)

    batch_rows = await db.fetch(
        """SELECT code, date::text, open, high, low, close, volume, change_rate
           FROM daily_bars
           WHERE code = ANY($1::text[]) AND date BETWEEN $2 AND $3
           ORDER BY code, date""",
        codes, min_date, max_date,
    )

    bars_by_code: dict[str, list[dict]] = defaultdict(list)
    for r in batch_rows:
        bars_by_code[r['code']].append(dict(r))

    def _filter_bars(code: str, ev_date) -> list[dict]:
        d = _date_of(ev_date)
        s = str(d - timedelta(days=window_before))
        e = str(d + timedelta(days=window_after))
        return [b for b in bars_by_code[code] if s <= b['date'] <= e]

    event_bars = _filter_bars(event_dict['code'], event_dict['detected_at'])

    enriched = []
    for c in cases:
        cd = dict(c)
        cd['bars'] = _filter_bars(cd['code'], cd['detected_at'])
        enriched.append(cd)

    return {
        'event':      event_dict,
        'event_bars': event_bars,
        'cases':      enriched,
    }


@router.get("/{event_id}")
async def get_feature(event_id: int, svc: FeatureService = Depends(_svc)):
    return await svc.get_by_id(event_id)

from fastapi import APIRouter, Depends, Query
import asyncpg
import redis.asyncio as redis_lib
from deps import get_db, get_redis
from services.disclosure_service import DisclosureService

router = APIRouter()


def _svc(db: asyncpg.Pool = Depends(get_db), redis: redis_lib.Redis = Depends(get_redis)) -> DisclosureService:
    return DisclosureService(db, redis)


@router.get("")
async def list_disclosures(
    code:     str | None = None,
    category: str | None = None,
    market:   str | None = None,
    flagged:  bool | None = None,
    hours:    int = Query(default=72, le=168),
    limit:    int = Query(default=50, le=200),
    svc: DisclosureService = Depends(_svc),
):
    return await svc.list_disclosures(code, category, market, flagged, hours, limit)


@router.get("/favorable")
async def favorable_disclosures(
    hours:  int = Query(default=48, le=168),
    market: str | None = None,
    svc: DisclosureService = Depends(_svc),
):
    return await svc.list_favorable(hours, market)


@router.get("/{rcept_no}")
async def get_disclosure(rcept_no: str, svc: DisclosureService = Depends(_svc)):
    return await svc.get_by_rcept_no(rcept_no)

from fastapi import APIRouter, Depends, HTTPException
import asyncpg
import redis.asyncio as redis_lib
from deps import get_db, get_redis, enrich_live_prices
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class WatchlistAddRequest(BaseModel):
    code: str
    session_id: str = 'default'
    note: Optional[str] = None


class WatchlistItem(BaseModel):
    id: int
    session_id: str
    code: str
    name: str
    market: str
    added_at: str
    note: Optional[str] = None
    current_price: Optional[int] = None
    change_rate: Optional[float] = None


@router.get("", response_model=list[WatchlistItem])
async def list_watchlist(
    session_id: str = 'default',
    db: asyncpg.Pool = Depends(get_db),
    redis: redis_lib.Redis = Depends(get_redis),
):
    rows = await db.fetch(
        """
        SELECT
            w.id, w.session_id, w.code, (w.added_at AT TIME ZONE 'Asia/Seoul')::TEXT AS added_at, w.note,
            COALESCE(s.name, w.code)                         AS name,
            COALESCE(NULLIF(s.market, 'UNKNOWN'), '-')       AS market,
            db.close                                          AS current_price,
            COALESCE(db.change_rate, 0)::FLOAT               AS change_rate
        FROM watchlist w
        LEFT JOIN stocks s ON s.code = w.code
        LEFT JOIN LATERAL (
            SELECT close, change_rate FROM daily_bars
            WHERE code = w.code ORDER BY date DESC LIMIT 1
        ) db ON true
        WHERE w.session_id = $1
        ORDER BY w.added_at DESC
        """,
        session_id,
    )
    dicts = [dict(r) for r in rows]
    await enrich_live_prices(redis, dicts, price_field="current_price", rate_field="change_rate")
    return dicts


@router.post("", response_model=WatchlistItem, status_code=201)
async def add_to_watchlist(
    body: WatchlistAddRequest,
    db: asyncpg.Pool = Depends(get_db),
    redis: redis_lib.Redis = Depends(get_redis),
):
    code = body.code.upper()
    row = await db.fetchrow(
        """
        INSERT INTO watchlist (session_id, code, note)
        VALUES ($1, $2, $3)
        ON CONFLICT (session_id, code) DO UPDATE
            SET note = EXCLUDED.note
        RETURNING id, session_id, code, (added_at AT TIME ZONE 'Asia/Seoul')::TEXT AS added_at, note
        """,
        body.session_id, code, body.note,
    )
    stock = await db.fetchrow(
        """
        SELECT COALESCE(s.name, $1) AS name,
               COALESCE(NULLIF(s.market, 'UNKNOWN'), '-') AS market,
               db.close AS current_price,
               COALESCE(db.change_rate, 0)::FLOAT AS change_rate
        FROM stocks s
        LEFT JOIN LATERAL (
            SELECT close, change_rate FROM daily_bars
            WHERE code = $1 ORDER BY date DESC LIMIT 1
        ) db ON true
        WHERE s.code = $1
        LIMIT 1
        """,
        code,
    )
    result = dict(row)
    if stock:
        result.update({
            "name":          stock["name"],
            "market":        stock["market"],
            "current_price": stock["current_price"],
            "change_rate":   stock["change_rate"],
        })
        # Redis 실시간 호가로 보정
        await enrich_live_prices(redis, [result], price_field="current_price", rate_field="change_rate")
    else:
        result.update({"name": code, "market": "-", "current_price": None, "change_rate": None})
    return result


@router.delete("/{code}", status_code=204)
async def remove_from_watchlist(
    code: str,
    session_id: str = 'default',
    db: asyncpg.Pool = Depends(get_db),
):
    deleted = await db.fetchval(
        "DELETE FROM watchlist WHERE session_id = $1 AND code = $2 RETURNING id",
        session_id, code.upper(),
    )
    if not deleted:
        raise HTTPException(404, "Not in watchlist")
from fastapi import APIRouter, Depends, Query, HTTPException
import asyncpg
import orjson
import redis.asyncio as redis_lib
from deps import get_db, get_redis

router = APIRouter()


@router.get("")
async def list_stocks(
    market: str | None = None,
    sector: str | None = None,
    q: str | None = None,
    limit: int = Query(default=50, le=500),
    db: asyncpg.Pool = Depends(get_db),
):
    where = ["is_active = TRUE"]
    params: list = []
    if market:
        params.append(market.upper())
        where.append(f"market = ${len(params)}")
    if sector:
        params.append(sector)
        where.append(f"sector ILIKE ${len(params)}")
    if q:
        params.append(f"%{q}%")
        p_name = len(params)
        params.append(f"%{q}%")
        p_code = len(params)
        where.append(f"(name ILIKE ${p_name} OR code ILIKE ${p_code})")

    rows = await db.fetch(
        f"SELECT code, name, market, sector, industry FROM stocks "
        f"WHERE {' AND '.join(where)} ORDER BY market, code LIMIT {limit}",
        *params,
    )
    return [dict(r) for r in rows]


_DEFAULT_ACTIVE = [
    "005930","000660","035420","005380","051910","006400","035720","028260",
    "207940","068270","323410","105560","055550","086790","032830","066570",
    "003550","096770","033780","015760",
]

@router.get("/active")
async def get_active_stocks(
    redis: redis_lib.Redis = Depends(get_redis),
    db: asyncpg.Pool = Depends(get_db),
):
    """Redis active_codes 기반 실시간 구독 중인 종목 목록 + DB 정보."""
    try:
        cached = await redis.get("stocks:active_codes")
        codes = orjson.loads(cached) if cached else _DEFAULT_ACTIVE
    except Exception:
        codes = _DEFAULT_ACTIVE
    if not codes:
        return []
    rows = await db.fetch(
        "SELECT code, name, market, sector FROM stocks WHERE code = ANY($1::varchar[]) ORDER BY market, code",
        codes,
    )
    return [dict(r) for r in rows]


@router.get("/{code}")
async def get_stock(code: str, db: asyncpg.Pool = Depends(get_db)):
    row = await db.fetchrow("SELECT * FROM stocks WHERE code = $1", code)
    if not row:
        raise HTTPException(404, "Stock not found")
    return dict(row)


@router.get("/{code}/daily")
async def get_daily_bars(
    code: str,
    days: int = Query(default=60, le=780),
    db: asyncpg.Pool = Depends(get_db),
):
    rows = await db.fetch(
        """
        SELECT date::TEXT, open, high, low, close, volume, amount,
               change_rate, adj_close, foreign_net_buy, inst_net_buy,
               ma5, ma20, ma60, rsi14, bb_upper, bb_lower
        FROM daily_bars
        WHERE code = $1
        ORDER BY date DESC
        LIMIT $2
        """,
        code, days,
    )
    return [dict(r) for r in reversed(rows)]  # daily end


@router.get("/{code}/supply")
async def get_supply_demand(
    code: str,
    days: int = Query(default=20, le=60),
    db: asyncpg.Pool = Depends(get_db),
):
    rows = await db.fetch(
        """
        SELECT date::TEXT, foreign_net, inst_net, indiv_net,
               prog_arbitrage_net, foreign_hold_rate
        FROM supply_demand
        WHERE code = $1
        ORDER BY date DESC
        LIMIT $2
        """,
        code, days,
    )
    if not rows:
        # supply_demand 미적재 시 daily_bars 컬럼으로 폴백 (write_supply_demand가 기록한 값)
        rows = await db.fetch(
            """
            SELECT date::TEXT,
                   foreign_net_buy   AS foreign_net,
                   inst_net_buy      AS inst_net,
                   indiv_net_buy     AS indiv_net,
                   prog_net_buy      AS prog_arbitrage_net,
                   NULL::numeric     AS foreign_hold_rate
            FROM daily_bars
            WHERE code = $1
              AND (foreign_net_buy != 0 OR inst_net_buy != 0)
            ORDER BY date DESC
            LIMIT $2
            """,
            code, days,
        )
    return [dict(r) for r in reversed(rows)]


@router.post("/{code}/watch", status_code=200)
async def watch_stock(
    code: str,
    redis: redis_lib.Redis = Depends(get_redis),
):
    """종목 상세 열람 시 호출 — collector가 해당 종목 KIS WebSocket 구독 추가 (TTL 3분)."""
    await redis.set(f"watching:{code}", "1", ex=180)
    return {"watching": code}


# ── 관심종목 서버 사이드 동기화 ─────────────────────────────────

@router.post("/favorites/sync", status_code=200)
async def sync_favorites(
    payload: dict,
    redis: redis_lib.Redis = Depends(get_redis),
):
    """브라우저 관심종목 → Redis 동기화. batch_scanner가 active_codes에 포함시킴."""
    codes = payload.get("codes", [])
    if not isinstance(codes, list):
        codes = []
    codes = [str(c).upper()[:6] for c in codes if c][:100]
    await redis.set("user:favorites", orjson.dumps(codes), ex=90_000)
    # watching TTL도 갱신 (실시간 구독 유지)
    for code in codes:
        await redis.set(f"watching:{code}", "1", ex=600)
    return {"synced": len(codes)}


@router.get("/favorites/list")
async def list_favorites(redis: redis_lib.Redis = Depends(get_redis)):
    """현재 서버에 동기화된 관심종목 코드 목록."""
    raw = await redis.get("user:favorites")
    return orjson.loads(raw) if raw else []


@router.get("/{code}/quote")
async def get_stock_quote(
    code: str,
    db: asyncpg.Pool = Depends(get_db),
    redis: redis_lib.Redis = Depends(get_redis),
):
    """실시간 현재가. Redis 캐시(30s TTL) → daily_bars 순으로 폴백."""
    cached = await redis.get(f"quote:{code}")
    if cached:
        tick = orjson.loads(cached)
        return {
            "code":        code,
            "price":       tick.get("price"),
            "prev_close":  tick.get("prev_close"),
            "change":      tick.get("change"),
            "change_rate": tick.get("change_rate"),
            "open":        tick.get("open"),
            "high":        tick.get("high"),
            "low":         tick.get("low"),
            "volume":      tick.get("cum_volume"),
            "amount":      tick.get("cum_amount"),
            "source":      "realtime",
        }

    rows = await db.fetch(
        """
        SELECT close AS price, change_rate, volume, amount, open, high, low
        FROM daily_bars WHERE code = $1 ORDER BY date DESC LIMIT 2
        """,
        code,
    )
    if rows:
        bar = rows[0]
        prev_price = rows[1]["price"] if len(rows) > 1 else None
        price_val  = bar["price"]
        change_val = round(price_val - prev_price) if prev_price else None
        rate_val   = bar["change_rate"]
        if not rate_val and change_val and prev_price:
            rate_val = round(change_val / prev_price * 100, 2)
        return {
            "code":        code,
            "price":       price_val,
            "prev_close":  prev_price,
            "change":      change_val,
            "change_rate": rate_val,
            "open":        bar["open"],
            "high":        bar["high"],
            "low":         bar["low"],
            "volume":      bar["volume"],
            "amount":      bar["amount"],
            "source":      "daily",
        }

    return {
        "code": code, "price": None, "prev_close": None,
        "change": None, "change_rate": None,
        "open": None, "high": None, "low": None,
        "volume": None, "amount": None, "source": "none",
    }

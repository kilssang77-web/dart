from fastapi import APIRouter, Depends, Query
from datetime import datetime, timedelta
import asyncpg
import json
from deps import get_db

router = APIRouter()


@router.get("")
async def list_disclosures(
    code: str | None = None,
    category: str | None = None,
    market: str | None = None,
    flagged: bool | None = None,
    hours: int = Query(default=24, le=168),
    limit: int = Query(default=50, le=200),
    db: asyncpg.Pool = Depends(get_db),
):
    since = datetime.now() - timedelta(hours=hours)
    where = ["d.disclosed_at >= $1"]
    params: list = [since]

    if code:
        params.append(code)
        where.append(f"d.code = ${len(params)}")
    if category:
        params.append(category)
        where.append(f"d.category = ${len(params)}")
    if market:
        params.append(market.upper())
        where.append(f"s.market = ${len(params)}")
    if flagged is True:
        where.append("d.is_flagged = TRUE")

    rows = await db.fetch(
        f"""
        SELECT
            d.id, d.rcept_no, d.code, d.corp_name,
            d.disclosed_at::TEXT, d.disclosure_type, d.title,
            d.category, d.sentiment_score,
            d.keywords, d.counterparty,
            d.post_1h_change, d.post_1d_change, d.post_3d_change,
            COALESCE(s.market, '-') AS market
        FROM disclosures d
        LEFT JOIN stocks s ON s.code = d.code
        WHERE {' AND '.join(where)}
        ORDER BY d.disclosed_at DESC
        LIMIT {limit}
        """,
        *params,
    )
    result = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get("keywords"), str):
            try:
                d["keywords"] = json.loads(d["keywords"])
            except Exception:
                d["keywords"] = []
        result.append(d)
    return result


@router.get("/favorable")
async def favorable_disclosures(
    hours: int = Query(default=48, le=168),
    market: str | None = None,
    db: asyncpg.Pool = Depends(get_db),
):
    mkt_filter = "AND s.market = $2" if market else ""
    params = [hours] + ([market.upper()] if market else [])
    rows = await db.fetch(
        f"""
        SELECT d.id, d.rcept_no, d.code, d.corp_name,
               d.disclosed_at::TEXT, d.disclosure_type, d.title,
               d.category, d.sentiment_score,
               d.keywords, d.counterparty,
               d.post_1h_change, d.post_1d_change, d.post_3d_change,
               COALESCE(s.market, '-') AS market
        FROM disclosures d
        LEFT JOIN stocks s ON s.code = d.code
        WHERE d.category = 'favorable'
          AND d.disclosed_at >= NOW() - ($1 * INTERVAL '1 hour')
          {mkt_filter}
        ORDER BY d.sentiment_score DESC, d.disclosed_at DESC
        LIMIT 30
        """,
        *params,
    )
    result = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get("keywords"), str):
            try:
                d["keywords"] = json.loads(d["keywords"])
            except Exception:
                d["keywords"] = []
        result.append(d)
    return result


@router.get("/{rcept_no}")
async def get_disclosure(rcept_no: str, db: asyncpg.Pool = Depends(get_db)):
    row = await db.fetchrow(
        "SELECT * FROM disclosures WHERE rcept_no = $1",
        rcept_no,
    )
    if not row:
        return {}
    d = dict(row)
    if isinstance(d.get("keywords"), str):
        try:
            d["keywords"] = json.loads(d["keywords"])
        except Exception:
            d["keywords"] = []
    return d

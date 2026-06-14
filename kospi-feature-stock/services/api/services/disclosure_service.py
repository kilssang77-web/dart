"""
공시 비즈니스 로직 서비스.
"""
import json
from datetime import datetime, timedelta, timezone
import asyncpg
import redis.asyncio as redis_lib
from deps import cached_fetch


def _parse_keywords(d: dict) -> dict:
    if isinstance(d.get("keywords"), str):
        try:
            d["keywords"] = json.loads(d["keywords"])
        except Exception:
            d["keywords"] = []
    return d


class DisclosureService:

    def __init__(self, db: asyncpg.Pool, redis: redis_lib.Redis | None = None):
        self.db    = db
        self.redis = redis

    async def list_disclosures(
        self,
        code:       str | None,
        category:   str | None,
        market:     str | None,
        flagged:    bool | None,
        hours:      int,
        limit:      int,
        sort_by:    str  = "disclosed_at",
        sort_dir:   str  = "desc",
        min_amount: int | None = None,
    ) -> list[dict]:
        since  = datetime.now(timezone.utc) - timedelta(hours=hours)
        where  = ["d.disclosed_at >= $1"]
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
        if min_amount is not None:
            params.append(min_amount * 100_000_000)
            where.append(f"d.amount >= ${len(params)}")

        _COL_MAP = {"contract_amount": "amount"}
        direction = "DESC" if sort_dir == "desc" else "ASC"
        order_col = f"d.{_COL_MAP.get(sort_by, sort_by)}"
        null_order = "NULLS LAST" if direction == "DESC" else "NULLS FIRST"

        params.append(limit)
        rows = await self.db.fetch(
            f"""
            SELECT
                d.id, d.rcept_no, d.code, d.corp_name,
                (d.disclosed_at AT TIME ZONE 'Asia/Seoul')::TEXT AS disclosed_at,
                d.disclosure_type, d.title, d.category, d.sentiment_score,
                d.keywords, d.counterparty,
                d.post_1h_change, d.post_1d_change, d.post_3d_change,
                d.amount AS contract_amount,
                COALESCE(NULLIF(s.market, 'UNKNOWN'), '-') AS market
            FROM disclosures d
            LEFT JOIN stocks s ON s.code = d.code
            WHERE {' AND '.join(where)}
            ORDER BY {order_col} {direction} {null_order}
            LIMIT ${len(params)}
            """,
            *params,
        )
        return [_parse_keywords(dict(r)) for r in rows]

    async def list_favorable(
        self,
        hours:  int,
        market: str | None,
    ) -> list[dict]:
        mkt_filter = "AND s.market = $2" if market else ""
        params     = [hours] + ([market.upper()] if market else [])
        rows = await self.db.fetch(
            f"""
            SELECT d.id, d.rcept_no, d.code, d.corp_name,
                   (d.disclosed_at AT TIME ZONE 'Asia/Seoul')::TEXT AS disclosed_at,
                   d.disclosure_type, d.title, d.category, d.sentiment_score,
                   d.keywords, d.counterparty,
                   d.post_1h_change, d.post_1d_change, d.post_3d_change,
                   d.amount AS contract_amount,
                   COALESCE(NULLIF(s.market, 'UNKNOWN'), '-') AS market
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
        return [_parse_keywords(dict(r)) for r in rows]

    async def get_by_rcept_no(self, rcept_no: str) -> dict:
        row = await self.db.fetchrow(
            "SELECT * FROM disclosures WHERE rcept_no = $1", rcept_no
        )
        if not row:
            return {}
        return _parse_keywords(dict(row))

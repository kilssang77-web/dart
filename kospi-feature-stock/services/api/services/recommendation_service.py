"""
매매 추천 비즈니스 로직 서비스.
"""
import json
import asyncpg
import redis.asyncio as redis_lib
from deps import cached_fetch, enrich_live_prices
from schemas.responses import (
    RecommendationResponse, PerformanceStatsResponse, CodeSignalsResponse, SignalItem,
)

_MAX_PROB = 0.95


async def _enrich_similar_cases_names(db: asyncpg.Pool, dicts: list[dict]) -> None:
    """similar_cases 항목에 name이 없는 경우 stocks 테이블에서 일괄 보완."""
    codes: set[str] = set()
    for d in dicts:
        for sc in (d.get("similar_cases") or []):
            if isinstance(sc, dict) and not sc.get("name") and sc.get("code"):
                codes.add(sc["code"])
    if not codes:
        return
    rows = await db.fetch("SELECT code, name FROM stocks WHERE code = ANY($1::text[])", list(codes))
    name_map = {r["code"]: r["name"] for r in rows}
    for d in dicts:
        for sc in (d.get("similar_cases") or []):
            if isinstance(sc, dict) and not sc.get("name") and sc.get("code"):
                sc["name"] = name_map.get(sc["code"], sc["code"])


def _parse_json_fields(d: dict) -> dict:
    for key in ("rationale", "similar_cases"):
        if isinstance(d.get(key), str):
            try:
                d[key] = json.loads(d[key])
            except Exception:
                d[key] = {} if key == "rationale" else []
    if "success_prob" in d and d["success_prob"] is not None:
        d["success_prob"] = min(_MAX_PROB, float(d["success_prob"]))
    return d


class RecommendationService:

    def __init__(self, db: asyncpg.Pool, redis: redis_lib.Redis):
        self.db    = db
        self.redis = redis

    def _build_where(
        self,
        action:   str | None,
        market:   str | None,
        code:     str | None,
        min_prob: float,
        hours:    int,
    ) -> tuple[list[str], list]:
        where  = [
            "r.created_at >= NOW() - ($1 * INTERVAL '1 hour')",
            "r.success_prob >= $2",
        ]
        params: list = [hours, min_prob]

        if action:
            params.append(action.upper())
            where.append(f"r.action = ${len(params)}")
        if code:
            params.append(code.upper())
            where.append(f"r.code = ${len(params)}")
        if market:
            params.append(market.upper())
            where.append(f"s.market = ${len(params)}")
        else:
            where.append("s.market IN ('KOSPI', 'KOSDAQ')")

        return where, params

    async def list_recommendations(
        self,
        action:   str | None,
        market:   str | None,
        code:     str | None,
        min_prob: float,
        hours:    int,
        limit:    int,
        dedupe:   bool,
    ) -> list[RecommendationResponse]:
        where, params = self._build_where(action, market, code, min_prob, hours)
        params.append(limit)
        limit_ph      = f"${len(params)}"
        where_clause  = " AND ".join(where)

        if dedupe:
            query = f"""
            WITH base AS (
                SELECT
                    r.id, (r.created_at AT TIME ZONE 'Asia/Seoul')::TEXT AS created_at, r.code,
                    COALESCE(s.name, r.code)   AS name,
                    COALESCE(NULLIF(s.market, 'UNKNOWN'), '-')    AS market,
                    r.action, r.entry_price, r.target_price, r.stop_loss_price,
                    r.expected_hold_days, r.success_prob, r.expected_return,
                    r.risk_score, r.risk_reward_ratio,
                    r.rationale, r.similar_cases,
                    r.feature_event_id,
                    COALESCE(db.close, r.entry_price)  AS current_price,
                    COALESCE(db.change_rate, 0)        AS current_change_rate,
                    (r.created_at AT TIME ZONE 'Asia/Seoul')::TEXT AS fe_detected_at,
                    (SELECT COUNT(*) FROM recommendations r2
                     WHERE r2.code = r.code
                       AND r2.created_at >= NOW() - INTERVAL '168 hours') AS rec_count,
                    ROW_NUMBER() OVER (
                        PARTITION BY r.code
                        ORDER BY r.success_prob DESC, r.created_at DESC
                    ) AS rn
                FROM recommendations r
                LEFT JOIN stocks s ON s.code = r.code
                LEFT JOIN LATERAL (
                    SELECT close, change_rate FROM daily_bars
                    WHERE code = r.code ORDER BY date DESC LIMIT 1
                ) db ON true
                WHERE {where_clause}
            )
            SELECT id, created_at, code, name, market, action,
                   entry_price, target_price, stop_loss_price,
                   expected_hold_days, success_prob, expected_return,
                   risk_score, risk_reward_ratio, rationale, similar_cases, rec_count,
                   feature_event_id, current_price, current_change_rate, fe_detected_at
            FROM base WHERE rn = 1
            ORDER BY success_prob DESC
            LIMIT {limit_ph}
            """
        else:
            query = f"""
            SELECT
                r.id, (r.created_at AT TIME ZONE 'Asia/Seoul')::TEXT AS created_at, r.code,
                COALESCE(s.name, r.code)   AS name,
                COALESCE(NULLIF(s.market, 'UNKNOWN'), '-')    AS market,
                r.action, r.entry_price, r.target_price, r.stop_loss_price,
                r.expected_hold_days, r.success_prob, r.expected_return,
                r.risk_score, r.risk_reward_ratio,
                r.rationale, r.similar_cases,
                r.feature_event_id,
                1 AS rec_count,
                COALESCE(db.close, r.entry_price)  AS current_price,
                COALESCE(db.change_rate, 0)        AS current_change_rate,
                (r.created_at AT TIME ZONE 'Asia/Seoul')::TEXT AS fe_detected_at
            FROM recommendations r
            LEFT JOIN stocks s ON s.code = r.code
            LEFT JOIN LATERAL (
                SELECT close, change_rate FROM daily_bars
                WHERE code = r.code ORDER BY date DESC LIMIT 1
            ) db ON true
            WHERE {where_clause}
            ORDER BY r.success_prob DESC, r.created_at DESC
            LIMIT {limit_ph}
            """

        cache_key = f"recs:{action}:{market}:{code}:{min_prob}:{limit}:{dedupe}"
        rows  = await cached_fetch(self.redis, self.db, cache_key, query, *params, ttl=60)
        dicts = [dict(r) for r in rows]
        [_parse_json_fields(d) for d in dicts]
        await _enrich_similar_cases_names(self.db, dicts)
        await enrich_live_prices(self.redis, dicts, price_field="current_price", rate_field="current_change_rate")
        return [RecommendationResponse(**d) for d in dicts]

    async def performance_stats(self, days: int) -> PerformanceStatsResponse:
        row = await self.db.fetchrow(
            """
            SELECT
                COUNT(*)                                        AS total_count,
                COUNT(*) FILTER (WHERE action='BUY')            AS buy_count,
                COUNT(*) FILTER (WHERE is_success=TRUE)         AS success_count,
                ROUND(AVG(actual_return)::NUMERIC, 4)           AS avg_return,
                ROUND(AVG(success_prob)::NUMERIC, 3)            AS avg_pred_prob
            FROM recommendations
            WHERE created_at >= NOW() - ($1 * INTERVAL '1 day')
              AND actual_return IS NOT NULL
            """,
            days,
        )
        result = dict(row)
        buy    = result.get("buy_count") or 1
        result["success_rate"] = round((result.get("success_count") or 0) / buy, 3)
        return PerformanceStatsResponse(**result)

    async def code_signals(self, code: str, hours: int) -> CodeSignalsResponse:
        rows = await self.db.fetch(
            """
            SELECT
                r.id, (r.created_at AT TIME ZONE 'Asia/Seoul')::TEXT AS created_at, r.code,
                COALESCE(s.name, r.code)                    AS name,
                COALESCE(NULLIF(s.market, 'UNKNOWN'), '-')  AS market,
                r.action, r.entry_price, r.target_price, r.stop_loss_price,
                r.expected_hold_days, r.success_prob, r.expected_return,
                r.risk_score, r.risk_reward_ratio,
                r.rationale, r.similar_cases,
                1 AS rec_count,
                COALESCE(db.close, r.entry_price)  AS current_price,
                COALESCE(db.change_rate, 0)        AS current_change_rate,
                fe.event_type                      AS fe_event_type,
                fe.signal_score                    AS fe_signal_score,
                (fe.detected_at AT TIME ZONE 'Asia/Seoul')::TEXT AS fe_detected_at
            FROM recommendations r
            LEFT JOIN stocks s ON s.code = r.code
            LEFT JOIN feature_events fe
                ON fe.id = r.feature_event_id
               AND fe.detected_at >= NOW() - (($2 + 48) * INTERVAL '1 hour')
            LEFT JOIN LATERAL (
                SELECT close, change_rate FROM daily_bars
                WHERE code = r.code ORDER BY date DESC LIMIT 1
            ) db ON true
            WHERE r.code = $1
              AND r.created_at >= NOW() - ($2 * INTERVAL '1 hour')
            ORDER BY r.created_at DESC
            LIMIT 200
            """,
            code.upper(), hours,
        )
        dicts = [dict(r) for r in rows]
        [_parse_json_fields(d) for d in dicts]
        await _enrich_similar_cases_names(self.db, dicts)
        await enrich_live_prices(self.redis, dicts, price_field="current_price", rate_field="current_change_rate")
        items = [SignalItem(**d) for d in dicts]
        return CodeSignalsResponse(total_count=len(items), signals=items)

from fastapi import APIRouter, Depends, Query, HTTPException
import asyncpg
import json
from deps import get_db
from schemas.responses import RecommendationResponse, PerformanceStatsResponse


def _parse_json_fields(d: dict) -> dict:
    for key in ("rationale", "similar_cases"):
        if isinstance(d.get(key), str):
            try:
                d[key] = json.loads(d[key])
            except Exception:
                d[key] = {} if key == "rationale" else []
    return d

router = APIRouter()


@router.get("", response_model=list[RecommendationResponse])
async def list_recommendations(
    action: str | None = None,
    market: str | None = None,
    min_prob: float = Query(default=0.35, ge=0.0, le=1.0),
    hours: int = Query(default=24, le=168),
    limit: int = Query(default=30, le=100),
    db: asyncpg.Pool = Depends(get_db),
):
    where = ["r.created_at >= NOW()-($1 * INTERVAL '1 hour')", "r.success_prob >= $2"]
    params: list = [hours, min_prob]

    if action:
        params.append(action.upper())
        where.append(f"r.action = ${len(params)}")

    if market:
        params.append(market.upper())
        where.append(f"s.market = ${len(params)}")

    params.append(limit)
    rows = await db.fetch(
        f"""
        SELECT
            r.id, r.created_at::TEXT, r.code,
            COALESCE(s.name, r.code)   AS name,
            COALESCE(s.market, '-')    AS market,
            r.action, r.entry_price, r.target_price, r.stop_loss_price,
            r.expected_hold_days, r.success_prob, r.expected_return,
            r.risk_score, r.risk_reward_ratio,
            r.rationale, r.similar_cases
        FROM recommendations r
        LEFT JOIN stocks s ON s.code = r.code
        WHERE {' AND '.join(where)}
        ORDER BY r.success_prob DESC, r.created_at DESC
        LIMIT ${len(params)}
        """,
        *params,
    )
    return [_parse_json_fields(dict(r)) for r in rows]


@router.get("/buy", response_model=list[RecommendationResponse])
async def get_buy_signals(
    min_prob: float = Query(default=0.35, ge=0.0, le=1.0),
    db: asyncpg.Pool = Depends(get_db),
):
    rows = await db.fetch(
        """
        SELECT
            r.id, r.code,
            COALESCE(s.name, r.code)   AS name,
            COALESCE(s.market, '-')    AS market,
            COALESCE(s.sector, '-')    AS sector,
            r.entry_price, r.target_price, r.stop_loss_price,
            r.success_prob, r.expected_return, r.risk_score,
            r.risk_reward_ratio, r.expected_hold_days,
            r.created_at::TEXT
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


# /stats/performance 는 /{code}/latest 보다 반드시 먼저 선언해야 함
@router.get("/stats/performance", response_model=PerformanceStatsResponse)
async def performance_stats(
    days: int = Query(default=30, le=90),
    db: asyncpg.Pool = Depends(get_db),
):
    row = await db.fetchrow(
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
    buy = result.get("buy_count") or 1
    result["success_rate"] = round((result.get("success_count") or 0) / buy, 3)
    return PerformanceStatsResponse(**result)


@router.get("/{code}/latest", response_model=RecommendationResponse)
async def get_latest(code: str, db: asyncpg.Pool = Depends(get_db)):
    row = await db.fetchrow(
        """
        SELECT r.*, COALESCE(s.name, r.code) AS name
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

from fastapi import APIRouter, Depends, Query
from datetime import datetime, timedelta, timezone
import asyncpg
from deps import get_db

router = APIRouter()

EVENT_TYPES = [
    "VOLUME_SURGE", "AMOUNT_SURGE",
    "BREAKOUT_52W", "BREAKOUT_26W", "BREAKOUT_13W", "BREAKOUT_20D",
    "VI_TRIGGERED", "LONG_WHITE_CANDLE", "HAMMER_CANDLE", "MORNING_STAR",
    "SUPPLY_ANOMALY", "POST_DISCLOSURE_SURGE",
]


@router.get("")
async def list_features(
    event_type: str | None = None,
    code: str | None = None,
    market: str | None = None,
    min_score: float = Query(default=0.5, ge=0.0, le=1.0),
    hours: int = Query(default=24, le=168),
    limit: int = Query(default=50, le=200),
    dedupe: bool = Query(default=False, description="종목당 최고점수 1건만 반환, all_event_types 포함"),
    db: asyncpg.Pool = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    where = ["fe.detected_at >= $1", "fe.signal_score >= $2"]
    params: list = [since, min_score]

    if event_type:
        params.append(event_type)
        where.append(f"fe.event_type = ${len(params)}")

    if code:
        params.append(code.upper())
        where.append(f"fe.code = ${len(params)}")
        dedupe = False  # 특정 종목 조회 시 전체 시그널 표시

    if market:
        params.append(market.upper())
        where.append(f"s.market = ${len(params)}")

    where_clause = " AND ".join(where)

    params.append(limit)
    limit_placeholder = f"${len(params)}"

    if dedupe:
        query = f"""
        WITH base AS (
            SELECT
                fe.id, fe.detected_at::TEXT, fe.code,
                COALESCE(s.name, fe.code) AS name,
                COALESCE(s.market, '-')   AS market,
                COALESCE(s.sector, '-')   AS sector,
                fe.event_type, fe.price, fe.change_rate,
                COALESCE(fe.volume, db.volume)       AS volume,
                fe.volume_ratio,
                COALESCE(fe.amount, db.amount)       AS amount,
                fe.signal_score, fe.risk_score,
                fe.result_1d, fe.result_3d, fe.result_5d
            FROM feature_events fe
            LEFT JOIN stocks s ON s.code = fe.code
            LEFT JOIN LATERAL (
                SELECT volume, amount FROM daily_bars
                WHERE code = fe.code ORDER BY date DESC LIMIT 1
            ) db ON true
            WHERE {where_clause}
        ),
        agg AS (
            SELECT code, ARRAY_AGG(DISTINCT event_type ORDER BY event_type) AS all_event_types
            FROM base GROUP BY code
        ),
        ranked AS (
            SELECT base.*, agg.all_event_types,
                   ROW_NUMBER() OVER (
                       PARTITION BY base.code
                       ORDER BY base.signal_score DESC, base.detected_at DESC
                   ) AS rn
            FROM base JOIN agg USING (code)
        )
        SELECT id, detected_at, code, name, market, sector,
               event_type, price, change_rate, volume, volume_ratio, amount,
               signal_score, risk_score, result_1d, result_3d, result_5d,
               all_event_types
        FROM ranked WHERE rn = 1
        ORDER BY signal_score DESC
        LIMIT {limit_placeholder}
        """
    else:
        query = f"""
        SELECT
            fe.id, fe.detected_at::TEXT, fe.code,
            COALESCE(s.name, fe.code) AS name,
            COALESCE(s.market, '-')   AS market,
            COALESCE(s.sector, '-')   AS sector,
            fe.event_type, fe.price, fe.change_rate,
            COALESCE(fe.volume, db.volume)       AS volume,
            fe.volume_ratio,
            COALESCE(fe.amount, db.amount)       AS amount,
            fe.signal_score, fe.risk_score,
            fe.result_1d, fe.result_3d, fe.result_5d,
            NULL::text[] AS all_event_types
        FROM feature_events fe
        LEFT JOIN stocks s ON s.code = fe.code
        LEFT JOIN LATERAL (
            SELECT volume, amount FROM daily_bars
            WHERE code = fe.code ORDER BY date DESC LIMIT 1
        ) db ON true
        WHERE {where_clause}
        ORDER BY fe.signal_score DESC, fe.detected_at DESC
        LIMIT {limit_placeholder}
        """

    rows = await db.fetch(query, *params)
    return [dict(r) for r in rows]


@router.get("/types")
async def get_event_types():
    return EVENT_TYPES


# /today/summary 는 /{event_id} 보다 반드시 먼저 선언해야 함
@router.get("/today/summary")
async def today_summary(db: asyncpg.Pool = Depends(get_db)):
    row = await db.fetchrow(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE event_type = 'VOLUME_SURGE')          AS volume_surge,
            COUNT(*) FILTER (WHERE event_type = 'AMOUNT_SURGE')          AS amount_surge,
            COUNT(*) FILTER (WHERE event_type = 'BREAKOUT_52W')          AS breakout_52w,
            COUNT(*) FILTER (WHERE event_type = 'BREAKOUT_26W')          AS breakout_26w,
            COUNT(*) FILTER (WHERE event_type = 'BREAKOUT_13W')          AS breakout_13w,
            COUNT(*) FILTER (WHERE event_type = 'BREAKOUT_20D')          AS breakout_20d,
            COUNT(*) FILTER (WHERE event_type = 'VI_TRIGGERED')          AS vi_triggered,
            COUNT(*) FILTER (WHERE event_type = 'LONG_WHITE_CANDLE')     AS long_white_candle,
            COUNT(*) FILTER (WHERE event_type = 'HAMMER_CANDLE')         AS hammer_candle,
            COUNT(*) FILTER (WHERE event_type = 'SUPPLY_ANOMALY')        AS supply_anomaly,
            COUNT(*) FILTER (WHERE event_type = 'POST_DISCLOSURE_SURGE') AS post_disclosure_surge,
            COUNT(*) FILTER (WHERE signal_score >= 0.7)                  AS high_score,
            ROUND(AVG(signal_score)::NUMERIC, 3)                         AS avg_score
        FROM feature_events
        WHERE detected_at >= CURRENT_DATE
        """
    )
    d = dict(row)
    by_type = {
        "VOLUME_SURGE":          d.pop("volume_surge", 0),
        "AMOUNT_SURGE":          d.pop("amount_surge", 0),
        "BREAKOUT_52W":          d.pop("breakout_52w", 0),
        "BREAKOUT_26W":          d.pop("breakout_26w", 0),
        "BREAKOUT_13W":          d.pop("breakout_13w", 0),
        "BREAKOUT_20D":          d.pop("breakout_20d", 0),
        "VI_TRIGGERED":          d.pop("vi_triggered", 0),
        "LONG_WHITE_CANDLE":     d.pop("long_white_candle", 0),
        "HAMMER_CANDLE":         d.pop("hammer_candle", 0),
        "SUPPLY_ANOMALY":        d.pop("supply_anomaly", 0),
        "POST_DISCLOSURE_SURGE": d.pop("post_disclosure_surge", 0),
    }
    d["by_type"] = {k: v for k, v in by_type.items() if v}
    d["date"] = datetime.now().strftime("%Y-%m-%d")
    return d


@router.get("/{event_id}/similar")
async def get_similar(
    event_id: int,
    top_k: int = Query(default=10, le=30),
    db: asyncpg.Pool = Depends(get_db),
):
    event = await db.fetchrow(
        "SELECT code, event_type, pattern_vector FROM feature_events WHERE id = $1",
        event_id,
    )
    if not event:
        return []

    if event["pattern_vector"]:
        rows = await db.fetch(
            """
            SELECT
                id, code, detected_at::TEXT, event_type,
                ROUND((1 - (pattern_vector <=> $1::vector))::NUMERIC, 4) AS similarity,
                result_1d, result_3d, result_5d, signal_score
            FROM feature_events
            WHERE id != $2
              AND pattern_vector IS NOT NULL
            ORDER BY pattern_vector <=> $1::vector
            LIMIT $3
            """,
            event["pattern_vector"], event_id, top_k,
        )
        if rows:
            return [dict(r) for r in rows]

    # Fallback: same stock historical events
    rows = await db.fetch(
        """
        SELECT
            id, code, detected_at::TEXT, event_type,
            NULL::numeric AS similarity,
            result_1d, result_3d, result_5d, signal_score
        FROM feature_events
        WHERE code = $1 AND id != $2
        ORDER BY detected_at DESC
        LIMIT $3
        """,
        event["code"], event_id, top_k,
    )
    return [dict(r) for r in rows]


@router.get("/{event_id}")
async def get_feature(event_id: int, db: asyncpg.Pool = Depends(get_db)):
    row = await db.fetchrow(
        """
        SELECT fe.*, s.name, s.market, s.sector
        FROM feature_events fe
        JOIN stocks s ON s.code = fe.code
        WHERE fe.id = $1
        """,
        event_id,
    )
    return dict(row) if row else {}

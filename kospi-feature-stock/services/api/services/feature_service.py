"""
특징주 이벤트 비즈니스 로직 서비스.
라우터에서 직접 SQL을 작성하지 않고 이 서비스를 호출한다.
"""
from datetime import datetime, timedelta, timezone
import asyncpg
import redis.asyncio as redis_lib
from deps import cached_fetch

EVENT_TYPES = [
    "VOLUME_SURGE", "AMOUNT_SURGE",
    "BREAKOUT_52W", "BREAKOUT_26W", "BREAKOUT_13W", "BREAKOUT_20D",
    "VI_TRIGGERED", "LONG_WHITE_CANDLE", "HAMMER_CANDLE", "MORNING_STAR",
    "SUPPLY_ANOMALY", "POST_DISCLOSURE_SURGE",
    "SHORT_SURGE", "DUAL_BUY_STREAK",
]


class FeatureService:

    def __init__(self, db: asyncpg.Pool, redis: redis_lib.Redis):
        self.db    = db
        self.redis = redis

    # ── 쿼리 빌더 ─────────────────────────────────────────────────

    def _build_where(
        self,
        event_type: str | None,
        code:       str | None,
        market:     str | None,
        min_score:  float,
        hours:      int,
    ) -> tuple[list[str], list]:
        since  = datetime.now(timezone.utc) - timedelta(hours=hours)
        where  = ["fe.detected_at >= $1", "fe.signal_score >= $2"]
        params: list = [since, min_score]

        if event_type:
            params.append(event_type)
            where.append(f"fe.event_type = ${len(params)}")
        if code:
            params.append(code.upper())
            where.append(f"fe.code = ${len(params)}")
        if market:
            params.append(market.upper())
            where.append(f"s.market = ${len(params)}")
        else:
            where.append("s.market IN ('KOSPI', 'KOSDAQ')")

        return where, params

    # ── 공개 메서드 ───────────────────────────────────────────────

    async def list_features(
        self,
        event_type: str | None,
        code:       str | None,
        market:     str | None,
        min_score:  float,
        hours:      int,
        limit:      int,
        dedupe:     bool,
    ) -> list[dict]:
        if code:
            dedupe = False  # 특정 종목은 전체 시그널 표시

        where, params = self._build_where(event_type, code, market, min_score, hours)
        where_clause  = " AND ".join(where)
        params.append(limit)
        limit_ph = f"${len(params)}"

        if dedupe:
            query = f"""
            WITH base AS (
                SELECT
                    fe.id, (fe.detected_at AT TIME ZONE 'Asia/Seoul')::TEXT AS detected_at, fe.code,
                    COALESCE(s.name, fe.code) AS name,
                    COALESCE(NULLIF(s.market, 'UNKNOWN'), '-')   AS market,
                    COALESCE(s.sector, '-')   AS sector,
                    fe.event_type, fe.price, fe.change_rate,
                    COALESCE(fe.volume, db.volume)       AS volume,
                    fe.volume_ratio,
                    COALESCE(fe.amount, db.amount)       AS amount,
                    fe.signal_score, fe.risk_score,
                    fe.result_1d, fe.result_3d, fe.result_5d
                FROM feature_events fe
                JOIN stocks s ON s.code = fe.code
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
            LIMIT {limit_ph}
            """
        else:
            query = f"""
            SELECT
                fe.id, (fe.detected_at AT TIME ZONE 'Asia/Seoul')::TEXT AS detected_at, fe.code,
                COALESCE(s.name, fe.code) AS name,
                COALESCE(NULLIF(s.market, 'UNKNOWN'), '-')   AS market,
                COALESCE(s.sector, '-')   AS sector,
                fe.event_type, fe.price, fe.change_rate,
                COALESCE(fe.volume, db.volume)       AS volume,
                fe.volume_ratio,
                COALESCE(fe.amount, db.amount)       AS amount,
                fe.signal_score, fe.risk_score,
                fe.result_1d, fe.result_3d, fe.result_5d,
                NULL::text[] AS all_event_types
            FROM feature_events fe
            JOIN stocks s ON s.code = fe.code
            LEFT JOIN LATERAL (
                SELECT volume, amount FROM daily_bars
                WHERE code = fe.code ORDER BY date DESC LIMIT 1
            ) db ON true
            WHERE {where_clause}
            ORDER BY fe.signal_score DESC, fe.detected_at DESC
            LIMIT {limit_ph}
            """

        if code:
            rows = await self.db.fetch(query, *params)
            return [dict(r) for r in rows]

        cache_key = f"features:{event_type}:{market}:{min_score}:{hours}:{limit}:{dedupe}"
        return await cached_fetch(self.redis, self.db, cache_key, query, *params, ttl=30)

    async def today_summary(self) -> dict:
        row = await self.db.fetchrow(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE fe.event_type = 'VOLUME_SURGE')          AS volume_surge,
                COUNT(*) FILTER (WHERE fe.event_type = 'AMOUNT_SURGE')          AS amount_surge,
                COUNT(*) FILTER (WHERE fe.event_type = 'BREAKOUT_52W')          AS breakout_52w,
                COUNT(*) FILTER (WHERE fe.event_type = 'BREAKOUT_26W')          AS breakout_26w,
                COUNT(*) FILTER (WHERE fe.event_type = 'BREAKOUT_13W')          AS breakout_13w,
                COUNT(*) FILTER (WHERE fe.event_type = 'BREAKOUT_20D')          AS breakout_20d,
                COUNT(*) FILTER (WHERE fe.event_type = 'VI_TRIGGERED')          AS vi_triggered,
                COUNT(*) FILTER (WHERE fe.event_type = 'LONG_WHITE_CANDLE')     AS long_white_candle,
                COUNT(*) FILTER (WHERE fe.event_type = 'HAMMER_CANDLE')         AS hammer_candle,
                COUNT(*) FILTER (WHERE fe.event_type = 'MORNING_STAR')          AS morning_star,
                COUNT(*) FILTER (WHERE fe.event_type = 'SUPPLY_ANOMALY')        AS supply_anomaly,
                COUNT(*) FILTER (WHERE fe.event_type = 'POST_DISCLOSURE_SURGE') AS post_disclosure_surge,
                COUNT(*) FILTER (WHERE fe.event_type = 'SHORT_SURGE')           AS short_surge,
                COUNT(*) FILTER (WHERE fe.event_type = 'DUAL_BUY_STREAK')       AS dual_buy_streak,
                COUNT(*) FILTER (WHERE fe.signal_score >= 0.7)                  AS high_score,
                ROUND(AVG(fe.signal_score)::NUMERIC, 3)                         AS avg_score
            FROM feature_events fe
            JOIN stocks s ON s.code = fe.code
            WHERE fe.detected_at >= date_trunc('day', NOW() AT TIME ZONE 'Asia/Seoul') AT TIME ZONE 'Asia/Seoul'
              AND s.market IN ('KOSPI', 'KOSDAQ')
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
            "MORNING_STAR":          d.pop("morning_star", 0),
            "SUPPLY_ANOMALY":        d.pop("supply_anomaly", 0),
            "POST_DISCLOSURE_SURGE": d.pop("post_disclosure_surge", 0),
            "SHORT_SURGE":           d.pop("short_surge", 0),
            "DUAL_BUY_STREAK":       d.pop("dual_buy_streak", 0),
        }
        d["by_type"] = {k: v for k, v in by_type.items() if v}
        d["date"] = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")
        return d

    async def get_similar(self, event_id: int, top_k: int) -> list[dict]:
        event = await self.db.fetchrow(
            """
            SELECT fe.code, fe.event_type, fe.signal_score, fe.pattern_vector,
                   COALESCE(s.sector, '-') AS sector
            FROM feature_events fe
            LEFT JOIN stocks s ON s.code = fe.code
            WHERE fe.id = $1
            """,
            event_id,
        )
        if not event:
            return []

        if event["pattern_vector"]:
            # HNSW/IVFFlat 양쪽 파라미터 SET — 활성 인덱스 타입에만 적용됨
            async with self.db.acquire() as conn:
                async with conn.transaction():
                    await conn.execute("SET LOCAL ivfflat.probes = 10")
                    await conn.execute("SET LOCAL hnsw.ef_search = 100")
                    candidates = await conn.fetch(
                        """
                        SELECT
                            fe.id, fe.code, fe.event_type, fe.signal_score,
                            (fe.detected_at AT TIME ZONE 'Asia/Seoul')::TEXT AS detected_at,
                            ROUND((1 - (fe.pattern_vector <=> $1::vector))::NUMERIC, 4) AS vec_sim,
                            fe.result_1d, fe.result_3d, fe.result_5d,
                            COALESCE(s.sector, '-') AS sector,
                            COALESCE(s.name, fe.code) AS name
                        FROM feature_events fe
                        LEFT JOIN stocks s ON s.code = fe.code
                        WHERE fe.code != $2
                          AND fe.pattern_vector IS NOT NULL
                          AND fe.result_5d IS NOT NULL
                        ORDER BY fe.pattern_vector <=> $1::vector
                        LIMIT $3
                        """,
                        event["pattern_vector"], event["code"], top_k * 4,
                        timeout=60,
                    )
            if candidates:
                src_event_type = event["event_type"] or ""
                src_sector     = event["sector"] or "-"
                src_score      = float(event["signal_score"] or 0.5)

                def _combined(row: dict) -> float:
                    vec_sim    = float(row["vec_sim"] or 0.0)
                    et_bonus   = 0.20 if row["event_type"] == src_event_type else 0.0
                    sec_bonus  = 0.15 if (row["sector"] not in ("-", None) and row["sector"] == src_sector) else 0.0
                    score_diff = abs(float(row["signal_score"] or 0.5) - src_score)
                    sc_bonus   = 0.05 * max(0.0, 1.0 - score_diff)
                    return vec_sim * 0.60 + et_bonus + sec_bonus + sc_bonus

                ranked = sorted(candidates, key=lambda r: _combined(dict(r)), reverse=True)[:top_k]
                return [
                    {**dict(r), "similarity": round(_combined(dict(r)), 4)}
                    for r in ranked
                ]

        rows = await self.db.fetch(
            """
            SELECT
                fe.id, fe.code, (fe.detected_at AT TIME ZONE 'Asia/Seoul')::TEXT AS detected_at, fe.event_type,
                NULL::numeric AS similarity,
                fe.result_1d, fe.result_3d, fe.result_5d, fe.signal_score,
                COALESCE(s.name, fe.code) AS name
            FROM feature_events fe
            LEFT JOIN stocks s ON s.code = fe.code
            WHERE fe.code = $1 AND fe.id != $2
            ORDER BY fe.detected_at DESC
            LIMIT $3
            """,
            event["code"], event_id, top_k,
        )
        return [dict(r) for r in rows]

    async def get_by_id(self, event_id: int) -> dict:
        row = await self.db.fetchrow(
            """
            SELECT fe.*, s.name, s.market, s.sector
            FROM feature_events fe
            JOIN stocks s ON s.code = fe.code
            WHERE fe.id = $1
            """,
            event_id,
        )
        return dict(row) if row else {}

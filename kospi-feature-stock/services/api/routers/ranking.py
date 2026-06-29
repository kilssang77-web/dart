"""ranking.py — 종합점수 랭킹 API.

종합점수 = ML확률(40%) + 수급점수(30%) + 기술점수(20%) + 모멘텀점수(10%)
"""
from fastapi import APIRouter, Depends, Query
from typing import List, Optional
import asyncpg
import redis.asyncio as redis_lib
import orjson
import logging
from datetime import datetime, timezone, timedelta

from deps import get_db, get_redis

router = APIRouter()
logger = logging.getLogger("ranking")

_KST = timezone(timedelta(hours=9))


async def _build_ranking(
    db: asyncpg.Pool,
    market: str = "ALL",
    limit: int = 100,
) -> list[dict]:
    """종합점수 계산 및 랭킹 반환."""

    market_filter = ""
    if market == "KOSPI":
        market_filter = "AND s.market = 'KOSPI'"
    elif market == "KOSDAQ":
        market_filter = "AND s.market = 'KOSDAQ'"

    # 최신 날짜 먼저 확인
    latest_date = await db.fetchval("""
        SELECT date FROM (
            SELECT date, COUNT(*) AS cnt FROM daily_bars
            GROUP BY date ORDER BY date DESC
        ) sub WHERE cnt >= 100 LIMIT 1
    """)
    if not latest_date:
        return []

    prev_date = await db.fetchval(
        "SELECT MAX(date) FROM daily_bars WHERE date < $1", latest_date
    )
    prev5_date = await db.fetchval(
        """SELECT date FROM daily_bars
           WHERE date < $1 GROUP BY date ORDER BY date DESC LIMIT 1 OFFSET 4""",
        latest_date
    )

    rows = await db.fetch(f"""
        WITH
        cur AS (
            SELECT db.code, db.close, db.volume,
                   COALESCE(
                       CASE WHEN db.change_rate IS NOT NULL AND db.change_rate <> 0
                            THEN db.change_rate
                            WHEN p.close IS NOT NULL AND p.close > 0
                            THEN ROUND(((db.close - p.close)::NUMERIC / p.close * 100), 2)
                            ELSE 0
                       END, 0
                   ) AS change_rate
            FROM daily_bars db
            LEFT JOIN daily_bars p ON p.code = db.code AND p.date = $2
            WHERE db.date = $1 AND db.close > 0
        ),
        w52 AS (
            SELECT code, MAX(high) AS high52, MIN(low) AS low52
            FROM daily_bars
            WHERE date >= $1::DATE - INTERVAL '252 days'
            GROUP BY code
        ),
        mom5 AS (
            SELECT p5.code,
                   (cur.close - p5.close) / NULLIF(p5.close, 0) * 100 AS ret5d
            FROM daily_bars p5
            JOIN cur ON cur.code = p5.code
            WHERE p5.date = $3
        ),
        sup AS (
            SELECT code,
                   SUM(foreign_net)      AS foreign_net5,
                   MAX(ABS(foreign_net)) AS foreign_max
            FROM supply_demand
            WHERE date >= $1::DATE - INTERVAL '7 days'
            GROUP BY code
        ),
        ml AS (
            SELECT code,
                   MAX((signal_data->>'ml_prob')::FLOAT) AS ml_prob
            FROM feature_events
            WHERE detected_at >= $1::TIMESTAMPTZ - INTERVAL '30 days'
              AND signal_data->>'ml_prob' IS NOT NULL
            GROUP BY code
        )
        SELECT
            s.code, s.name, s.market, s.sector,
            cur.close AS current_price, cur.change_rate AS change_pct, cur.volume,
            w52.high52, w52.low52,
            ml.ml_prob, sup.foreign_net5, sup.foreign_max, mom5.ret5d
        FROM stocks s
        JOIN cur  ON cur.code = s.code
        LEFT JOIN w52  ON w52.code = s.code
        LEFT JOIN ml   ON ml.code = s.code
        LEFT JOIN sup  ON sup.code = s.code
        LEFT JOIN mom5 ON mom5.code = s.code
        WHERE s.is_active = TRUE {market_filter}
          AND s.market IN ('KOSPI', 'KOSDAQ')
        ORDER BY s.code
    """, latest_date, prev_date, prev5_date or prev_date)

    results = []
    for r in rows:
        code        = r["code"]
        ml_prob     = float(r["ml_prob"] or 0)
        foreign_net = float(r["foreign_net5"] or 0)
        foreign_max = float(r["foreign_max"] or 1)
        close       = float(r["current_price"] or 0)
        high52      = float(r["high52"] or close or 1)
        low52       = float(r["low52"] or 0)
        ret5d       = float(r["ret5d"] or 0)

        # ── 점수 계산 ────────────────────────────────────────────────
        # ML 점수 (40점)
        ml_score = min(40.0, ml_prob * 40)

        # 수급 점수 (30점) — foreign_net이 양수면 비례
        if foreign_net > 0 and foreign_max > 0:
            supply_score = min(30.0, (foreign_net / foreign_max) * 30)
        elif foreign_net < 0 and foreign_max > 0:
            supply_score = max(0.0, 15.0 + (foreign_net / foreign_max) * 15)
        elif foreign_net is None or foreign_max is None or foreign_max == 0:
            supply_score = 0.0
        else:
            supply_score = 0.0

        # 기술 점수 (20점) — 52주 고가 대비 현재 위치
        range52 = high52 - low52
        if range52 > 0:
            tech_score = min(20.0, ((close - low52) / range52) * 20)
        else:
            tech_score = 0.0

        # 모멘텀 점수 (10점) — 5일 수익률
        if ret5d >= 5:
            momentum_score = 10.0
        elif ret5d > 0:
            momentum_score = ret5d / 5 * 10
        elif ret5d < 0:
            momentum_score = max(0.0, 5.0 + ret5d * 0.5)
        else:
            momentum_score = 0.0

        total_score = ml_score + supply_score + tech_score + momentum_score

        # 리스크 레벨
        if total_score >= 70:
            risk_level = "LOW"
        elif total_score >= 50:
            risk_level = "MEDIUM"
        else:
            risk_level = "HIGH"

        # 기대수익 (52주 고가까지 상승 여력)
        expected_return = ((high52 - close) / close * 100) if close > 0 else 0

        results.append({
            "code":           code,
            "name":           r["name"],
            "market":         r["market"],
            "sector":         r["sector"],
            "current_price":  int(close),
            "change_pct":     float(r["change_pct"] or 0),
            "volume":         int(r["volume"] or 0),
            "score":          round(total_score, 1),
            "ml_score":       round(ml_score, 1),
            "supply_score":   round(supply_score, 1),
            "tech_score":     round(tech_score, 1),
            "momentum_score": round(momentum_score, 1),
            "expected_return": round(expected_return, 1),
            "risk_level":     risk_level,
        })

    # 종합점수 내림차순 정렬, limit 적용
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


@router.get("/daily")
async def ranking_daily(
    market:  str = Query("ALL", enum=["ALL", "KOSPI", "KOSDAQ"]),
    limit:   int = Query(100, ge=10, le=500),
    sort_by: str = Query("score", enum=["score", "supply_score", "ml_score", "momentum_score", "expected_return", "change_pct"]),
    db:      asyncpg.Pool = Depends(get_db),
    redis:   redis_lib.Redis = Depends(get_redis),
):
    """종합점수 일별 랭킹.

    Redis 1시간 캐시 사용.
    """
    today = datetime.now(_KST).strftime("%Y-%m-%d")
    cache_key = f"ranking:daily:{today}:{market}:{limit}"

    cached = await redis.get(cache_key)
    if cached:
        data = orjson.loads(cached)
    else:
        data = await _build_ranking(db, market=market, limit=limit)
        await redis.setex(cache_key, 3600, orjson.dumps(data))

    # 정렬
    if sort_by != "score":
        data = sorted(data, key=lambda x: x.get(sort_by, 0) or 0, reverse=True)

    return data


@router.get("/daily-change")
async def ranking_daily_change(
    db:    asyncpg.Pool = Depends(get_db),
    redis: redis_lib.Redis = Depends(get_redis),
):
    """전일 대비 점수 급상승 종목 (score >= 60 기준 상위 20개)."""
    today = datetime.now(_KST).strftime("%Y-%m-%d")
    cache_key = f"ranking:daily:{today}:ALL:200"

    cached = await redis.get(cache_key)
    if cached:
        data = orjson.loads(cached)
    else:
        data = await _build_ranking(db, market="ALL", limit=200)
        await redis.setex(cache_key, 3600, orjson.dumps(data))

    # 점수 높고 변화 큰 종목
    high_score = [x for x in data if x["score"] >= 60]
    return sorted(high_score, key=lambda x: x["score"], reverse=True)[:20]


@router.delete("/cache")
async def clear_ranking_cache(redis: redis_lib.Redis = Depends(get_redis)):
    """랭킹 캐시 수동 초기화 (관리자용)."""
    today = datetime.now(_KST).strftime("%Y-%m-%d")
    keys = await redis.keys(f"ranking:daily:{today}*")
    if keys:
        await redis.delete(*keys)
    return {"deleted": len(keys)}

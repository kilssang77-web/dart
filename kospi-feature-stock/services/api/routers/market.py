from fastapi import APIRouter, Depends, Query
from datetime import datetime, timedelta, timezone
import asyncpg
import asyncio
import httpx
import logging
import orjson
import os
import redis.asyncio as redis_lib
from deps import get_db, get_redis, enrich_live_prices

router = APIRouter()

# 전일 종가 대비 실시간 등락률 계산 CTE (change_rate=0 저장 문제 보정)
_CHANGE_RATE_CTE = """
WITH
latest_dt AS (SELECT MAX(date) AS d FROM daily_bars WHERE date > NOW() - INTERVAL '14 days'),
prev_dt   AS (SELECT MAX(date) AS d FROM daily_bars
               WHERE date < (SELECT d FROM latest_dt) AND date > NOW() - INTERVAL '21 days'),
computed AS (
    SELECT
        c.code,
        c.close,
        c.volume,
        c.amount,
        CASE
            WHEN c.change_rate IS NOT NULL AND c.change_rate <> 0
                THEN c.change_rate
            WHEN p.close IS NOT NULL AND p.close > 0 AND c.close IS NOT NULL
                THEN ROUND(((c.close - p.close)::NUMERIC / p.close * 100), 2)
            ELSE 0
        END AS change_rate,
        c.date
    FROM daily_bars c
    CROSS JOIN latest_dt
    LEFT JOIN daily_bars p ON p.code = c.code
                           AND p.date = (SELECT d FROM prev_dt)
    WHERE c.date = latest_dt.d AND c.close > 0
)
"""


@router.get("/summary")
async def market_summary(db: asyncpg.Pool = Depends(get_db)):
    """KOSPI/KOSDAQ 등락 현황 (직전 종가 대비 실시간 계산, UNKNOWN 제외)."""
    try:
        row = await db.fetchrow(f"""
            {_CHANGE_RATE_CTE}
            SELECT
                MAX(c.date)::TEXT AS data_date,
                ROUND(AVG(c.change_rate) FILTER (WHERE s.market='KOSPI' )::NUMERIC, 2) AS kospi_avg_change,
                ROUND(AVG(c.change_rate) FILTER (WHERE s.market='KOSDAQ')::NUMERIC, 2) AS kosdaq_avg_change,
                COUNT(*) FILTER (WHERE c.change_rate > 0 AND s.market IN ('KOSPI','KOSDAQ')) AS advancers,
                COUNT(*) FILTER (WHERE c.change_rate < 0 AND s.market IN ('KOSPI','KOSDAQ')) AS decliners,
                COUNT(*) FILTER (WHERE c.change_rate = 0 AND s.market IN ('KOSPI','KOSDAQ')) AS unchanged,
                COUNT(*) FILTER (WHERE c.change_rate > 0 AND s.market='KOSPI')  AS kospi_up,
                COUNT(*) FILTER (WHERE c.change_rate < 0 AND s.market='KOSPI')  AS kospi_down,
                COUNT(*) FILTER (WHERE c.change_rate > 0 AND s.market='KOSDAQ') AS kosdaq_up,
                COUNT(*) FILTER (WHERE c.change_rate < 0 AND s.market='KOSDAQ') AS kosdaq_down
            FROM computed c
            JOIN stocks s ON s.code = c.code
            WHERE s.market IN ('KOSPI', 'KOSDAQ')
        """, timeout=30)
        return dict(row) if row else {}
    except Exception as e:
        logger.warning(f"market/summary query failed: {e}")
        return {}


@router.get("/movers")
async def market_movers(
    market: str | None = None,
    limit: int = Query(default=10, le=30),
    db: asyncpg.Pool = Depends(get_db),
    redis: redis_lib.Redis = Depends(get_redis),
):
    """상승/하락 상위 종목. 순위는 직전 종가 기준, 현재가는 Redis 실시간 보정."""
    mkt_filter = "AND s.market = $2" if market else "AND s.market IN ('KOSPI','KOSDAQ')"
    params = [limit] + ([market.upper()] if market else [])

    try:
        rows_up = await db.fetch(f"""
            {_CHANGE_RATE_CTE}
            SELECT c.code, s.name, s.market, s.sector,
                   c.close AS price, c.change_rate, c.volume
            FROM computed c
            JOIN stocks s ON s.code = c.code
            WHERE c.change_rate IS NOT NULL {mkt_filter}
            ORDER BY c.change_rate DESC LIMIT $1
        """, *params, timeout=30)

        rows_down = await db.fetch(f"""
            {_CHANGE_RATE_CTE}
            SELECT c.code, s.name, s.market, s.sector,
                   c.close AS price, c.change_rate, c.volume
            FROM computed c
            JOIN stocks s ON s.code = c.code
            WHERE c.change_rate IS NOT NULL {mkt_filter}
            ORDER BY c.change_rate ASC LIMIT $1
        """, *params, timeout=30)
    except Exception as e:
        logger.warning(f"market/movers query failed: {e}")
        return {"gainers": [], "losers": []}

    gainers = [dict(r) for r in rows_up]
    losers  = [dict(r) for r in rows_down]
    # 실시간 호가로 price / change_rate 보정
    await enrich_live_prices(redis, gainers, price_field="price", rate_field="change_rate")
    await enrich_live_prices(redis, losers,  price_field="price", rate_field="change_rate")
    return {"gainers": gainers, "losers": losers}


@router.get("/foreign-flow")
async def foreign_flow(
    market: str | None = None,
    limit: int = Query(default=10, le=30),
    db: asyncpg.Pool = Depends(get_db),
    redis: redis_lib.Redis = Depends(get_redis),
):
    """외국인/기관 순매수 상위 종목 (UNKNOWN 제외)."""
    _ff_key = f"cache:foreign_flow:{market or 'all'}:{limit}"
    try:
        _cached = await redis.get(_ff_key)
        if _cached:
            import orjson as _orjson
            return _orjson.loads(_cached)
    except Exception:
        pass

    mkt_filter = "AND s.market = $2" if market else "AND s.market IN ('KOSPI','KOSDAQ')"
    params = [limit * 2] + ([market.upper()] if market else [])

    rows = await db.fetch(f"""
        WITH sd_ld AS (
            SELECT MAX(date) AS d FROM supply_demand
            WHERE foreign_net != 0 OR inst_net != 0
        ),
        bar_ld AS (
            SELECT MAX(date) AS d FROM daily_bars
            WHERE foreign_net_buy != 0 OR inst_net_buy != 0
        ),
        effective AS (
            SELECT
                GREATEST(sd_ld.d, bar_ld.d) AS data_date,
                sd_ld.d  AS sd_date,
                bar_ld.d AS bar_date
            FROM sd_ld CROSS JOIN bar_ld
        ),
        price_latest AS (
            SELECT code, close, change_rate
            FROM daily_bars
            WHERE date = (SELECT MAX(date) FROM daily_bars)
        )
        SELECT
            s.code, s.name, s.market, s.sector,
            COALESCE(NULLIF(sd.foreign_net, 0), db.foreign_net_buy, 0) AS foreign_net,
            COALESCE(NULLIF(sd.inst_net,   0), db.inst_net_buy,   0) AS inst_net,
            sd.foreign_hold_rate,
            pl.close       AS price,
            pl.change_rate AS change_rate,
            e.data_date::TEXT AS data_date
        FROM stocks s
        JOIN effective e ON TRUE
        LEFT JOIN supply_demand  sd ON sd.code = s.code AND sd.date = e.sd_date
        LEFT JOIN daily_bars     db ON db.code = s.code AND db.date = e.bar_date
        LEFT JOIN price_latest   pl ON pl.code = s.code
        WHERE s.is_active = TRUE
          {mkt_filter}
          AND (
              COALESCE(NULLIF(sd.foreign_net, 0), db.foreign_net_buy, 0) != 0
              OR COALESCE(NULLIF(sd.inst_net,   0), db.inst_net_buy,   0) != 0
          )
        LIMIT $1
    """, *params)

    all_rows = [dict(r) for r in rows]
    await enrich_live_prices(redis, all_rows, price_field="price", rate_field="change_rate")

    foreign_buy = sorted(
        [r for r in all_rows if (r.get("foreign_net") or 0) > 0],
        key=lambda x: -(x.get("foreign_net") or 0)
    )[:limit]
    inst_buy = sorted(
        [r for r in all_rows if (r.get("inst_net") or 0) > 0],
        key=lambda x: -(x.get("inst_net") or 0)
    )[:limit]

    result = {"foreign_buy": foreign_buy, "inst_buy": inst_buy}
    try:
        import orjson as _orjson
        await redis.set(_ff_key, _orjson.dumps(result), ex=60)
    except Exception:
        pass
    return result


_KIS_BASE = os.getenv("KIS_BASE_URL", "https://openapi.koreainvestment.com:9443")
_KIS_APP_KEY    = os.getenv("KIS_APP_KEY") or ""
_KIS_APP_SECRET = os.getenv("KIS_APP_SECRET") or ""

logger = logging.getLogger("api.market")

if not _KIS_APP_KEY or not _KIS_APP_SECRET:
    logger.warning(
        "KIS_APP_KEY / KIS_APP_SECRET 환경변수가 설정되지 않았습니다. "
        "지수 실시간 조회(/index-live)가 비활성화됩니다."
    )


async def _kis_index_quote(redis: redis_lib.Redis, market_code: str) -> dict | None:
    """KIS 지수 현재가(FHKUP03500100 inquire-daily-indexchartprice) 조회."""
    if not _KIS_APP_KEY or not _KIS_APP_SECRET:
        return None

    cache_key = f"market:idx:{market_code}"
    try:
        cached = await redis.get(cache_key)
        if cached:
            import json as _json
            return _json.loads(cached)
    except Exception as e:
        logger.debug(f"Redis cache read failed for {cache_key}: {e}")

    try:
        raw = await redis.get("kis:access_token")
        if not raw:
            return None
        token = raw.decode() if isinstance(raw, bytes) else raw
        today = datetime.now().strftime("%Y%m%d")

        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=5) as c:
                    r = await c.get(
                        f"{_KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice",
                        headers={
                            "Content-Type":  "application/json; charset=utf-8",
                            "authorization": f"Bearer {token}",
                            "appkey":        _KIS_APP_KEY,
                            "appsecret":     _KIS_APP_SECRET,
                            "tr_id":         "FHKUP03500100",
                            "custtype":      "P",
                        },
                        params={
                            "FID_COND_MRKT_DIV_CODE": "U",
                            "FID_INPUT_ISCD":         market_code,
                            "FID_INPUT_DATE_1":       today,
                            "FID_INPUT_DATE_2":       today,
                            "FID_PERIOD_DIV_CODE":    "D",
                        },
                    )
                d = r.json()
                if d.get("rt_cd") != "0":
                    logger.debug(f"KIS API non-zero rt_cd={d.get('rt_cd')} for {market_code}")
                    return None
                o = d.get("output1") or {}
                if isinstance(o, list):
                    o = o[0] if o else {}
                price_str = o.get("bstp_nmix_prpr", "")
                if not price_str or price_str == "0":
                    return None
                result = {
                    "price":       round(float(price_str), 2),
                    "change":      round(float(o.get("bstp_nmix_prdy_vrss", 0) or 0), 2),
                    "change_rate": round(float(o.get("bstp_nmix_prdy_ctrt", 0) or 0), 2),
                    "open":        round(float(o.get("bstp_nmix_oprc", 0)    or 0), 2),
                    "high":        round(float(o.get("bstp_nmix_hgpr", 0)    or 0), 2),
                    "low":         round(float(o.get("bstp_nmix_lwpr", 0)    or 0), 2),
                    "volume":      int(o.get("acml_vol", 0) or 0),
                }
                try:
                    import json as _json
                    await redis.set(cache_key, _json.dumps(result), ex=30)
                except Exception as e:
                    logger.debug(f"Redis cache write failed for {cache_key}: {e}")
                return result
            except asyncio.TimeoutError:
                if attempt == 0:
                    logger.debug(f"KIS index quote timeout (attempt 1), retrying in 1s for {market_code}")
                    await asyncio.sleep(1)
                    continue
                logger.warning(f"KIS index quote timeout after 2 attempts for {market_code}")
                return None
    except Exception as e:
        logger.error(f"KIS index quote error for {market_code}: {e}")
        return None


@router.get("/index-live")
async def market_index_live(
    db: asyncpg.Pool = Depends(get_db),
    redis: redis_lib.Redis = Depends(get_redis),
):
    """KOSPI/KOSDAQ 실시간 지수 현재가 (KIS → Redis 30초 캐시, 실패 시 daily_bars 폴백)."""
    cache_key = "market:index_live"
    try:
        raw = await redis.get(cache_key)
        if raw:
            return orjson.loads(raw)
    except Exception:
        pass

    kospi  = await _kis_index_quote(redis, "0001")
    kosdaq = await _kis_index_quote(redis, "1001")

    if kospi and kosdaq:
        result = {
            "kospi":      {"code": "0001", "name": "KOSPI",  **kospi},
            "kosdaq":     {"code": "1001", "name": "KOSDAQ", **kosdaq},
            "source":     "realtime",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await redis.set(cache_key, orjson.dumps(result), ex=30)
        except Exception:
            pass
        return result

    # 실시간 실패 → daily_bars 폴백
    row = await db.fetchrow(f"""
        {_CHANGE_RATE_CTE}
        SELECT
            MAX(c.date)::TEXT AS data_date,
            ROUND(AVG(c.change_rate) FILTER (WHERE s.market='KOSPI' )::NUMERIC, 2) AS kospi_change,
            ROUND(AVG(c.change_rate) FILTER (WHERE s.market='KOSDAQ')::NUMERIC, 2) AS kosdaq_change
        FROM computed c
        JOIN stocks s ON s.code = c.code
        WHERE s.market IN ('KOSPI', 'KOSDAQ')
    """)
    d = dict(row) if row else {}
    return {
        "kospi":     {"name": "KOSPI",  "change_rate": d.get("kospi_change",  0)},
        "kosdaq":    {"name": "KOSDAQ", "change_rate": d.get("kosdaq_change", 0)},
        "source":    "daily",
        "data_date": d.get("data_date"),
    }


@router.get("/new-highs")
async def new_highs(
    hours: int = Query(default=24, le=168),
    db: asyncpg.Pool = Depends(get_db),
):
    """신고가 종목 (feature_events BREAKOUT 기반, UNKNOWN 제외)."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = await db.fetch("""
        SELECT DISTINCT ON (fe.code, fe.event_type)
            fe.code, s.name, s.market, s.sector,
            fe.event_type, fe.price, fe.change_rate, fe.signal_score,
            (fe.detected_at AT TIME ZONE 'Asia/Seoul')::TEXT AS detected_at
        FROM feature_events fe
        JOIN stocks s ON s.code = fe.code
        WHERE fe.event_type IN ('BREAKOUT_52W','BREAKOUT_26W','BREAKOUT_20D')
          AND fe.detected_at >= $1
          AND s.market IN ('KOSPI', 'KOSDAQ')
        ORDER BY fe.code, fe.event_type, fe.signal_score DESC
    """, since)

    results = [dict(r) for r in rows]
    return {"since": since.isoformat(), "stocks": results, "total": len(results)}


@router.get("/sector-heatmap")
async def sector_heatmap(
    db:    asyncpg.Pool = Depends(get_db),
    redis: redis_lib.Redis = Depends(get_redis),
):
    """섹터별 등락 히트맵 (오늘 daily_bars 기준, 5분 캐시)."""
    cache_key = "cache:sector_heatmap"
    try:
        cached = await redis.get(cache_key)
        if cached:
            return orjson.loads(cached)
    except Exception:
        pass

    rows = await db.fetch("""
        WITH
        -- 충분한 종목 수(최소 100건)를 가진 가장 최근 날짜 선택
        latest_dt AS (
            SELECT date AS d FROM (
                SELECT date, COUNT(*) AS cnt FROM daily_bars
                GROUP BY date ORDER BY date DESC
            ) sub WHERE cnt >= 100 LIMIT 1
        ),
        prev_dt   AS (SELECT MAX(date) AS d FROM daily_bars
                       WHERE date < (SELECT d FROM latest_dt)),
        computed AS (
            SELECT
                c.code,
                COALESCE(
                    CASE WHEN c.change_rate IS NOT NULL AND c.change_rate <> 0 THEN c.change_rate
                         WHEN p.close IS NOT NULL AND p.close > 0
                         THEN ROUND(((c.close - p.close)::NUMERIC / p.close * 100), 2)
                         ELSE 0
                    END, 0
                ) AS change_rate,
                c.volume,
                c.amount
            FROM daily_bars c
            CROSS JOIN latest_dt
            LEFT JOIN daily_bars p ON p.code = c.code
                                   AND p.date = (SELECT d FROM prev_dt)
            WHERE c.date = latest_dt.d AND c.close > 0
        )
        SELECT
            s.sector,
            COUNT(DISTINCT s.code)           AS stock_count,
            ROUND(AVG(c.change_rate)::NUMERIC, 2) AS avg_change_pct,
            SUM(c.volume)                    AS total_volume,
            SUM(c.amount)                    AS total_amount,
            json_agg(json_build_object(
                'code', s.code,
                'name', s.name,
                'change_pct', c.change_rate
            ) ORDER BY c.change_rate DESC) FILTER (WHERE c.change_rate IS NOT NULL) AS top_stocks_raw
        FROM stocks s
        JOIN computed c ON c.code = s.code
        WHERE s.market IN ('KOSPI', 'KOSDAQ')
          AND s.is_active = TRUE
          AND s.sector IS NOT NULL
          AND s.sector != ''
        GROUP BY s.sector
        ORDER BY avg_change_pct DESC
    """)

    result = []
    for row in rows:
        raw = row["top_stocks_raw"]
        if isinstance(raw, str):
            import json as _json
            top_stocks = _json.loads(raw)[:5]
        elif isinstance(raw, list):
            top_stocks = raw[:5]
        else:
            top_stocks = []

        result.append({
            "sector":       row["sector"],
            "stock_count":  row["stock_count"],
            "avg_change_pct": float(row["avg_change_pct"] or 0),
            "total_volume": int(row["total_volume"] or 0),
            "total_amount": int(row["total_amount"] or 0),
            "top_stocks":   top_stocks,
        })

    try:
        await redis.setex(cache_key, 300, orjson.dumps(result))
    except Exception:
        pass

    return result


@router.get("/overview")
async def market_overview(
    db:    asyncpg.Pool        = Depends(get_db),
    redis: redis_lib.Redis     = Depends(get_redis),
):
    """Dashboard용 시장 전체 개요 — summary + index_live + movers + regime을 1회 요청으로 반환 (Redis 30s 캐시)."""
    cache_key = "cache:market_overview"
    try:
        cached = await redis.get(cache_key)
        if cached:
            return orjson.loads(cached)
    except Exception:
        pass

    async def _regime():
        try:
            raw = await redis.get("market:regime")
            if raw:
                return orjson.loads(raw)
        except Exception:
            pass
        try:
            rows = await db.fetch(
                "SELECT close FROM daily_bars WHERE code='0001' ORDER BY date DESC LIMIT 25"
            )
            if not rows or len(rows) < 5:
                return {"phase": "unknown"}
            closes = [float(r["close"]) for r in rows]
            ma20   = sum(closes[:20]) / min(20, len(closes))
            pct    = (closes[0] - ma20) / ma20 * 100
            import os as _os
            bear_thr = float(_os.environ.get("REGIME_BEAR_THRESHOLD", "-3.0"))
            bull_thr = float(_os.environ.get("REGIME_BULL_THRESHOLD", "-0.5"))
            phase = "bear" if pct < bear_thr else ("neutral" if pct < bull_thr else "bull")
            result = {"phase": phase, "kospi_price": round(closes[0], 2), "ma20": round(ma20, 2), "pct_from_ma20": round(pct, 2)}
            try:
                await redis.set("market:regime", orjson.dumps(result), ex=1800)
            except Exception:
                pass
            return result
        except Exception:
            return {"phase": "unknown"}

    summary_res, index_res, movers_res, regime_res, new_highs_res = await asyncio.gather(
        market_summary(db),
        market_index_live(db, redis),
        market_movers(db, redis),
        _regime(),
        new_highs(24, db),
        return_exceptions=True,
    )

    result = {
        "summary":   summary_res  if not isinstance(summary_res,  Exception) else None,
        "index":     index_res    if not isinstance(index_res,    Exception) else None,
        "movers":    movers_res   if not isinstance(movers_res,   Exception) else None,
        "regime":    regime_res   if not isinstance(regime_res,   Exception) else None,
        "new_highs": new_highs_res if not isinstance(new_highs_res, Exception) else None,
    }
    try:
        await redis.set(cache_key, orjson.dumps(result), ex=30)
    except Exception:
        pass
    return result
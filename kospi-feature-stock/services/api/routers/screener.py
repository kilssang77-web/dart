"""screener.py — 종목 스크리너 API.

다중 조건(RSI, 52주 신고가, 거래량, 수급, ML, PER, ROE) AND 조합.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
import asyncpg
import redis.asyncio as redis_lib
import orjson
import hashlib
import logging

from deps import get_db, get_redis

router = APIRouter()
logger = logging.getLogger("screener")


def _calc_rsi(closes: list[float], period: int = 14) -> float | None:
    """Wilder's RSI 계산. 데이터 부족 시 None 반환."""
    if len(closes) < period + 1:
        return None
    avg_gain = 0.0
    avg_loss = 0.0
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            avg_gain += diff
        else:
            avg_loss += abs(diff)
    avg_gain /= period
    avg_loss /= period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    rsi = 100 - 100 / (1 + rs)
    for i in range(period + 1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gain = diff if diff > 0 else 0.0
        loss = abs(diff) if diff < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        rs = avg_gain / avg_loss if avg_loss != 0 else 100.0
        rsi = 100 - 100 / (1 + rs)
    return round(rsi, 1)


class ScreenerRequest(BaseModel):
    rsi_min:            Optional[float] = Field(None, ge=0, le=100, description="RSI 최솟값")
    rsi_max:            Optional[float] = Field(None, ge=0, le=100, description="RSI 최댓값")
    near_52w_high_pct:  Optional[float] = Field(None, ge=0, le=100, description="52주 신고가 N% 이내")
    volume_ratio_min:   Optional[float] = Field(None, ge=0, description="평균 거래량 대비 N배 이상")
    foreign_net_days:   Optional[int]   = Field(None, ge=1, le=20, description="외국인 N일 연속 순매수")
    ml_prob_min:        Optional[float] = Field(None, ge=0, le=1, description="ML 확률 최솟값")
    event_types:        Optional[List[str]] = Field(None, description="이벤트 타입 목록")
    market:             Optional[str]   = Field(None, description="ALL/KOSPI/KOSDAQ")
    per_max:            Optional[float] = Field(None, ge=0, description="PER 상한")
    roe_min:            Optional[float] = Field(None, description="ROE 하한")
    limit:              int             = Field(50, ge=1, le=500)


@router.post("/run")
async def run_screener(
    req:   ScreenerRequest,
    db:    asyncpg.Pool = Depends(get_db),
    redis: redis_lib.Redis = Depends(get_redis),
):
    """종목 스크리너 실행.

    조건 없으면 해당 조건 제외 (AND 조합). 결과 2분 캐시.
    """
    # 캐시 키 생성
    req_bytes = req.model_dump_json().encode()
    cache_key = f"screener:run:{hashlib.md5(req_bytes).hexdigest()}"
    try:
        cached = await redis.get(cache_key)
        if cached:
            return orjson.loads(cached)
    except Exception:
        pass

    # 1. 기본 종목 목록 + 최신 bar
    # market 값을 허용 목록으로 검증 (SQL Injection 방지)
    allowed_markets = {"KOSPI", "KOSDAQ", "ALL"}
    market_val = (req.market or "ALL").upper()
    if market_val not in allowed_markets:
        market_val = "ALL"

    rows = await db.fetch("""
        WITH
        latest_dt AS (
            SELECT date AS d FROM (
                SELECT date, COUNT(*) AS cnt FROM daily_bars
                GROUP BY date ORDER BY date DESC
            ) sub WHERE cnt >= 100 LIMIT 1
        ),
        avg20_dt  AS (
            SELECT code, AVG(volume) AS avg_vol20
            FROM daily_bars
            WHERE date >= (SELECT d - INTERVAL '20 days' FROM latest_dt)
            GROUP BY code
        ),
        w52 AS (
            SELECT code, MAX(high) AS high52
            FROM daily_bars
            WHERE date >= (SELECT d - INTERVAL '252 days' FROM latest_dt)
            GROUP BY code
        )
        SELECT
            s.code, s.name, s.market, s.sector,
            db.close AS current_price,
            COALESCE(db.change_rate, 0) AS change_rate,
            db.volume,
            avg20.avg_vol20,
            w52.high52
        FROM stocks s
        JOIN daily_bars db ON db.code = s.code
        CROSS JOIN latest_dt
        JOIN avg20_dt avg20 ON avg20.code = s.code
        JOIN w52 ON w52.code = s.code
        WHERE db.date = latest_dt.d
          AND db.close > 0
          AND s.is_active = TRUE
          AND s.market IN ('KOSPI', 'KOSDAQ')
          AND ($1 = 'ALL' OR s.market = $1)
        ORDER BY s.code
        LIMIT 3000
    """, market_val)

    if not rows:
        return []

    # 2. RSI가 필요하면 30일 종가 일괄 조회
    need_rsi = req.rsi_min is not None or req.rsi_max is not None
    rsi_map: dict[str, float | None] = {}
    if need_rsi:
        codes = [r["code"] for r in rows]
        rsi_rows = await db.fetch("""
            WITH latest_dt AS (
                SELECT date AS d FROM daily_bars ORDER BY date DESC LIMIT 1
            )
            SELECT code, close::FLOAT, date
            FROM daily_bars, latest_dt
            WHERE date >= latest_dt.d - INTERVAL '40 days'
              AND code = ANY($1::text[])
            ORDER BY code, date ASC
        """, codes)
        code_closes: dict[str, list[float]] = {}
        for rr in rsi_rows:
            code_closes.setdefault(rr["code"], []).append(float(rr["close"]))
        for code, closes in code_closes.items():
            rsi_map[code] = _calc_rsi(closes)

    # 3. 수급 (foreign_net 연속 순매수)
    need_supply = req.foreign_net_days is not None
    supply_map: dict[str, int] = {}
    if need_supply:
        supply_rows = await db.fetch("""
            WITH latest_dt AS (SELECT MAX(date) AS d FROM supply_demand),
            recent AS (
                SELECT code, date, foreign_net,
                       ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) AS rn
                FROM supply_demand
                WHERE date >= (SELECT d - INTERVAL '25 days' FROM latest_dt)
                  AND foreign_net > 0
            )
            SELECT code, COUNT(*) AS consecutive
            FROM recent
            WHERE rn <= $1
            GROUP BY code
        """, req.foreign_net_days)
        supply_map = {r["code"]: r["consecutive"] for r in supply_rows}

    # 4. ML 확률
    need_ml = req.ml_prob_min is not None
    ml_map: dict[str, float] = {}
    if need_ml:
        ml_rows = await db.fetch("""
            SELECT code,
                   MAX((signal_data->>'ml_prob')::FLOAT) AS ml_prob
            FROM feature_events
            WHERE detected_at >= NOW() - INTERVAL '30 days'
              AND signal_data->>'ml_prob' IS NOT NULL
            GROUP BY code
        """)
        ml_map = {r["code"]: float(r["ml_prob"]) for r in ml_rows}

    # 5. 이벤트 타입
    need_event = bool(req.event_types)
    event_map: dict[str, list[str]] = {}
    if need_event:
        evt_rows = await db.fetch("""
            SELECT DISTINCT code, event_type
            FROM feature_events
            WHERE detected_at >= NOW() - INTERVAL '30 days'
              AND event_type = ANY($1)
        """, req.event_types)
        for r in evt_rows:
            event_map.setdefault(r["code"], []).append(r["event_type"])

    # 6. PER/ROE
    need_fin = req.per_max is not None or req.roe_min is not None
    fin_map: dict[str, dict] = {}
    if need_fin:
        fin_rows = await db.fetch("""
            SELECT DISTINCT ON (code)
                code, per, roe
            FROM financials
            WHERE per IS NOT NULL OR roe IS NOT NULL
            ORDER BY code, year DESC, quarter DESC
        """)
        fin_map = {r["code"]: {"per": r["per"], "roe": r["roe"]} for r in fin_rows}

    # 7. 필터링
    results = []
    for row in rows:
        code = row["code"]
        close = float(row["current_price"])
        high52 = float(row["high52"] or close)
        avg_vol = float(row["avg_vol20"] or 1)
        volume = int(row["volume"] or 0)

        matched: list[str] = []

        # RSI 조건
        rsi_val = rsi_map.get(code) if need_rsi else None
        if req.rsi_min is not None:
            if rsi_val is None or rsi_val < req.rsi_min:
                continue
            matched.append(f"RSI≥{req.rsi_min}")
        if req.rsi_max is not None:
            if rsi_val is None or rsi_val > req.rsi_max:
                continue
            matched.append(f"RSI≤{req.rsi_max}")

        # 52주 신고가 이내
        if req.near_52w_high_pct is not None:
            if high52 <= 0 or close <= 0:
                continue
            dist_pct = (high52 - close) / high52 * 100
            if dist_pct > req.near_52w_high_pct:
                continue
            matched.append(f"52W신고가{req.near_52w_high_pct}%이내")

        # 거래량 비율
        if req.volume_ratio_min is not None:
            vol_ratio = volume / avg_vol if avg_vol > 0 else 0
            if vol_ratio < req.volume_ratio_min:
                continue
            matched.append(f"거래량×{req.volume_ratio_min}")

        # 외국인 연속 순매수
        if req.foreign_net_days is not None:
            if supply_map.get(code, 0) < req.foreign_net_days:
                continue
            matched.append(f"외인{req.foreign_net_days}일연속")

        # ML 확률
        ml_val = ml_map.get(code)
        if req.ml_prob_min is not None:
            if ml_val is None or ml_val < req.ml_prob_min:
                continue
            matched.append(f"ML≥{int(req.ml_prob_min*100)}%")

        # 이벤트 타입
        if req.event_types:
            if code not in event_map:
                continue
            matched.append(f"이벤트:{','.join(event_map[code][:2])}")

        # PER
        fin = fin_map.get(code, {}) if need_fin else {}
        if req.per_max is not None:
            per = fin.get("per")
            if per is None or per > req.per_max:
                continue
            matched.append(f"PER≤{req.per_max}")

        # ROE
        if req.roe_min is not None:
            roe = fin.get("roe")
            if roe is None or roe < req.roe_min:
                continue
            matched.append(f"ROE≥{req.roe_min}%")

        vol_ratio = volume / avg_vol if avg_vol > 0 else 0
        results.append({
            "code":             code,
            "name":             row["name"],
            "sector":           row["sector"],
            "market":           row["market"],
            "current_price":    int(close),
            "change_rate":      float(row["change_rate"] or 0),
            "rsi":              rsi_val,
            "volume_ratio":     round(vol_ratio, 2),
            "foreign_net_5d":   supply_map.get(code, 0),
            "ml_prob":          ml_val,
            "per":              fin.get("per"),
            "roe":              fin.get("roe"),
            "match_conditions": matched,
        })

        if len(results) >= req.limit:
            break

    # 캐시 저장
    try:
        await redis.setex(cache_key, 120, orjson.dumps(results))
    except Exception:
        pass

    return results

"""DB 저장 헬퍼 — tick_data / minute_bars / daily_bars / supply_demand / feature_events"""
import json
import logging
import math as _math
from datetime import datetime, date as date_type, timezone
import asyncpg

logger = logging.getLogger(__name__)


def _safe_float(v):
    """Convert value to float, return None for NaN/inf/None."""
    if v is None:
        return None
    try:
        f = float(v)
        return None if (_math.isnan(f) or _math.isinf(f)) else f
    except (TypeError, ValueError):
        return None


async def _update_technical_indicators(pool: asyncpg.Pool, code: str) -> None:
    """
    pandas-ta로 RSI/MACD/BB/ATR 계산 후 daily_bars에 업데이트.
    KIS API 응답값 대신 직접 계산하므로 신뢰도가 높음.
    최소 30개 바 필요.
    """
    try:
        import pandas as pd
        import pandas_ta as ta
    except ImportError:
        logger.warning("pandas-ta not installed, skipping indicator calculation")
        return

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT date, open, high, low, close, volume
                FROM daily_bars WHERE code=$1
                ORDER BY date ASC
                """,
                code,
            )
        if len(rows) < 30:
            return

        df = pd.DataFrame([dict(r) for r in rows])
        df["close"]  = df["close"].astype(float)
        df["high"]   = df["high"].astype(float)
        df["low"]    = df["low"].astype(float)
        df["open"]   = df["open"].astype(float)
        df["volume"] = df["volume"].astype(float)

        # RSI(14)
        rsi = ta.rsi(df["close"], length=14)
        # MACD(12,26,9)
        macd_df = ta.macd(df["close"], fast=12, slow=26, signal=9)
        # Bollinger Bands(20,2)
        bb_df = ta.bbands(df["close"], length=20, std=2)
        # ATR(14)
        atr = ta.atr(df["high"], df["low"], df["close"], length=14)

        updates = []
        for i in range(len(df)):
            rsi_val   = _safe_float(rsi.iloc[i]                          if rsi is not None else None)
            macd_val  = _safe_float(macd_df["MACD_12_26_9"].iloc[i]      if macd_df is not None else None)
            macds_val = _safe_float(macd_df["MACDs_12_26_9"].iloc[i]     if macd_df is not None else None)
            bb_up     = _safe_float(bb_df["BBU_20_2.0"].iloc[i]          if bb_df is not None else None)
            bb_lo     = _safe_float(bb_df["BBL_20_2.0"].iloc[i]          if bb_df is not None else None)
            bb_mid    = _safe_float(bb_df["BBM_20_2.0"].iloc[i]          if bb_df is not None else None)
            atr_val   = _safe_float(atr.iloc[i]                          if atr is not None else None)

            # Only update rows where at least one indicator is available
            if any(v is not None for v in [rsi_val, macd_val, bb_up, atr_val]):
                updates.append((
                    rsi_val, macd_val, macds_val, bb_up, bb_lo, bb_mid, atr_val,
                    code, df["date"].iloc[i],
                ))

        if updates:
            async with pool.acquire() as conn:
                await conn.executemany(
                    """
                    UPDATE daily_bars SET
                        rsi14        = COALESCE($1, rsi14),
                        macd         = COALESCE($2, macd),
                        macd_signal  = COALESCE($3, macd_signal),
                        bb_upper     = COALESCE($4, bb_upper),
                        bb_lower     = COALESCE($5, bb_lower),
                        ma20         = COALESCE($6, ma20),
                        atr14        = COALESCE($7, atr14)
                    WHERE code=$8 AND date=$9
                    """,
                    updates,
                )
            logger.debug(f"[Indicators] Updated {len(updates)} rows for {code}")

    except Exception as e:
        logger.warning(f"[Indicators] Failed for {code}: {e}")


async def write_tick(pool: asyncpg.Pool, ticks: list[dict]) -> None:
    if not ticks:
        return
    try:
        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO tick_data (time, code, price, volume, amount, change_rate, is_buy)
                VALUES (NOW(), $1, $2, $3, $4, $5, $6)
                """,
                [
                    (
                        t.get("code", ""),
                        int(t.get("price", 0)),
                        int(t.get("volume", 0)),
                        int(t.get("amount", 0)),
                        float(t.get("change_rate", 0)),
                        t.get("is_buy"),
                    )
                    for t in ticks
                    if t.get("code") and int(t.get("price", 0)) > 0
                ],
            )
    except Exception as e:
        logger.debug(f"tick write error ({len(ticks)} rows): {e}")


async def write_minute_bars(pool: asyncpg.Pool, code: str, bars: list[dict]) -> None:
    if not bars:
        return
    rows = [
        (
            b["time"],          # "YYYYMMDDHH24MISS" 문자열
            code,
            1,
            int(b.get("open", 0)),
            int(b.get("high", 0)),
            int(b.get("low", 0)),
            int(b.get("close", 0)),
            int(b.get("volume", 0)),
            int(b.get("amount", 0)),
        )
        for b in bars
        if b.get("close") and b.get("time")
    ]
    if not rows:
        return
    try:
        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO minute_bars (time, code, interval_min, open, high, low, close, volume, amount)
                VALUES (
                    TO_TIMESTAMP($1, 'YYYYMMDDHH24MISS'),
                    $2, $3, $4, $5, $6, $7, $8, $9
                )
                ON CONFLICT (code, interval_min, time) DO UPDATE SET
                    high   = GREATEST(EXCLUDED.high, minute_bars.high),
                    low    = LEAST(EXCLUDED.low, minute_bars.low),
                    close  = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    amount = EXCLUDED.amount
                """,
                rows,
            )
    except Exception as e:
        logger.debug(f"minute_bar write error {code}: {e}")


async def write_daily_bars(pool: asyncpg.Pool, bars: list[dict]) -> int:
    if not bars:
        return 0
    def _to_date(d):
        if isinstance(d, date_type):
            return d
        s = str(d).replace("-", "")
        return datetime.strptime(s, "%Y%m%d").date()

    rows = [
        (
            _to_date(b.get("date")),
            b.get("code"),
            int(b.get("open", 0)),
            int(b.get("high", 0)),
            int(b.get("low", 0)),
            int(b.get("close", 0)),
            int(b.get("volume", 0)),
            int(b.get("amount", 0)),
            float(b.get("change_rate", 0)),
        )
        for b in bars
        if b.get("close") and b.get("date") and b.get("code")
    ]
    if not rows:
        return 0

    codes = list({r[1] for r in rows})
    dates = list({r[0] for r in rows})

    try:
        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO daily_bars
                    (date, code, open, high, low, close, volume, amount, change_rate)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (date, code) DO UPDATE SET
                    open=EXCLUDED.open, high=EXCLUDED.high,
                    low=EXCLUDED.low,  close=EXCLUDED.close,
                    volume=EXCLUDED.volume, amount=EXCLUDED.amount,
                    change_rate=EXCLUDED.change_rate
                """,
                rows,
            )
            # change_rate 재계산: KIS API가 0을 반환하는 경우 전일 종가 기준으로 보정
            await conn.execute(
                """
                WITH prev AS (
                    SELECT date, code,
                           LAG(close) OVER (PARTITION BY code ORDER BY date) AS prev_close
                    FROM daily_bars WHERE code = ANY($1)
                )
                UPDATE daily_bars d
                SET change_rate = ROUND(
                    (d.close::NUMERIC - p.prev_close::NUMERIC)
                    / p.prev_close::NUMERIC * 100, 2
                )
                FROM prev p
                WHERE d.date = p.date AND d.code = p.code
                  AND p.prev_close IS NOT NULL AND p.prev_close > 0
                  AND d.date = ANY($2)
                """,
                codes, dates,
            )
            # 이동평균선 계산 (MA5/20/60/120)
            await conn.execute(
                """
                WITH ma AS (
                    SELECT date, code,
                        AVG(close::NUMERIC) OVER (
                            PARTITION BY code ORDER BY date
                            ROWS BETWEEN 4 PRECEDING AND CURRENT ROW)   AS ma5,
                        AVG(close::NUMERIC) OVER (
                            PARTITION BY code ORDER BY date
                            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)  AS ma20,
                        AVG(close::NUMERIC) OVER (
                            PARTITION BY code ORDER BY date
                            ROWS BETWEEN 59 PRECEDING AND CURRENT ROW)  AS ma60,
                        AVG(close::NUMERIC) OVER (
                            PARTITION BY code ORDER BY date
                            ROWS BETWEEN 119 PRECEDING AND CURRENT ROW) AS ma120
                    FROM daily_bars WHERE code = ANY($1)
                )
                UPDATE daily_bars d
                SET ma5   = ROUND(m.ma5,   2),
                    ma20  = ROUND(m.ma20,  2),
                    ma60  = ROUND(m.ma60,  2),
                    ma120 = ROUND(m.ma120, 2)
                FROM ma m
                WHERE d.date = m.date AND d.code = m.code
                  AND d.date = ANY($2)
                """,
                codes, dates,
            )

        # 기술지표 사후 계산 (KIS API 값 보완)
        codes_in_batch = list({r[1] for r in rows})
        for c in codes_in_batch:
            await _update_technical_indicators(pool, c)

        return len(rows)
    except Exception as e:
        logger.error(f"daily_bar write error: {e}")
        return 0


async def write_feature_events(pool: asyncpg.Pool, events: list[dict]) -> int:
    """배치 탐지 이벤트를 feature_events에 저장. 중복(ON CONFLICT DO NOTHING) 허용."""
    if not events:
        return 0
    now = datetime.now(timezone.utc)
    rows = [
        (
            now,
            e.get("code", ""),
            e.get("event_type", ""),
            e.get("price"),
            e.get("change_rate"),
            e.get("volume"),
            e.get("volume_ratio"),
            e.get("amount"),
            json.dumps(e.get("signal_data") or {}),
            e.get("signal_score"),
            e.get("risk_score", 0.3),
        )
        for e in events
        if e.get("code") and e.get("event_type")
    ]
    if not rows:
        return 0
    try:
        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO feature_events
                    (detected_at, code, event_type, price, change_rate,
                     volume, volume_ratio, amount, signal_data,
                     signal_score, risk_score)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,$11)
                ON CONFLICT DO NOTHING
                """,
                rows,
            )
        return len(rows)
    except Exception as e:
        logger.error(f"feature_events write error: {e}")
        return 0


async def write_supply_demand(pool: asyncpg.Pool, sd: dict) -> None:
    """수급 데이터를 daily_bars 업데이트 + supply_demand 테이블 UPSERT"""
    from datetime import date as _date, datetime as _dt
    if not sd or not sd.get("code") or not sd.get("date"):
        return
    code           = sd["code"]
    raw_date       = sd["date"]
    if isinstance(raw_date, str):
        try:
            date_val = _dt.strptime(raw_date, "%Y%m%d").date()
        except ValueError:
            date_val = _date.fromisoformat(raw_date[:10])
    else:
        date_val = raw_date
    foreign_net    = int(sd.get("foreign_net", 0))
    inst_net       = int(sd.get("inst_net", 0))
    indiv_net      = int(sd.get("indiv_net", 0))
    prog_net       = int(sd.get("prog_arbitrage_net", 0))
    pension_net    = int(sd.get("pension_net", 0))
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE daily_bars
                SET foreign_net_buy = $3,
                    inst_net_buy    = $4,
                    indiv_net_buy   = $5,
                    prog_net_buy    = $6
                WHERE code = $1 AND date = $2
                """,
                code, date_val, foreign_net, inst_net, indiv_net, prog_net,
            )
            await conn.execute(
                """
                INSERT INTO supply_demand
                    (date, code, foreign_net, inst_net, indiv_net,
                     prog_arbitrage_net, pension_net)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (date, code) DO UPDATE SET
                    foreign_net        = EXCLUDED.foreign_net,
                    inst_net           = EXCLUDED.inst_net,
                    indiv_net          = EXCLUDED.indiv_net,
                    prog_arbitrage_net = EXCLUDED.prog_arbitrage_net,
                    pension_net        = EXCLUDED.pension_net
                """,
                date_val, code, foreign_net, inst_net, indiv_net, prog_net, pension_net,
            )
    except Exception as e:
        logger.warning(f"supply_demand write error {code}/{date_val}: {e}")

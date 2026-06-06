"""DB 저장 헬퍼 — tick_data / minute_bars / daily_bars / supply_demand / feature_events"""
import json
import logging
from datetime import datetime, date as date_type, timezone
import asyncpg

logger = logging.getLogger(__name__)


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
    try:
        async with pool.acquire() as conn:
            result = await conn.executemany(
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
    if not sd or not sd.get("code") or not sd.get("date"):
        return
    code           = sd["code"]
    date_val       = sd["date"]
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
                WHERE code = $1 AND date = $2::DATE
                """,
                code, date_val, foreign_net, inst_net, indiv_net, prog_net,
            )
            await conn.execute(
                """
                INSERT INTO supply_demand
                    (date, code, foreign_net, inst_net, indiv_net,
                     prog_arbitrage_net, pension_net)
                VALUES ($1::DATE, $2, $3, $4, $5, $6, $7)
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
        logger.debug(f"supply_demand write error {code}: {e}")

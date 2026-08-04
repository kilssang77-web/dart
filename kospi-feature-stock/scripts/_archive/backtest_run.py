"""
백테스트 실행 및 리포트 생성.

모드:
  events  : feature_events 테이블 기반 (기본, --mode events)
  replay  : daily_bars에서 규칙 재적용 기반 백테스트 (--mode replay)

사용:
  python scripts/backtest_run.py --mode events --start 2023-01-01 --end 2024-12-31
  python scripts/backtest_run.py --mode replay --start 2025-09-01 --end 2026-04-30
"""
import argparse
import asyncio
import asyncpg
import os
import sys
import json
import logging
from datetime import date as date_type, timedelta
import pandas as pd
from pathlib import Path

sys.path.insert(0, "/app")
try:
    from backtest.engine import BacktestEngine      # running inside ml container
except ImportError:
    from ml.backtest.engine import BacktestEngine  # running from project root

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backtest")


# ─── Signal loaders ────────────────────────────────────────────────────────────

async def load_signals_from_events(pool, start, end, event_type, min_score):
    start_d = date_type.fromisoformat(start)
    end_d   = date_type.fromisoformat(end)
    rows = await pool.fetch(
        """
        SELECT fe.code, DATE(fe.detected_at)::TEXT AS date, db.close
        FROM feature_events fe
        JOIN daily_bars db ON db.code=fe.code AND db.date=DATE(fe.detected_at)
        WHERE fe.event_type=$1
          AND fe.signal_score>=$2
          AND DATE(fe.detected_at) BETWEEN $3 AND $4
        ORDER BY fe.detected_at
        """,
        event_type, min_score, start_d, end_d,
    )
    return pd.DataFrame([dict(r) for r in rows])


async def load_signals_replay(pool, start, end, rule: str, vol_ratio: float, min_amount: int):
    """daily_bars에서 규칙을 직접 적용해 신호를 생성한다 (feature_events 불필요)."""
    start_d = date_type.fromisoformat(start)
    end_d   = date_type.fromisoformat(end)
    if rule == "VOLUME_SURGE":
        rows = await pool.fetch(
            """
            WITH ma AS (
                SELECT code, date,
                       close,
                       volume,
                       amount,
                       AVG(volume) OVER (
                           PARTITION BY code
                           ORDER BY date
                           ROWS BETWEEN 21 PRECEDING AND 2 PRECEDING
                       ) AS avg_vol_20d
                FROM daily_bars
                WHERE code NOT IN ('0001','1001')
                  AND date BETWEEN ($1::date - INTERVAL '25 days')::date AND $2
            )
            SELECT code, date::TEXT AS date, close
            FROM ma
            WHERE date BETWEEN $1 AND $2
              AND avg_vol_20d > 0
              AND volume >= avg_vol_20d * $3
              AND amount >= $4
            ORDER BY date, code
            """,
            start_d, end_d, vol_ratio, min_amount,
        )
    elif rule == "BREAKOUT_52W":
        rows = await pool.fetch(
            """
            WITH hi AS (
                SELECT code, date, close,
                       MAX(high) OVER (
                           PARTITION BY code
                           ORDER BY date
                           ROWS BETWEEN 260 PRECEDING AND 2 PRECEDING
                       ) AS high_52w
                FROM daily_bars
                WHERE code NOT IN ('0001','1001')
                  AND date BETWEEN ($1::date - INTERVAL '260 days')::date AND $2
            )
            SELECT code, date::TEXT AS date, close
            FROM hi
            WHERE date BETWEEN $1 AND $2
              AND high_52w > 0
              AND close > high_52w
            ORDER BY date, code
            """,
            start_d, end_d,
        )
    else:
        return pd.DataFrame()
    return pd.DataFrame([dict(r) for r in rows])


async def load_bars(pool, codes, start, end):
    start_d = date_type.fromisoformat(str(start))
    end_ext = date_type.fromisoformat(str(end)) + timedelta(days=22)
    rows = await pool.fetch(
        """
        SELECT code, date::TEXT, open, high, low, close, volume
        FROM daily_bars
        WHERE code=ANY($1) AND date BETWEEN $2 AND $3
        ORDER BY code, date
        """,
        codes, start_d, end_ext,
    )
    return pd.DataFrame([dict(r) for r in rows])


# ─── Main ──────────────────────────────────────────────────────────────────────

async def run_events_mode(pool, args):
    event_types = [
        "VOLUME_SURGE", "BREAKOUT_52W", "LONG_WHITE_CANDLE",
        "SUPPLY_ANOMALY", "POST_DISCLOSURE_SURGE",
    ]
    results = {}
    for etype in event_types:
        signals = await load_signals_from_events(pool, args.start, args.end, etype, 0.6)
        if signals.empty:
            logger.info(f"{etype}: no signals")
            continue
        codes = signals["code"].unique().tolist()
        bars  = await load_bars(pool, codes, args.start, args.end)
        engine = BacktestEngine(
            stop_loss_pct=-args.stop_loss,
            target_pct=args.target,
            max_hold_days=args.hold,
        )
        result = engine.run(signals, bars)
        results[etype] = result.summary()
        logger.info(f"{etype}: {result.summary()}")
    return results


async def run_replay_mode(pool, args):
    vol_ratio  = float(os.environ.get("VOL_SURGE_RATIO", "5.0"))
    min_amount = int(os.environ.get("VOL_SURGE_MIN_AMOUNT", "1000000000"))

    rules = [("VOLUME_SURGE", vol_ratio), ("BREAKOUT_52W", None)]
    results = {}
    for rule, ratio in rules:
        signals = await load_signals_replay(
            pool, args.start, args.end, rule,
            vol_ratio=ratio or 5.0,
            min_amount=min_amount,
        )
        if signals.empty:
            logger.info(f"[replay] {rule}: no signals")
            continue
        logger.info(f"[replay] {rule}: {len(signals)} signals")
        codes = signals["code"].unique().tolist()
        bars  = await load_bars(pool, codes, args.start, args.end)
        engine = BacktestEngine(
            stop_loss_pct=-args.stop_loss,
            target_pct=args.target,
            max_hold_days=args.hold,
        )
        result = engine.run(signals, bars)
        results[rule] = result.summary()
        logger.info(f"[replay] {rule}: {result.summary()}")
    return results


async def main(args):
    pool = await asyncpg.create_pool(
        dsn=os.environ["POSTGRES_DSN"].replace("+asyncpg", ""),
    )

    if args.mode == "replay":
        results = await run_replay_mode(pool, args)
    else:
        results = await run_events_mode(pool, args)

    out = Path("output")
    out.mkdir(exist_ok=True)
    report = {
        "mode":   args.mode,
        "period": {"start": args.start, "end": args.end},
        "params": {
            "stop_loss": args.stop_loss,
            "target":    args.target,
            "hold_days": args.hold,
        },
        "results": results,
    }
    with open("output/backtest_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    logger.info("Report saved to output/backtest_report.json")
    await pool.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode",      choices=["events", "replay"], default="events")
    parser.add_argument("--start",     default="2025-09-18")
    parser.add_argument("--end",       default="2026-04-30")
    parser.add_argument("--stop-loss", type=float, default=0.05)
    parser.add_argument("--target",    type=float, default=0.10)
    parser.add_argument("--hold",      type=int,   default=10)
    asyncio.run(main(parser.parse_args()))

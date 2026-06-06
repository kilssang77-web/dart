"""
백테스트 실행 및 리포트 생성.
사용: python scripts/backtest_run.py --start 2023-01-01 --end 2024-12-31
"""
import argparse
import asyncio
import asyncpg
import os
import sys
import json
import logging
import pandas as pd
from pathlib import Path

sys.path.insert(0, "/app")
from ml.backtest.engine import BacktestEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backtest")


async def load_signals(pool, start, end, event_type, min_score):
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
        event_type, min_score, start, end,
    )
    return pd.DataFrame([dict(r) for r in rows])


async def load_bars(pool, codes, start, end):
    rows = await pool.fetch(
        """
        SELECT code, date::TEXT, open, high, low, close, volume
        FROM daily_bars
        WHERE code=ANY($1) AND date BETWEEN $2 AND $3
        ORDER BY code, date
        """,
        codes, start, end,
    )
    return pd.DataFrame([dict(r) for r in rows])


async def main(args):
    pool = await asyncpg.create_pool(
        dsn=os.environ["POSTGRES_DSN"].replace("+asyncpg", ""),
    )

    event_types = [
        "VOLUME_SURGE", "BREAKOUT_52W", "LONG_WHITE_CANDLE",
        "SUPPLY_ANOMALY", "POST_DISCLOSURE_SURGE",
    ]
    results = {}

    for etype in event_types:
        signals = await load_signals(pool, args.start, args.end, etype, 0.6)
        if signals.empty:
            logger.info(f"{etype}: no signals")
            continue

        codes = signals["code"].unique().tolist()
        bars  = await load_bars(pool, codes, args.start, args.end)

        engine = BacktestEngine(
            stop_loss_pct=float(f"-{args.stop_loss}"),
            target_pct=args.target,
            max_hold_days=args.hold,
        )
        result = engine.run(signals, bars)
        results[etype] = result.summary()
        logger.info(f"{etype}: {result.summary()}")

    out = Path("output")
    out.mkdir(exist_ok=True)
    report = {
        "period": {"start": args.start, "end": args.end},
        "params": {"stop_loss": args.stop_loss, "target": args.target},
        "results": results,
    }
    with open("output/backtest_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    logger.info("Report saved to output/backtest_report.json")
    await pool.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start",     default="2023-01-01")
    parser.add_argument("--end",       default="2024-12-31")
    parser.add_argument("--stop-loss", type=float, default=0.05)
    parser.add_argument("--target",    type=float, default=0.10)
    parser.add_argument("--hold",      type=int,   default=10)
    asyncio.run(main(parser.parse_args()))

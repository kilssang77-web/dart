from fastapi import APIRouter, Depends, Body
from datetime import date
import asyncpg
import pandas as pd
from deps import get_db
from backtest.engine import BacktestEngine

router = APIRouter()


@router.post("/run")
async def run_backtest(
    start: str = Body(...),
    end: str = Body(...),
    event_type: str = Body(default="VOLUME_SURGE"),
    min_score: float = Body(default=0.6),
    stop_loss_pct: float = Body(default=0.05),
    target_pct: float = Body(default=0.10),
    db: asyncpg.Pool = Depends(get_db),
):

    # 시그널 로드
    start_d = date.fromisoformat(start)
    end_d   = date.fromisoformat(end)

    sig_rows = await db.fetch(
        """
        SELECT fe.code, fe.detected_at::TEXT AS date, db.close
        FROM feature_events fe
        JOIN daily_bars db ON db.code = fe.code
            AND db.date = DATE(fe.detected_at)
        WHERE fe.event_type = $1
          AND fe.signal_score >= $2
          AND DATE(fe.detected_at) BETWEEN $3 AND $4
        ORDER BY fe.detected_at
        """,
        event_type, min_score, start_d, end_d,
    )
    if not sig_rows:
        return {"error": "No signals found for the given period"}

    signals = pd.DataFrame([dict(r) for r in sig_rows])

    # 일봉 로드
    codes = signals["code"].unique().tolist()
    bar_rows = await db.fetch(
        """
        SELECT code, date::TEXT, open, high, low, close, volume
        FROM daily_bars
        WHERE code = ANY($1) AND date BETWEEN $2 AND $3
        ORDER BY code, date
        """,
        codes, start_d, end_d,
    )
    bars = pd.DataFrame([dict(r) for r in bar_rows])

    engine = BacktestEngine(
        stop_loss_pct=-stop_loss_pct,
        target_pct=target_pct,
    )
    result = engine.run(signals, bars)
    return {
        "params": {
            "event_type": event_type,
            "start": start,
            "end": end,
            "min_score": min_score,
        },
        "result": result.summary(),
        "sample_trades": [
            {
                "code": t.code,
                "entry": t.entry_date,
                "exit": t.exit_date,
                "pnl": round(t.pnl_pct, 2),
                "status": t.status,
            }
            for t in result.trades[:20]
        ],
    }

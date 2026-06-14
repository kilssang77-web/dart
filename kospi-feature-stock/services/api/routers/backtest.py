from __future__ import annotations
import json
from datetime import date, timedelta
from fastapi import APIRouter, Depends, Body, Query, HTTPException
import asyncpg
import pandas as pd
from deps import get_db
from backtest.engine import BacktestEngine

router = APIRouter()


def _make_query(use_ml: bool, has_market: bool) -> tuple[str, str]:
    """(SQL template, market_param_placeholder) 반환."""
    if use_ml:
        market_cond = "AND s.market = $6" if has_market else ""
        q = f"""
        SELECT DISTINCT ON (fe.code, DATE(fe.detected_at))
            fe.code,
            DATE(fe.detected_at)::TEXT AS date,
            db.close,
            rec.success_prob AS signal_score
        FROM feature_events fe
        JOIN daily_bars db ON db.code = fe.code AND db.date = DATE(fe.detected_at)
        JOIN LATERAL (
            SELECT r.success_prob
            FROM recommendations r
            WHERE r.code = fe.code
              AND r.created_at BETWEEN fe.detected_at - INTERVAL '1 hour'
                                   AND fe.detected_at + INTERVAL '4 hours'
            ORDER BY r.created_at DESC
            LIMIT 1
        ) rec ON true
        JOIN stocks s ON s.code = fe.code
        WHERE fe.event_type = ANY($1::text[])
          AND fe.signal_score >= $2
          AND DATE(fe.detected_at) BETWEEN $3 AND $4
          AND rec.success_prob >= $5
          {market_cond}
        ORDER BY fe.code, DATE(fe.detected_at), fe.detected_at DESC
        """
    else:
        market_cond = "AND s.market = $5" if has_market else ""
        q = f"""
        SELECT DISTINCT ON (fe.code, DATE(fe.detected_at))
            fe.code,
            DATE(fe.detected_at)::TEXT AS date,
            db.close,
            fe.signal_score
        FROM feature_events fe
        JOIN daily_bars db ON db.code = fe.code AND db.date = DATE(fe.detected_at)
        JOIN stocks s ON s.code = fe.code
        WHERE fe.event_type = ANY($1::text[])
          AND fe.signal_score >= $2
          AND DATE(fe.detected_at) BETWEEN $3 AND $4
          {market_cond}
        ORDER BY fe.code, DATE(fe.detected_at), fe.detected_at DESC
        """
    return q


@router.post("/run")
async def run_backtest(
    start:         str         = Body(...),
    end:           str         = Body(...),
    event_type:    str | None  = Body(default=None),
    event_types:   list[str] | None = Body(default=None),
    market:        str | None  = Body(default=None),
    min_score:     float       = Body(default=0.5),
    ml_min_prob:   float       = Body(default=0.0),
    stop_loss_pct: float       = Body(default=0.05),
    target_pct:    float       = Body(default=0.10),
    slippage:      float       = Body(default=0.001),
    walkforward:   bool        = Body(default=False),
    db: asyncpg.Pool = Depends(get_db),
):
    start_d = date.fromisoformat(start)
    end_d   = date.fromisoformat(end)

    types   = event_types or ([event_type] if event_type else ["BREAKOUT_52W"])
    use_ml  = ml_min_prob > 0
    mkt     = market if market and market != "ALL" else None

    q = _make_query(use_ml, bool(mkt))

    async def _fetch(s_d: date, e_d: date) -> list:
        if use_ml:
            params: list = [types, min_score, s_d, e_d, ml_min_prob]
        else:
            params = [types, min_score, s_d, e_d]
        if mkt:
            params.append(mkt)
        return await db.fetch(q, *params)

    engine = BacktestEngine(
        stop_loss_pct=-stop_loss_pct,
        target_pct=target_pct,
        slippage=max(0.0, min(slippage, 0.02)),
    )

    params_out = {
        "event_types":   types,
        "event_type":    types[0] if len(types) == 1 else None,
        "start":         start,
        "end":           end,
        "min_score":     min_score,
        "ml_min_prob":   ml_min_prob,
        "stop_loss_pct": stop_loss_pct,
        "target_pct":    target_pct,
        "slippage":      slippage,
        "market":        mkt,
        "walkforward":   walkforward,
        "cost_note":     "round-trip ~0.46% (commission+slippage+sell_tax)",
    }

    async def _run_window(s_d: date, e_d: date):
        sig_rows = await _fetch(s_d, e_d)
        if not sig_rows:
            return None, []
        sigs = pd.DataFrame([dict(r) for r in sig_rows])
        if "signal_score" not in sigs.columns:
            sigs["signal_score"] = 0.0
        codes = sigs["code"].unique().tolist()
        bar_rows = await db.fetch(
            "SELECT code, date::TEXT, open, high, low, close, volume "
            "FROM daily_bars WHERE code = ANY($1) AND date BETWEEN $2 AND $3 "
            "ORDER BY code, date",
            codes, s_d, e_d,
        )
        bars = pd.DataFrame([dict(r) for r in bar_rows])
        result = engine.run(sigs, bars)
        return result, [dict(r) for r in sig_rows]

    # ── Walkforward 모드 ─────────────────────────────────────
    if walkforward:
        total_days = (end_d - start_d).days
        window = max(30, total_days // 4)
        windows: list[tuple[date, date]] = []
        w_start = start_d
        while w_start < end_d:
            w_end = min(w_start + timedelta(days=window), end_d)
            windows.append((w_start, w_end))
            w_start = w_end

        wf_results = []
        all_trades = []
        combined_equity: list[dict] = []

        for ws, we in windows:
            r, sigs = await _run_window(ws, we)
            if r is None:
                wf_results.append({"period": f"{ws} ~ {we}", "signals": 0, "result": None})
            else:
                all_trades.extend(r.trades)
                combined_equity.extend(r.equity_curve)
                wf_results.append({
                    "period":       f"{ws} ~ {we}",
                    "signals":      len(sigs),
                    "result":       r.summary(),
                    "equity_curve": r.equity_curve,
                })

        combined = engine._stats(all_trades) if all_trades else None
        return {
            "params":       params_out,
            "walkforward":  wf_results,
            "result":       combined.summary() if combined else None,
            "trade_log":    [t.to_dict() for t in all_trades],
            "equity_curve": combined.equity_curve if combined else [],
        }

    # ── 단일 백테스트 ─────────────────────────────────────────
    sig_rows = await _fetch(start_d, end_d)
    if not sig_rows:
        return {"error": "No signals found for the given period"}

    signals = pd.DataFrame([dict(r) for r in sig_rows])
    if "signal_score" not in signals.columns:
        signals["signal_score"] = 0.0

    codes = signals["code"].unique().tolist()
    bar_rows = await db.fetch(
        "SELECT code, date::TEXT, open, high, low, close, volume "
        "FROM daily_bars WHERE code = ANY($1) AND date BETWEEN $2 AND $3 "
        "ORDER BY code, date",
        codes, start_d, end_d,
    )
    bars = pd.DataFrame([dict(r) for r in bar_rows])
    result = engine.run(signals, bars)

    return {
        "params":       params_out,
        "result":       result.summary(),
        "trade_log":    [t.to_dict() for t in result.trades],
        "equity_curve": result.equity_curve,
        "sample_trades": [
            {"code": t.code, "entry": t.entry_date, "exit": t.exit_date,
             "pnl": round(t.pnl_pct, 2), "status": t.status}
            for t in result.trades[:20]
        ],
    }


# ── 결과 저장/조회/삭제 ──────────────────────────────────────

@router.post("/results")
async def save_backtest_result(
    name:         str  = Body(...),
    params:       dict = Body(...),
    result:       dict = Body(...),
    equity_curve: list = Body(default=[]),
    db: asyncpg.Pool = Depends(get_db),
):
    row = await db.fetchrow(
        """INSERT INTO backtest_results (name, params, result, equity_curve)
           VALUES ($1, $2, $3, $4)
           RETURNING id, created_at""",
        name,
        json.dumps(params, ensure_ascii=False),
        json.dumps(result, ensure_ascii=False),
        json.dumps(equity_curve, ensure_ascii=False),
    )
    return {"id": row["id"], "name": name, "created_at": row["created_at"].isoformat()}


@router.get("/results")
async def list_backtest_results(
    limit: int = Query(default=20, le=100),
    db: asyncpg.Pool = Depends(get_db),
):
    rows = await db.fetch(
        "SELECT id, name, params, result, created_at "
        "FROM backtest_results ORDER BY created_at DESC LIMIT $1",
        limit,
    )
    return [
        {
            "id":         r["id"],
            "name":       r["name"],
            "params":     json.loads(r["params"] or "{}"),
            "result":     json.loads(r["result"] or "{}"),
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


@router.get("/results/{result_id}")
async def get_backtest_result(
    result_id: int,
    db: asyncpg.Pool = Depends(get_db),
):
    row = await db.fetchrow(
        "SELECT id, name, params, result, equity_curve, created_at "
        "FROM backtest_results WHERE id = $1",
        result_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="결과 없음")
    return {
        "id":           row["id"],
        "name":         row["name"],
        "params":       json.loads(row["params"] or "{}"),
        "result":       json.loads(row["result"] or "{}"),
        "equity_curve": json.loads(row["equity_curve"] or "[]"),
        "created_at":   row["created_at"].isoformat(),
    }


@router.delete("/results/{result_id}")
async def delete_backtest_result(
    result_id: int,
    db: asyncpg.Pool = Depends(get_db),
):
    await db.execute("DELETE FROM backtest_results WHERE id = $1", result_id)
    return {"deleted": result_id}

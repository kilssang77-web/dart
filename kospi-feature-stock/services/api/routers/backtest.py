from __future__ import annotations
import dataclasses
import json
from datetime import date, timedelta
from fastapi import APIRouter, Depends, Body, Query, HTTPException
import asyncpg
from deps import get_db
from backtest.engine import BacktestEngine

router = APIRouter()


def _make_query(use_ml: bool, has_market: bool) -> str:
    """SQL 템플릿 반환.
    - stocks JOIN은 market 필터 시에만 포함 (없으면 Cartesian product 방지)
    - daily_bars에 명시적 날짜 범위 추가 → TimescaleDB chunk 프루닝 활성화
    - detected_at 범위를 timestamp로 비교해 기존 btree 인덱스 활용
    """
    if use_ml:
        market_join = "JOIN stocks s ON s.code = fe.code AND s.market = $6" if has_market else ""
        q = f"""
        SELECT DISTINCT ON (fe.code, DATE(fe.detected_at))
            fe.code,
            DATE(fe.detected_at)::TEXT AS date,
            db.close,
            db.volume,
            db.close * db.volume AS amount,
            rec.success_prob AS signal_score
        FROM feature_events fe
        JOIN daily_bars db ON db.code = fe.code
          AND db.date = DATE(fe.detected_at)
          AND db.date BETWEEN $3 AND $4
        JOIN LATERAL (
            SELECT r.success_prob
            FROM recommendations r
            WHERE r.code = fe.code
              AND r.created_at BETWEEN fe.detected_at - INTERVAL '1 hour'
                                   AND fe.detected_at + INTERVAL '4 hours'
            ORDER BY r.created_at DESC
            LIMIT 1
        ) rec ON true
        {market_join}
        WHERE fe.event_type = ANY($1::text[])
          AND fe.signal_score >= $2
          AND fe.detected_at >= $3::date
          AND fe.detected_at <  $4::date + INTERVAL '1 day'
          AND rec.success_prob >= $5
        ORDER BY fe.code, DATE(fe.detected_at), fe.detected_at DESC
        """
    else:
        market_join = "JOIN stocks s ON s.code = fe.code AND s.market = $5" if has_market else ""
        q = f"""
        SELECT DISTINCT ON (fe.code, DATE(fe.detected_at))
            fe.code,
            DATE(fe.detected_at)::TEXT AS date,
            db.close,
            db.volume,
            db.close * db.volume AS amount,
            fe.signal_score
        FROM feature_events fe
        JOIN daily_bars db ON db.code = fe.code
          AND db.date = DATE(fe.detected_at)
          AND db.date BETWEEN $3 AND $4
        {market_join}
        WHERE fe.event_type = ANY($1::text[])
          AND fe.signal_score >= $2
          AND fe.detected_at >= $3::date
          AND fe.detected_at <  $4::date + INTERVAL '1 day'
        ORDER BY fe.code, DATE(fe.detected_at), fe.detected_at DESC
        """
    return q


@router.post("/run")
async def run_backtest(
    start:            str            = Body(...),
    end:              str            = Body(...),
    event_type:       str | None     = Body(default=None),
    event_types:      list[str] | None = Body(default=None),
    market:           str | None     = Body(default=None),
    min_score:        float          = Body(default=0.5),
    ml_min_prob:      float          = Body(default=0.0),
    stop_loss_pct:    float          = Body(default=0.05),
    target_pct:       float          = Body(default=0.10),
    max_hold_days:    int            = Body(default=10),
    initial_capital:  float          = Body(default=10_000_000),
    invest_per_trade: float          = Body(default=500_000),
    max_positions:    int            = Body(default=5),
    sizing_method:    str            = Body(default="fixed"),
    invest_pct:       float          = Body(default=10.0),
    walkforward:      bool           = Body(default=False),
    db: asyncpg.Pool = Depends(get_db),
):
    try:
        import pandas as pd  # noqa: PLC0415 — lazy: pandas 256MB VM에서 임포트 지연
    except ImportError:
        raise HTTPException(status_code=503, detail="백테스트 기능은 현재 환경에서 사용 불가 (pandas 미설치)")

    start_d = date.fromisoformat(start)
    end_d   = date.fromisoformat(end)

    # 일봉 데이터 최대 날짜로 end_d 자동 클램핑 (오늘 선택 시 신호 0건 방지)
    max_bar_row = await db.fetchrow("SELECT MAX(date)::text AS max_date FROM daily_bars")
    if max_bar_row and max_bar_row["max_date"]:
        max_bar_date = date.fromisoformat(max_bar_row["max_date"])
        if end_d > max_bar_date:
            end_d = max_bar_date

    types   = event_types if event_types else ([event_type] if event_type else ["BREAKOUT_52W"])
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
        return await db.fetch(q, *params, timeout=120)

    engine = BacktestEngine(
        stop_loss_pct=-abs(stop_loss_pct),
        target_pct=target_pct,
        max_hold_days=max_hold_days,
        initial_capital=initial_capital,
        invest_per_trade=invest_per_trade,
        max_positions=max_positions,
        sizing_method=sizing_method,
        invest_pct=invest_pct,
    )

    params_out = {
        "event_types":      types,
        "event_type":       types[0] if len(types) == 1 else None,
        "start":            start,
        "end":              end,
        "min_score":        min_score,
        "ml_min_prob":      ml_min_prob,
        "stop_loss_pct":    stop_loss_pct,
        "target_pct":       target_pct,
        "market":           mkt,
        "walkforward":      walkforward,
        "initial_capital":  initial_capital,
        "invest_per_trade": invest_per_trade,
        "max_positions":    max_positions,
        "cost_note":        "소형주(<50억) round-trip ~1.13%, 대형주 ~0.43% (거래세 0.3%)",
    }

    _SIG_COLS = ["code", "date", "close", "volume", "amount", "signal_score"]
    _BAR_COLS = ["code", "date", "open", "high", "low", "close", "volume", "amount"]

    async def _run_window(s_d: date, e_d: date):
        sig_rows = await _fetch(s_d, e_d)
        if not sig_rows:
            return None, []
        sigs = pd.DataFrame(sig_rows, columns=_SIG_COLS)
        codes = sigs["code"].unique().tolist()
        bar_rows = await db.fetch(
            "SELECT code, date::TEXT, open, high, low, close, volume, "
            "COALESCE(close * volume, 0) AS amount "
            "FROM daily_bars WHERE code = ANY($1) AND date BETWEEN $2 AND $3 "
            "ORDER BY code, date",
            codes, s_d, e_d,
        )
        bars = pd.DataFrame(bar_rows, columns=_BAR_COLS) if bar_rows else pd.DataFrame(columns=_BAR_COLS)
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

        combined = engine._stats(all_trades, {}) if all_trades else None
        # 종목명 조회
        wf_codes = list({t.code for t in all_trades})
        wf_name_rows = await db.fetch(
            "SELECT code, name FROM stocks WHERE code = ANY($1)", wf_codes
        ) if wf_codes else []
        wf_code_name = {r["code"]: r["name"] for r in wf_name_rows}

        def _wf_trade(t):
            d = dataclasses.asdict(t)
            d["name"] = wf_code_name.get(t.code, "")
            return d

        return {
            "params":       params_out,
            "walkforward":  wf_results,
            "result":       combined.summary() if combined else None,
            "trade_log":    [_wf_trade(t) for t in all_trades],
            "equity_curve": combined.equity_curve if combined else [],
        }

    # ── 단일 백테스트 ─────────────────────────────────────────
    sig_rows = await _fetch(start_d, end_d)
    if not sig_rows:
        return {
            "error": f"해당 기간에 신호가 없습니다 ({start} ~ {end_d}). "
                     "이벤트 타입을 선택하거나 기간을 조정해 보세요."
        }

    signals = pd.DataFrame(sig_rows, columns=_SIG_COLS)

    codes = signals["code"].unique().tolist()
    bar_rows = await db.fetch(
        "SELECT code, date::TEXT, open, high, low, close, volume, "
        "COALESCE(close * volume, 0) AS amount "
        "FROM daily_bars WHERE code = ANY($1) AND date BETWEEN $2 AND $3 "
        "ORDER BY code, date",
        codes, start_d, end_d,
    )
    bars = pd.DataFrame(bar_rows, columns=_BAR_COLS) if bar_rows else pd.DataFrame(columns=_BAR_COLS)
    result = engine.run(signals, bars)

    # 종목명 조회 (trade_log 표시용)
    trade_codes = list({t.code for t in result.trades})
    name_rows = await db.fetch(
        "SELECT code, name FROM stocks WHERE code = ANY($1)", trade_codes
    )
    code_name = {r["code"]: r["name"] for r in name_rows}

    def _trade_dict(t):
        d = dataclasses.asdict(t)
        d["name"] = code_name.get(t.code, "")
        return d

    return {
        "params":       params_out,
        "result":       result.summary(),
        "trade_log":    [_trade_dict(t) for t in result.trades],
        "equity_curve": result.equity_curve,
        "sample_trades": [
            {"code": t.code, "name": code_name.get(t.code, ""),
             "entry": t.entry_date, "exit": t.exit_date,
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

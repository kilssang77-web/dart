"""
백테스트 엔진 (현실화 + 고성능 버전)
주요 개선사항:
1. 포지션 사이징 파라미터 (initial_capital, sizing_method, invest_per_trade, max_positions)
2. 동시 최대 보유 종목 수 제한 (max_positions)
3. 일일 기준 Sharpe 계산 (per-trade → daily equity curve)
4. 소형주 vs 대형주 슬리피지 차등 적용 (amount 기준)
5. Sortino, Calmar ratio 추가
6. equity_curve 반환 (프론트 차트용)
7. 핫루프 pandas 제거 → list/dict 기반으로 110s → <5s 성능 개선
"""
import bisect
import logging
import os
from dataclasses import dataclass, field
from typing import Literal, NamedTuple

import numpy as np
from datetime import date as _date

logger = logging.getLogger(__name__)

_BACKTEST_COMMISSION   = float(os.getenv("BACKTEST_COMMISSION",   "0.00015"))
_BACKTEST_SELL_TAX     = float(os.getenv("BACKTEST_SELL_TAX",     "0.00300"))
_BACKTEST_SLIP_LARGE   = float(os.getenv("BACKTEST_SLIP_LARGE",   "0.00050"))
_BACKTEST_SLIP_SMALL   = float(os.getenv("BACKTEST_SLIP_SMALL",   "0.00400"))
_BACKTEST_LARGE_AMOUNT = float(os.getenv("BACKTEST_LARGE_AMOUNT", "5000000000"))
_RISK_FREE_DAILY       = 0.04 / 252.0


class _Bar(NamedTuple):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float


@dataclass
class Trade:
    code: str
    entry_date: str
    entry_price: float
    target_price: float
    stop_loss_price: float
    invest_amount: float = 0.0
    qty: int = 0
    exit_date: str = ""
    exit_price: float = 0.0
    pnl_pct: float = 0.0
    pnl_amount: float = 0.0
    status: str = "open"


@dataclass
class BacktestResult:
    total_trades: int = 0
    win_trades: int = 0
    loss_trades: int = 0
    win_rate: float = 0.0
    avg_return: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0
    total_pnl_pct: float = 0.0
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "total":          self.total_trades,
            "win":            self.win_trades,
            "loss":           self.loss_trades,
            "win_rate":       f"{self.win_rate:.1%}",
            "avg_return":     f"{self.avg_return:.2f}%",
            "avg_win":        f"{self.avg_win:.2f}%",
            "avg_loss":       f"{self.avg_loss:.2f}%",
            "profit_factor":  round(self.profit_factor, 2),
            "max_drawdown":   f"{self.max_drawdown:.2f}%",
            "sharpe":         round(self.sharpe, 2),
            "sortino":        round(self.sortino, 2),
            "calmar":         round(self.calmar, 2),
            "total_pnl_pct":  f"{self.total_pnl_pct:.2f}%",
        }


class BacktestEngine:

    def __init__(
        self,
        stop_loss_pct:     float = -0.05,
        target_pct:        float =  0.10,
        max_hold_days:     int   = 10,
        commission:        float = _BACKTEST_COMMISSION,
        sell_tax:          float = _BACKTEST_SELL_TAX,
        slippage_large:    float = _BACKTEST_SLIP_LARGE,
        slippage_small:    float = _BACKTEST_SLIP_SMALL,
        initial_capital:   float = 10_000_000,
        invest_per_trade:  float = 500_000,
        max_positions:     int   = 5,
        sizing_method:     Literal["fixed", "pct"] = "fixed",
        invest_pct:        float = 10.0,
    ):
        self.stop_loss_pct   = stop_loss_pct
        self.target_pct      = target_pct
        self.max_hold_days   = max_hold_days
        self.commission      = commission
        self.sell_tax        = sell_tax
        self.slip_large      = slippage_large
        self.slip_small      = slippage_small
        self.initial_capital = initial_capital
        self.invest_per_trade = invest_per_trade
        self.max_positions   = max_positions
        self.sizing_method   = sizing_method
        self.invest_pct      = invest_pct

    def _slip(self, amount: float) -> float:
        return self.slip_large if amount >= _BACKTEST_LARGE_AMOUNT else self.slip_small

    def _get_invest(self, capital: float) -> float:
        if self.sizing_method == "pct":
            return capital * self.invest_pct / 100.0
        return min(self.invest_per_trade, capital)

    def run(self, signals, bars) -> BacktestResult:
        # ── bars를 code별 정렬된 _Bar 리스트로 인덱싱 (pandas 핫루프 제거) ──
        bars_by_code: dict[str, list[_Bar]] = {}
        bars_dates:   dict[str, list[str]]  = {}   # bisect용 date 키 리스트
        for code, grp in bars.groupby("code"):
            grp_sorted = grp.sort_values("date")
            bar_list: list[_Bar] = []
            for row in grp_sorted.itertuples(index=False):
                bar_list.append(_Bar(
                    date=str(row.date),
                    open=float(getattr(row, "open", 0) or 0),
                    high=float(getattr(row, "high", 0) or 0),
                    low=float(getattr(row, "low",  0) or 0),
                    close=float(row.close or 0),
                    volume=float(row.volume or 0),
                    amount=float(getattr(row, "amount", 0) or 0),
                ))
            bars_by_code[code] = bar_list
            bars_dates[code]   = [b.date for b in bar_list]

        capital       = self.initial_capital
        active: dict[str, Trade] = {}
        completed: list[Trade]   = []
        daily_equity: dict[str, float] = {}
        _last_update_date = ""   # _update_active 중복 호출 방지

        # 신호를 날짜 순 처리 (iterrows → itertuples, 10× 빠름)
        signals_sorted = signals.sort_values("date").reset_index(drop=True)
        sig_records = list(signals_sorted.itertuples(index=False))

        for sig in sig_records:
            code         = sig.code
            sig_date_str = str(sig.date)[:10]   # "YYYY-MM-DD"

            # 날짜가 바뀔 때만 active 포지션 업데이트
            if sig_date_str != _last_update_date and active:
                self._update_active_fast(
                    active, completed, bars_by_code, bars_dates, sig_date_str
                )
                capital = self.initial_capital + sum(t.pnl_amount for t in completed)
                _last_update_date = sig_date_str

            if code in active:
                continue
            if len(active) >= self.max_positions:
                continue
            invest = self._get_invest(capital)
            if invest < 10_000:
                continue

            amount    = float(getattr(sig, "amount", 0) or invest)
            slip      = self._slip(amount)
            buy_cost  = self.commission + slip
            sell_cost = self.commission + slip + self.sell_tax
            entry     = float(sig.close) * (1 + buy_cost)
            target    = entry * (1 + self.target_pct)
            stop      = entry * (1 + self.stop_loss_pct)
            qty       = max(1, int(invest / entry))
            invest_actual = entry * qty

            active[code] = Trade(
                code=code,
                entry_date=sig_date_str,
                entry_price=entry,
                target_price=target,
                stop_loss_price=stop,
                invest_amount=invest_actual,
                qty=qty,
            )
            daily_equity[sig_date_str] = capital

        # 남은 포지션 만기 처리
        for code, trade in list(active.items()):
            bar_list = bars_by_code.get(code)
            if bar_list:
                last = bar_list[-1]
                slip = self._slip(last.amount)
                sell_cost = self.commission + slip + self.sell_tax
                trade.exit_price = last.close * (1 - sell_cost)
                trade.exit_date  = last.date
                trade.status     = "timeout"
                trade.pnl_pct    = (trade.exit_price - trade.entry_price) / trade.entry_price * 100
                trade.pnl_amount = (trade.exit_price - trade.entry_price) * trade.qty
            completed.append(trade)

        return self._stats(completed, daily_equity)

    def _update_active_fast(
        self,
        active: dict,
        completed: list,
        bars_by_code: dict[str, list[_Bar]],
        bars_dates:   dict[str, list[str]],
        until_date: str,
    ) -> None:
        """active 포지션을 until_date까지 simulate — 순수 리스트/bisect, pandas 없음."""
        to_close: list[str] = []
        for code, trade in active.items():
            bar_list = bars_by_code.get(code)
            date_list = bars_dates.get(code)
            if not bar_list:
                continue

            # bisect로 entry_date 이후, until_date 이하 구간 O(log n)
            lo = bisect.bisect_right(date_list, trade.entry_date)
            hi = bisect.bisect_right(date_list, until_date)
            future_bars = bar_list[lo:hi]

            for i, bar in enumerate(future_bars):
                slip      = self._slip(bar.amount)
                sell_cost = self.commission + slip + self.sell_tax

                if bar.low <= trade.stop_loss_price:
                    trade.exit_price = trade.stop_loss_price * (1 - sell_cost)
                    trade.exit_date  = bar.date
                    trade.status     = "loss"
                    trade.pnl_pct    = (trade.exit_price - trade.entry_price) / trade.entry_price * 100
                    trade.pnl_amount = (trade.exit_price - trade.entry_price) * trade.qty
                    to_close.append(code)
                    break
                if bar.high >= trade.target_price:
                    trade.exit_price = trade.target_price * (1 - sell_cost)
                    trade.exit_date  = bar.date
                    trade.status     = "win"
                    trade.pnl_pct    = (trade.exit_price - trade.entry_price) / trade.entry_price * 100
                    trade.pnl_amount = (trade.exit_price - trade.entry_price) * trade.qty
                    to_close.append(code)
                    break
                if i + 1 >= self.max_hold_days:
                    trade.exit_price = bar.close * (1 - sell_cost)
                    trade.exit_date  = bar.date
                    trade.status     = "timeout"
                    trade.pnl_pct    = (trade.exit_price - trade.entry_price) / trade.entry_price * 100
                    trade.pnl_amount = (trade.exit_price - trade.entry_price) * trade.qty
                    to_close.append(code)
                    break

        for code in to_close:
            completed.append(active.pop(code))

    def _stats(self, trades: list[Trade], daily_equity: dict) -> BacktestResult:
        closed = [t for t in trades if t.exit_price > 0]
        if not closed:
            return BacktestResult(total_trades=len(trades), trades=trades)

        ret    = [float(t.pnl_pct) for t in closed]
        wins   = [r for r in ret if r > 0]
        losses = [r for r in ret if r <= 0]

        daily_returns: list[float] = []
        capital = self.initial_capital
        exit_by_date: dict[str, list[Trade]] = {}
        for t in sorted(closed, key=lambda x: x.exit_date):
            exit_by_date.setdefault(t.exit_date, []).append(t)

        sorted_dates = sorted(exit_by_date.keys())
        equity_curve = [{"date": sorted_dates[0] if sorted_dates else "", "equity": capital}]
        for d in sorted_dates:
            day_pnl = sum(t.pnl_amount for t in exit_by_date[d])
            capital += day_pnl
            daily_returns.append(day_pnl / max(self.initial_capital, 1.0) * 100)
            equity_curve.append({"date": d, "equity": capital})

        total_pnl_pct = (capital - self.initial_capital) / self.initial_capital * 100

        equities    = np.array([e["equity"] for e in equity_curve])
        running_max = np.maximum.accumulate(equities)
        drawdowns   = (equities - running_max) / running_max * 100
        mdd         = float(drawdowns.min())

        dr     = np.array(daily_returns) / 100.0
        excess = dr - _RISK_FREE_DAILY
        sharpe = float(excess.mean() / (excess.std(ddof=1) + 1e-9) * np.sqrt(252)) if len(dr) > 1 else 0.0

        downside = excess[excess < 0]
        sortino = (
            float(excess.mean() / (downside.std(ddof=1) + 1e-9) * np.sqrt(252))
            if len(downside) > 1 else 0.0
        )

        if sorted_dates and len(sorted_dates) >= 2:
            n_years = (_date.fromisoformat(sorted_dates[-1]) - _date.fromisoformat(sorted_dates[0])).days / 365.25
            cagr = ((1 + total_pnl_pct / 100) ** (1 / max(n_years, 0.01)) - 1) * 100
        else:
            cagr = total_pnl_pct
        calmar = round(cagr / (abs(mdd) + 1e-8), 3)

        gross_profit = sum(wins)
        gross_loss   = abs(sum(losses)) + 1e-8

        return BacktestResult(
            total_trades  = len(closed),
            win_trades    = len(wins),
            loss_trades   = len(losses),
            win_rate      = round(len(wins) / len(closed), 4),
            avg_return    = round(float(np.mean(ret)), 3),
            avg_win       = round(float(np.mean(wins)),   3) if wins   else 0.0,
            avg_loss      = round(float(np.mean(losses)), 3) if losses else 0.0,
            profit_factor = round(gross_profit / gross_loss, 3),
            max_drawdown  = round(mdd, 3),
            sharpe        = round(sharpe, 3),
            sortino       = round(sortino, 3),
            calmar        = round(calmar, 3),
            total_pnl_pct = round(total_pnl_pct, 3),
            trades        = closed,
            equity_curve  = equity_curve,
        )

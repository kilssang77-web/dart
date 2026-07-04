"""
백테스트 엔진 (현실화 버전)
주요 개선사항:
1. 포지션 사이징 파라미터 (initial_capital, sizing_method, invest_per_trade, max_positions)
2. 동시 최대 보유 종목 수 제한 (max_positions)
3. 일일 기준 Sharpe 계산 (per-trade → daily equity curve)
4. 소형주 vs 대형주 슬리피지 차등 적용 (amount 기준)
5. Sortino, Calmar ratio 추가
6. equity_curve 반환 (프론트 차트용)
"""
import logging
import os
from dataclasses import dataclass, field
from typing import Literal
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_BACKTEST_COMMISSION   = float(os.getenv("BACKTEST_COMMISSION",   "0.00015"))
_BACKTEST_SELL_TAX     = float(os.getenv("BACKTEST_SELL_TAX",     "0.00300"))
_BACKTEST_SLIP_LARGE   = float(os.getenv("BACKTEST_SLIP_LARGE",   "0.00050"))   # 대형주 (거래대금 50억+)
_BACKTEST_SLIP_SMALL   = float(os.getenv("BACKTEST_SLIP_SMALL",   "0.00400"))   # 소형주
_BACKTEST_LARGE_AMOUNT = float(os.getenv("BACKTEST_LARGE_AMOUNT", "5000000000"))  # 50억
_RISK_FREE_DAILY       = 0.04 / 252.0  # 연 4% 무위험 → 일별


@dataclass
class Trade:
    code: str
    entry_date: str
    entry_price: float
    target_price: float
    stop_loss_price: float
    invest_amount: float = 0.0    # 투입 금액 (원)
    qty: int = 0                  # 주수
    exit_date: str = ""
    exit_price: float = 0.0
    pnl_pct: float = 0.0
    pnl_amount: float = 0.0       # 원화 손익
    status: str = "open"          # open|win|loss|timeout


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
    total_pnl_pct: float = 0.0    # 백테스트 기간 총 수익률
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)  # [{date, equity}]

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
        # ── 현실화 파라미터 ──
        initial_capital:   float = 10_000_000,         # 초기 자본 (원)
        invest_per_trade:  float = 500_000,             # 종목당 투자금 (원)
        max_positions:     int   = 5,                   # 동시 최대 보유 종목 수
        sizing_method:     Literal["fixed", "pct"] = "fixed",  # fixed=고정금액, pct=자본대비%
        invest_pct:        float = 10.0,                # sizing_method=pct 시 자본 대비 비율
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
        """거래대금 기준 차등 슬리피지."""
        return self.slip_large if amount >= _BACKTEST_LARGE_AMOUNT else self.slip_small

    def _get_invest(self, capital: float) -> float:
        if self.sizing_method == "pct":
            return capital * self.invest_pct / 100.0
        return min(self.invest_per_trade, capital)

    def run(self, signals: pd.DataFrame, bars: pd.DataFrame) -> BacktestResult:
        # ── bars 인덱싱 ────────────────────────────────────────────────────────
        bars_by_code: dict[str, pd.DataFrame] = {}
        for code, grp in bars.groupby("code"):
            bars_by_code[code] = grp.sort_values("date").reset_index(drop=True)

        capital       = self.initial_capital
        active: dict[str, Trade] = {}   # code → 진행 중 trade
        completed: list[Trade]   = []
        daily_equity: dict[str, float] = {}   # date_str → 자본

        # 신호를 날짜 순 처리
        signals_sorted = signals.sort_values("date").reset_index(drop=True)

        for _, sig in signals_sorted.iterrows():
            code     = sig["code"]
            sig_date = pd.Timestamp(sig["date"]).normalize()
            sig_date_str = str(sig_date.date())

            # 진행 중 포지션 업데이트 (오늘 날짜 기준 청산 확인)
            self._update_active(active, completed, bars_by_code, sig_date_str, capital)
            capital = self.initial_capital + sum(t.pnl_amount for t in completed)

            # 이미 보유 중이면 스킵
            if code in active:
                continue
            # 최대 포지션 수 제한
            if len(active) >= self.max_positions:
                continue
            # 자본 부족
            invest = self._get_invest(capital)
            if invest < 10_000:
                continue

            # 진입 비용 계산
            amount    = float(sig.get("amount", invest))
            slip      = self._slip(amount)
            buy_cost  = self.commission + slip
            sell_cost = self.commission + slip + self.sell_tax
            entry     = float(sig["close"]) * (1 + buy_cost)
            target    = entry * (1 + self.target_pct)
            stop      = entry * (1 + self.stop_loss_pct)
            qty       = max(1, int(invest / entry))
            invest_actual = entry * qty

            trade = Trade(
                code=code,
                entry_date=sig_date_str,
                entry_price=entry,
                target_price=target,
                stop_loss_price=stop,
                invest_amount=invest_actual,
                qty=qty,
            )
            active[code] = trade
            daily_equity[sig_date_str] = capital

        # 남은 활성 포지션 만기 처리
        for code, trade in list(active.items()):
            code_bars = bars_by_code.get(code)
            if code_bars is not None:
                last = code_bars.iloc[-1]
                c = float(last.get("close", trade.entry_price))
                slip = self._slip(float(last.get("amount", 0)))
                sell_cost = self.commission + slip + self.sell_tax
                trade.exit_price = c * (1 - sell_cost)
                trade.exit_date  = str(last["date"])
                trade.status     = "timeout"
                trade.pnl_pct    = (trade.exit_price - trade.entry_price) / trade.entry_price * 100
                trade.pnl_amount = (trade.exit_price - trade.entry_price) * trade.qty
            completed.append(trade)

        return self._stats(completed, daily_equity)

    def _update_active(
        self,
        active: dict,
        completed: list,
        bars_by_code: dict,
        until_date: str,
        capital: float,
    ) -> None:
        """active 포지션들을 until_date까지 simulate 하여 청산 조건 확인."""
        to_close = []
        for code, trade in active.items():
            code_bars = bars_by_code.get(code)
            if code_bars is None:
                continue
            entry_dt = pd.Timestamp(trade.entry_date)
            until_dt = pd.Timestamp(until_date)
            future = code_bars[
                (pd.to_datetime(code_bars["date"]).dt.normalize() > entry_dt) &
                (pd.to_datetime(code_bars["date"]).dt.normalize() <= until_dt)
            ]
            for i, (_, row) in enumerate(future.iterrows()):
                h = float(row.get("high",  trade.entry_price))
                l = float(row.get("low",   trade.entry_price))
                c = float(row.get("close", trade.entry_price))
                amount = float(row.get("amount", 0))
                slip   = self._slip(amount)
                sell_cost = self.commission + slip + self.sell_tax

                if l <= trade.stop_loss_price:
                    trade.exit_price = trade.stop_loss_price * (1 - sell_cost)
                    trade.exit_date  = str(row["date"])
                    trade.status     = "loss"
                    trade.pnl_pct    = (trade.exit_price - trade.entry_price) / trade.entry_price * 100
                    trade.pnl_amount = (trade.exit_price - trade.entry_price) * trade.qty
                    to_close.append(code)
                    break
                if h >= trade.target_price:
                    trade.exit_price = trade.target_price * (1 - sell_cost)
                    trade.exit_date  = str(row["date"])
                    trade.status     = "win"
                    trade.pnl_pct    = (trade.exit_price - trade.entry_price) / trade.entry_price * 100
                    trade.pnl_amount = (trade.exit_price - trade.entry_price) * trade.qty
                    to_close.append(code)
                    break
                if i + 1 >= self.max_hold_days:
                    trade.exit_price = c * (1 - sell_cost)
                    trade.exit_date  = str(row["date"])
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

        # ── Equity curve (일별 자본 기준 daily return 계산) ─────────────────
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
            daily_ret = day_pnl / max(self.initial_capital, 1.0) * 100
            daily_returns.append(daily_ret)
            equity_curve.append({"date": d, "equity": capital})

        total_pnl_pct = (capital - self.initial_capital) / self.initial_capital * 100

        # ── MDD (자본 기준) ──────────────────────────────────────────────────
        equities    = np.array([e["equity"] for e in equity_curve])
        running_max = np.maximum.accumulate(equities)
        drawdowns   = (equities - running_max) / running_max * 100
        mdd         = float(drawdowns.min())

        # ── Sharpe (일별 기준, 표준) ─────────────────────────────────────────
        dr = np.array(daily_returns) / 100.0
        excess = dr - _RISK_FREE_DAILY
        sharpe = float(excess.mean() / (excess.std(ddof=1) + 1e-9) * np.sqrt(252)) if len(dr) > 1 else 0.0

        # ── Sortino (하방 변동성만 사용) ─────────────────────────────────────
        downside = excess[excess < 0]
        sortino = (
            float(excess.mean() / (downside.std(ddof=1) + 1e-9) * np.sqrt(252))
            if len(downside) > 1 else 0.0
        )

        # ── Calmar = CAGR / |MDD| ────────────────────────────────────────────
        if sorted_dates and len(sorted_dates) >= 2:
            n_years = (pd.Timestamp(sorted_dates[-1]) - pd.Timestamp(sorted_dates[0])).days / 365.25
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

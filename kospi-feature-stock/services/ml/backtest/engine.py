import logging
import os
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_BACKTEST_COMMISSION = float(os.getenv("BACKTEST_COMMISSION", "0.00015"))


@dataclass
class Trade:
    code: str
    entry_date: str
    entry_price: float
    target_price: float
    stop_loss_price: float
    exit_date: str = ""
    exit_price: float = 0.0
    pnl_pct: float = 0.0
    status: str = "open"   # open|win|loss|timeout


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
    trades: list[Trade] = field(default_factory=list)

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
        }


class BacktestEngine:

    def __init__(
        self,
        stop_loss_pct: float = -0.05,
        target_pct:    float =  0.10,
        max_hold_days: int   = 10,
        commission:    float = _BACKTEST_COMMISSION,
    ):
        self.stop_loss_pct = stop_loss_pct
        self.target_pct    = target_pct
        self.max_hold_days = max_hold_days
        self.commission    = commission

    def run(
        self,
        signals: pd.DataFrame,
        bars: pd.DataFrame,
    ) -> BacktestResult:
        # Pre-index bars by code for O(1) lookup instead of O(n) per signal
        bars_by_code: dict[str, pd.DataFrame] = {}
        for code, grp in bars.groupby("code"):
            bars_by_code[code] = grp.sort_values("date").reset_index(drop=True)

        trades = []
        for _, sig in signals.iterrows():
            code  = sig["code"]
            entry = float(sig["close"]) * (1 + self.commission)
            target = entry * (1 + self.target_pct)
            stop   = entry * (1 + self.stop_loss_pct)
            trade  = Trade(
                code=code,
                entry_date=str(sig["date"]),
                entry_price=entry,
                target_price=target,
                stop_loss_price=stop,
            )

            code_bars = bars_by_code.get(code)
            if code_bars is None:
                trades.append(trade)
                continue

            sig_date = str(sig["date"])
            future = code_bars[code_bars["date"] >= sig_date]
            for i, (_, row) in enumerate(future.iterrows()):
                if i == 0:
                    continue
                h = float(row.get("high", entry))
                l = float(row.get("low",  entry))
                c = float(row.get("close", entry))

                if l <= stop:
                    trade.exit_price = stop * (1 - self.commission)
                    trade.exit_date  = str(row["date"])
                    trade.status     = "loss"
                    break
                if h >= target:
                    trade.exit_price = target * (1 - self.commission)
                    trade.exit_date  = str(row["date"])
                    trade.status     = "win"
                    break
                if i >= self.max_hold_days:
                    trade.exit_price = c * (1 - self.commission)
                    trade.exit_date  = str(row["date"])
                    trade.status     = "timeout"
                    break

            if trade.exit_price:
                trade.pnl_pct = (trade.exit_price - trade.entry_price) / trade.entry_price * 100
            trades.append(trade)

        return self._stats(trades)

    def _stats(self, trades: list) -> "BacktestResult":
        closed = [t for t in trades if getattr(t, "exit_price", 0) > 0 and getattr(t, "pnl_pct", None) is not None]
        if not closed:
            return BacktestResult(total_trades=len(trades), trades=trades)

        ret    = [float(t.pnl_pct) for t in closed]
        wins   = [r for r in ret if r > 0]
        losses = [r for r in ret if r <= 0]

        # Equity curve: cumulative product starting at 1.0
        equity      = np.cumprod([1.0 + r / 100.0 for r in ret])
        running_max = np.maximum.accumulate(equity)
        drawdowns   = (equity - running_max) / running_max * 100
        mdd         = float(drawdowns.min())

        # Sharpe: annualise from per-trade returns
        try:
            avg_hold_days = np.mean([
                (pd.Timestamp(t.exit_date) - pd.Timestamp(t.entry_date)).days
                for t in closed
                if getattr(t, "exit_date", None) and getattr(t, "entry_date", None)
            ])
        except Exception:
            avg_hold_days = getattr(self, "max_hold_days", 5)
        trades_per_year = 252.0 / max(float(avg_hold_days), 1.0)
        r_arr  = np.array(ret)
        sharpe = float((r_arr.mean() / (r_arr.std(ddof=1) + 1e-8)) * np.sqrt(trades_per_year))

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
            trades        = closed,
        )

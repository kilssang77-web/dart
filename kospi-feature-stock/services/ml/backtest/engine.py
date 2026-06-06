import logging
from dataclasses import dataclass, field
from typing import Callable
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


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
        commission:    float = 0.00015,
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
        """
        signals: DataFrame with columns [code, date, close]
        bars:    MultiIndex DataFrame or pivot with columns = codes, index = date
        """
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

            future = self._get_future_bars(bars, code, str(sig["date"]))
            for i, (d, row) in enumerate(future.iterrows()):
                if i == 0:
                    continue
                h = float(row.get("high", row.get(code, {}).get("high", entry)))
                l = float(row.get("low",  row.get(code, {}).get("low", entry)))
                c = float(row.get("close",row.get(code, {}).get("close", entry)))

                if l <= stop:
                    trade.exit_price = stop * (1 - self.commission)
                    trade.exit_date  = str(d)
                    trade.status     = "loss"
                    break
                if h >= target:
                    trade.exit_price = target * (1 - self.commission)
                    trade.exit_date  = str(d)
                    trade.status     = "win"
                    break
                if i >= self.max_hold_days:
                    trade.exit_price = c * (1 - self.commission)
                    trade.exit_date  = str(d)
                    trade.status     = "timeout"
                    break

            if trade.exit_price:
                trade.pnl_pct = (trade.exit_price - trade.entry_price) / trade.entry_price * 100
            trades.append(trade)

        return self._stats(trades)

    def _get_future_bars(self, bars: pd.DataFrame, code: str, from_date: str):
        try:
            subset = bars[bars["code"] == code].sort_values("date")
            return subset[subset["date"] >= from_date].iterrows()
        except Exception:
            return iter([])

    def _stats(self, trades: list[Trade]) -> BacktestResult:
        closed = [t for t in trades if t.exit_price > 0]
        if not closed:
            return BacktestResult(total_trades=len(trades), trades=trades)

        ret = [t.pnl_pct for t in closed]
        wins   = [r for r in ret if r > 0]
        losses = [r for r in ret if r <= 0]
        gross_profit = sum(wins)
        gross_loss   = abs(sum(losses)) + 1e-8

        cum = np.cumsum(ret)
        peak = np.maximum.accumulate(cum)
        mdd  = float((cum - peak).min())

        r_arr  = np.array(ret)
        sharpe = float(r_arr.mean() / (r_arr.std() + 1e-8) * np.sqrt(252 / max(self.max_hold_days, 1)))

        return BacktestResult(
            total_trades  = len(closed),
            win_trades    = len(wins),
            loss_trades   = len(losses),
            win_rate      = len(wins) / len(closed),
            avg_return    = float(np.mean(ret)),
            avg_win       = float(np.mean(wins)) if wins else 0.0,
            avg_loss      = float(np.mean(losses)) if losses else 0.0,
            profit_factor = gross_profit / gross_loss,
            max_drawdown  = mdd,
            sharpe        = sharpe,
            trades        = closed,
        )

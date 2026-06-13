import logging
from dataclasses import dataclass, field
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
    signal_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "code":            self.code,
            "entry_date":      self.entry_date,
            "exit_date":       self.exit_date,
            "entry_price":     round(self.entry_price, 0),
            "exit_price":      round(self.exit_price, 0),
            "pnl_pct":         round(self.pnl_pct, 2),
            "status":          self.status,
            "signal_score":    round(self.signal_score, 3),
        }


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
    win_streak: int = 0
    lose_streak: int = 0
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
            "win_streak":     self.win_streak,
            "lose_streak":    self.lose_streak,
        }


class BacktestEngine:
    """
    한국 증시 현실 비용 모델:
      buy  side: commission(0.015%) + slippage(0.1%)          = 0.115%
      sell side: commission(0.015%) + slippage(0.1%) + tax(0.23%) = 0.345%
      round-trip total: ~0.46%
    """

    def __init__(
        self,
        stop_loss_pct: float = -0.05,
        target_pct:    float =  0.10,
        max_hold_days: int   = 10,
        commission:    float = 0.00015,   # 편도 수수료 0.015%
        slippage:      float = 0.00100,   # 편도 슬리피지 0.1% (시장충격)
        sell_tax:      float = 0.00230,   # 증권거래세 0.23%
    ):
        self.stop_loss_pct = stop_loss_pct
        self.target_pct    = target_pct
        self.max_hold_days = max_hold_days
        self.commission    = commission
        self.slippage      = slippage
        self.sell_tax      = sell_tax
        self._buy_cost  = commission + slippage
        self._sell_cost = commission + slippage + sell_tax

    def run(
        self,
        signals: pd.DataFrame,
        bars: pd.DataFrame,
    ) -> BacktestResult:
        bars_by_code: dict[str, pd.DataFrame] = {}
        for code, grp in bars.groupby("code"):
            bars_by_code[code] = grp.sort_values("date").reset_index(drop=True)

        trades = []
        for _, sig in signals.iterrows():
            code  = sig["code"]
            # 매수 체결가 = 종가 × (1 + 수수료 + 슬리피지)
            entry  = float(sig["close"]) * (1 + self._buy_cost)
            target = entry * (1 + self.target_pct)
            stop   = entry * (1 + self.stop_loss_pct)
            trade  = Trade(
                code=code,
                entry_date=str(sig["date"]),
                entry_price=entry,
                target_price=target,
                stop_loss_price=stop,
                signal_score=float(sig.get("signal_score", 0) or 0),
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
                    trade.exit_price = stop   * (1 - self._sell_cost)
                    trade.exit_date  = str(row["date"])
                    trade.status     = "loss"
                    break
                if h >= target:
                    trade.exit_price = target * (1 - self._sell_cost)
                    trade.exit_date  = str(row["date"])
                    trade.status     = "win"
                    break
                if i >= self.max_hold_days:
                    trade.exit_price = c * (1 - self._sell_cost)
                    trade.exit_date  = str(row["date"])
                    trade.status     = "timeout"
                    break

            if trade.exit_price:
                trade.pnl_pct = (trade.exit_price - trade.entry_price) / trade.entry_price * 100
            trades.append(trade)

        return self._stats(trades)

    def _stats(self, trades: list[Trade]) -> BacktestResult:
        closed = [t for t in trades if t.exit_price > 0]
        if not closed:
            return BacktestResult(total_trades=len(trades), trades=trades)

        ret = [t.pnl_pct for t in closed]
        wins   = [r for r in ret if r > 0]
        losses = [r for r in ret if r <= 0]
        gross_profit = sum(wins)
        gross_loss   = abs(sum(losses)) + 1e-8

        # Max drawdown: assume 2% fixed position size → peak-to-trough on equity curve
        r_pct   = np.array(ret)
        pos_r   = r_pct / 100 * 0.02          # each trade = 2% of portfolio
        equity  = np.cumprod(1 + pos_r)        # normalized equity curve
        peak_eq = np.maximum.accumulate(equity)
        mdd     = float(((equity - peak_eq) / peak_eq).min()) * 100

        scale = np.sqrt(252 / max(self.max_hold_days, 1))
        sharpe = float(r_pct.mean() / (r_pct.std() + 1e-8) * scale)

        # Sortino: downside deviation (losses only)
        down = r_pct[r_pct < 0]
        down_std = float(down.std()) if len(down) > 1 else 1e-8
        sortino = float(r_pct.mean() / (down_std + 1e-8) * scale)

        # Calmar: annualised return / max drawdown
        ann_ret = float(r_pct.mean()) * (252 / max(self.max_hold_days, 1))
        calmar  = ann_ret / max(abs(mdd), 1e-8)

        # 연속 승/패 최대
        max_win_streak = max_lose_streak = cur_win = cur_lose = 0
        for r in ret:
            if r > 0:
                cur_win += 1; cur_lose = 0
                max_win_streak = max(max_win_streak, cur_win)
            else:
                cur_lose += 1; cur_win = 0
                max_lose_streak = max(max_lose_streak, cur_lose)

        # 자본금 곡선 (거래별)
        equity_curve = []
        cumulative = 1.0
        for t in closed:
            cumulative *= (1 + t.pnl_pct / 100 * 0.02)  # 2% 포지션 기준
            peak = max((p["equity"] for p in equity_curve), default=1.0)
            dd = (cumulative - peak) / peak * 100 if cumulative < peak else 0.0
            equity_curve.append({
                "date":     t.exit_date,
                "equity":   round(cumulative, 5),
                "drawdown": round(dd, 3),
                "pnl":      round(t.pnl_pct, 2),
            })

        return BacktestResult(
            total_trades  = len(closed),
            win_trades    = len(wins),
            loss_trades   = len(losses),
            win_rate      = len(wins) / len(closed),
            avg_return    = float(r_pct.mean()),
            avg_win       = float(np.mean(wins)) if wins else 0.0,
            avg_loss      = float(np.mean(losses)) if losses else 0.0,
            profit_factor = gross_profit / gross_loss,
            max_drawdown  = mdd,
            sharpe        = sharpe,
            sortino       = sortino,
            calmar        = calmar,
            win_streak    = max_win_streak,
            lose_streak   = max_lose_streak,
            trades        = closed,
            equity_curve  = equity_curve,
        )

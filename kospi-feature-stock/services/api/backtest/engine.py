import logging
import os
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_BACKTEST_COMMISSION   = float(os.getenv("BACKTEST_COMMISSION",   "0.00015"))  # 편도 수수료 0.015%
_BACKTEST_SLIPPAGE     = float(os.getenv("BACKTEST_SLIPPAGE",     "0.00050"))  # 대형주 슬리피지 0.05%
_BACKTEST_SLIPPAGE_SM  = float(os.getenv("BACKTEST_SLIPPAGE_SM",  "0.00400"))  # 소형주 슬리피지 0.4%
_BACKTEST_SELL_TAX     = float(os.getenv("BACKTEST_SELL_TAX",     "0.00300"))  # 증권거래세 0.3%
_BACKTEST_SMALL_AMOUNT = float(os.getenv("BACKTEST_SMALL_AMOUNT", "5000000000"))  # 소형주 기준 거래대금 50억


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
      대형주(거래대금 50억+): buy 0.065% + sell 0.365%  = round-trip ~0.43%
      소형주(거래대금 50억미만): buy 0.415% + sell 0.715% = round-trip ~1.13%
      거래세: 0.3% (매도시), 수수료: 0.015% (편도)
    """

    def __init__(
        self,
        stop_loss_pct:    float = -0.05,
        target_pct:       float =  0.10,
        max_hold_days:    int   = 10,
        max_daily_entries: int  = 0,       # 0 = 무제한
        commission:       float = _BACKTEST_COMMISSION,
        slippage:         float = _BACKTEST_SLIPPAGE,
        slippage_small:   float = _BACKTEST_SLIPPAGE_SM,
        sell_tax:         float = _BACKTEST_SELL_TAX,
        small_amount:     float = _BACKTEST_SMALL_AMOUNT,
    ):
        self.stop_loss_pct    = stop_loss_pct
        self.target_pct       = target_pct
        self.max_hold_days    = max_hold_days
        self.max_daily_entries = max_daily_entries
        self.commission       = commission
        self.slippage         = slippage
        self.slippage_small   = slippage_small
        self.sell_tax         = sell_tax
        self.small_amount     = small_amount

    def _costs(self, amount: float) -> tuple[float, float]:
        """거래대금 기반 슬리피지 차등 적용. (buy_cost, sell_cost) 반환."""
        slip = self.slippage_small if amount < self.small_amount else self.slippage
        return self.commission + slip, self.commission + slip + self.sell_tax

    def run(
        self,
        signals: pd.DataFrame,
        bars: pd.DataFrame,
    ) -> BacktestResult:
        # bars를 numpy 배열로 캐시: code → (dates, highs, lows, closes)
        bars_cache: dict[str, tuple] = {}
        for code, grp in bars.groupby("code"):
            g = grp.sort_values("date").reset_index(drop=True)
            bars_cache[code] = (
                g["date"].to_numpy(dtype=str),
                g["high"].to_numpy(dtype=float),
                g["low"].to_numpy(dtype=float),
                g["close"].to_numpy(dtype=float),
            )

        trades = []
        daily_counts: dict[str, int] = {}   # date → 당일 진입 수

        for row in signals.itertuples(index=False):
            code     = row.code
            sig_date = str(row.date)

            # 하루 최대 진입 제한
            if self.max_daily_entries > 0:
                cnt = daily_counts.get(sig_date, 0)
                if cnt >= self.max_daily_entries:
                    continue
                daily_counts[sig_date] = cnt + 1

            # 거래대금 기반 슬리피지 선택
            close  = float(row.close)
            volume = float(getattr(row, "volume", 0) or 0)
            amount = float(getattr(row, "amount", close * volume) or close * volume)
            buy_cost, sell_cost = self._costs(amount)

            entry  = close * (1 + buy_cost)
            target = entry * (1 + self.target_pct)
            stop   = entry * (1 + self.stop_loss_pct)
            trade  = Trade(
                code=code,
                entry_date=sig_date,
                entry_price=entry,
                target_price=target,
                stop_loss_price=stop,
                signal_score=float(getattr(row, "signal_score", 0) or 0),
            )

            cached = bars_cache.get(code)
            if cached is None:
                trades.append(trade)
                continue

            dates, highs, lows, closes = cached
            idx = int(np.searchsorted(dates, sig_date))  # 진입일 위치
            end = min(idx + self.max_hold_days + 1, len(dates))
            for i in range(idx + 1, end):
                l = lows[i]
                h = highs[i]
                c = closes[i]
                if l <= stop:
                    trade.exit_price = stop   * (1 - sell_cost)
                    trade.exit_date  = dates[i]
                    trade.status     = "loss"
                    break
                if h >= target:
                    trade.exit_price = target * (1 - sell_cost)
                    trade.exit_date  = dates[i]
                    trade.status     = "win"
                    break
                if i == end - 1:
                    trade.exit_price = c * (1 - sell_cost)
                    trade.exit_date  = dates[i]
                    trade.status     = "timeout"

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

        # 자본금 곡선 (거래별) — O(n) running-peak
        equity_curve = []
        cumulative = 1.0
        peak_eq_run = 1.0
        for t in closed:
            cumulative *= (1 + t.pnl_pct / 100 * 0.02)  # 2% 포지션 기준
            if cumulative > peak_eq_run:
                peak_eq_run = cumulative
            dd = (cumulative - peak_eq_run) / peak_eq_run * 100 if cumulative < peak_eq_run else 0.0
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

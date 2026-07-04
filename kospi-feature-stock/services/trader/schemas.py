from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class TraderSettings(BaseModel):
    is_active: bool = False
    mode: str = "paper"               # paper | live
    sizing_method: str = "fixed_fraction"
    max_invest_per_trade: int = 500_000
    max_total_invest: int = 3_000_000
    max_positions: int = 5
    daily_loss_limit: int = 100_000
    min_prob: float = 0.45
    kelly_fraction: float = 0.25
    fixed_fraction_pct: float = 10.0
    auto_sell: bool = True
    allow_manual_order: bool = True


class TraderSettingsUpdate(BaseModel):
    is_active: Optional[bool] = None
    mode: Optional[str] = None
    sizing_method: Optional[str] = None
    max_invest_per_trade: Optional[int] = None
    max_total_invest: Optional[int] = None
    max_positions: Optional[int] = None
    daily_loss_limit: Optional[int] = None
    min_prob: Optional[float] = None
    kelly_fraction: Optional[float] = None
    fixed_fraction_pct: Optional[float] = None
    auto_sell: Optional[bool] = None
    allow_manual_order: Optional[bool] = None


class ManualOrderRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=10)
    side: str = Field(..., pattern="^(BUY|SELL)$")
    qty: int = Field(..., ge=1)
    price: int = Field(default=0, ge=0)  # 0=시장가
    order_type: str = Field(default="MARKET", pattern="^(MARKET|LIMIT)$")
    rec_id: Optional[int] = None


class OrderResponse(BaseModel):
    id: int
    order_no: Optional[str]
    rec_id: Optional[int]
    code: str
    name: Optional[str]
    side: str
    order_type: str
    order_price: int
    order_qty: int
    filled_qty: int
    avg_filled_price: Optional[float]
    status: str
    mode: str
    error_msg: Optional[str]
    created_at: datetime


class PositionResponse(BaseModel):
    id: int
    code: str
    name: Optional[str]
    qty: int
    avg_price: float
    current_price: Optional[float]
    target_price: Optional[float]
    stop_loss_price: Optional[float]
    unrealized_pct: Optional[float]
    unrealized_amount: Optional[float]
    invest_amount: float
    entry_date: str
    mode: str
    rec_id: Optional[int]


class HoldingItem(BaseModel):
    code: str
    name: str
    qty: int
    avg_price: int
    current_price: int
    eval_amount: int
    pnl_pct: float
    pnl_amount: int


class BalanceResponse(BaseModel):
    success: bool
    deposit: int = 0
    total_eval: int = 0
    total_buy: int = 0
    holdings: list[HoldingItem] = []
    error_msg: str = ""


class DailyPnlResponse(BaseModel):
    trade_date: str
    mode: str
    realized_pnl: int
    unrealized_pnl: int
    total_trades: int
    win_trades: int
    loss_trades: int
    buy_amount: int
    sell_amount: int
    is_limit_hit: bool
    win_rate: Optional[float] = None
    today_loss_guard: Optional[dict] = None


class AutoExecuteLog(BaseModel):
    rec_id: int
    code: str
    action: str
    reason: str
    qty: int = 0
    price: int = 0
    order_id: Optional[int] = None
    success: bool = False
    created_at: datetime

from __future__ import annotations
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, field_validator


class RecommendationResponse(BaseModel):
    id: int
    created_at: str
    fe_detected_at: Optional[str] = None
    feature_event_id: Optional[int] = None
    code: str
    name: str
    market: str
    action: str
    entry_price: int
    target_price: int
    stop_loss_price: int
    expected_hold_days: int
    success_prob: float
    expected_return: float
    risk_score: float
    risk_reward_ratio: float
    rationale: dict[str, Any] = {}
    similar_cases: list[dict[str, Any]] = []
    rec_count: int = 1
    current_price: Optional[int] = None
    current_change_rate: Optional[float] = None


class FeatureEventResponse(BaseModel):
    id: int
    detected_at: str
    code: str
    name: str
    market: str
    event_type: str
    price: Optional[int] = None
    change_rate: Optional[float] = None
    volume_ratio: Optional[float] = None
    signal_score: Optional[float] = None
    risk_score: Optional[float] = None


class DisclosureResponse(BaseModel):
    id: int
    rcept_no: str
    code: Optional[str] = None
    corp_name: Optional[str] = None
    disclosed_at: str
    title: str
    category: Optional[str] = None
    sentiment_score: Optional[float] = None
    amount: Optional[int] = None
    keywords: list[str] = []
    counterparty: Optional[str] = None


class StockResponse(BaseModel):
    code: str
    name: str
    market: str
    sector: Optional[str] = None
    is_active: bool = True
    is_trading_halt: bool = False


class SignalItem(RecommendationResponse):
    fe_event_type: Optional[str] = None
    fe_signal_score: Optional[float] = None
    fe_detected_at: Optional[str] = None


class CodeSignalsResponse(BaseModel):
    total_count: int
    signals: list[SignalItem]


class PerformanceStatsResponse(BaseModel):
    total_count: int
    buy_count: int
    success_count: int
    avg_return: Optional[float] = None
    avg_pred_prob: Optional[float] = None
    success_rate: float


class NewsStockLink(BaseModel):
    code: str
    name: str


class NewsItem(BaseModel):
    id: int
    source: Optional[str] = None
    published_at: str
    title: str
    content: Optional[str] = None
    url: Optional[str] = None
    sentiment_score: Optional[float] = None
    category: Optional[str] = None
    keywords: list[str] = []
    codes: list[str] = []          # 하위 호환 유지
    stock_links: list[NewsStockLink] = []
    corp_name: Optional[str] = None

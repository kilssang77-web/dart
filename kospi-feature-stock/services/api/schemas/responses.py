from __future__ import annotations
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, field_validator


class RecommendationResponse(BaseModel):
    id: int
    created_at: str
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


class PerformanceStatsResponse(BaseModel):
    total_count: int
    buy_count: int
    success_count: int
    avg_return: Optional[float] = None
    avg_pred_prob: Optional[float] = None
    success_rate: float

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from ...database import get_db
from ...models import User
from ...services import MarketIntelService
from ...common.security import get_current_user

router = APIRouter(prefix="/market-intel", tags=["시장인텔리전스"])
svc = MarketIntelService()


@router.get("/agency-heatmap")
def agency_heatmap(
    months: int = Query(12, ge=1, le=36),
    top_n: int = Query(20, ge=5, le=50),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """발주처별 낙찰율 박스플롯 히트맵 데이터."""
    return svc.agency_heatmap(db, months=months, top_n=top_n)


@router.get("/winner-trend")
def winner_trend(
    agency_name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """월별 낙찰율 추세."""
    return svc.winner_rate_trend(db, agency_name=agency_name)


@router.get("/top-winners")
def top_winners(
    agency_name: Optional[str] = Query(None),
    top_n: int = Query(10, ge=3, le=30),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """낙찰 다발 업체 순위."""
    return svc.top_winner_companies(db, agency_name=agency_name, top_n=top_n)

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import User
from ...schemas import (
    BidContextResponse, SimulateBidRequest, SimulateBidResponse,
    AgencyWinHistogramResponse, WinProbCurveResponse,
)
from ...services import DecisionService
from ...common.security import get_current_user

router = APIRouter(prefix="/bids", tags=["투찰결정"])
svc = DecisionService()


@router.get("/{bid_id}/bid-context", response_model=BidContextResponse)
def get_bid_context(
    bid_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """투찰 결정용 공고 컨텍스트 — A값, 사정율 예측, 경쟁사 패턴."""
    ctx = svc.get_bid_context(db, bid_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="bid not found")
    return ctx


@router.get("/{bid_id}/agency-win-histogram", response_model=AgencyWinHistogramResponse)
def get_agency_win_histogram(
    bid_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """inpo21c 실증 기관별 낙찰 분포 — base_ratio 0.001 버킷."""
    return svc.get_agency_win_histogram(db, bid_id)


@router.get("/{bid_id}/win-prob-curve", response_model=WinProbCurveResponse)
def get_win_prob_curve(
    bid_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """bid_rate 구간별 낙찰확률 곡선 — LightGBM 모델 기반."""
    return svc.get_win_prob_curve(db, bid_id)


@router.post("/{bid_id}/simulate-bid", response_model=SimulateBidResponse)
def simulate_bid(
    bid_id: int,
    req: SimulateBidRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    복수예가 시뮬레이션.
    - yega_values=None  : 추정 모드 (A값 ± 2.8% Monte Carlo)
    - yega_values=[15개]: 실측 모드 (C(15,4)=1365 전수 열거)
    """
    result = svc.simulate_bid(db, bid_id, req)
    if not result:
        raise HTTPException(status_code=404, detail="bid not found")
    if result.get("error") == "base_amount_missing":
        raise HTTPException(status_code=400, detail="기초금액 정보가 없어 시뮬레이션을 실행할 수 없습니다.")
    return result

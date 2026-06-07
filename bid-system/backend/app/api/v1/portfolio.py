"""포트폴리오 최적화 API — E7 입찰 포트폴리오 최적화 엔진"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...database import get_db
from ...schemas import PortfolioOptimizeRequest, PortfolioPlanResponse
from ...services import PortfolioService
from .auth import get_current_user

router = APIRouter(prefix="/portfolio", tags=["포트폴리오 최적화"])
_svc = PortfolioService()


@router.post("/optimize", response_model=PortfolioPlanResponse)
def optimize_portfolio(
    body: PortfolioOptimizeRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    주간 포트폴리오 최적화.

    입력한 공고 목록 중 보증한도·동시 진행 제약 하에서
    기대 수주건수를 최대화하는 투찰 조합을 반환합니다.

    반환:
      - selected: 투찰 권장 공고
      - not_selected: 선별됐으나 제약으로 미선택
      - no_go_list: GO 판정 안 된 공고
      - expected_wins: 기대 수주 건수
      - schedule: 날짜별 투찰 일정
    """
    return _svc.optimize(db, user.id, body.bid_ids)


@router.get("/active")
def get_active_portfolio(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """현재 진행중 포트폴리오 상태 조회"""
    from ...models import PortfolioState, Bid
    rows = db.query(PortfolioState).filter(
        PortfolioState.status == "ACTIVE",
    ).all()
    result = []
    for r in rows:
        bid = db.query(Bid).filter(Bid.id == r.bid_id).first()
        result.append({
            "bid_id":          r.bid_id,
            "title":           bid.title if bid else "",
            "base_amount":     bid.base_amount if bid else 0,
            "bid_date":        r.bid_date.isoformat() if r.bid_date else None,
            "submitted_rate":  float(r.submitted_rate) if r.submitted_rate else None,
            "bond_exposure":   r.bond_exposure,
            "status":          r.status,
        })
    return {"active": result, "count": len(result)}

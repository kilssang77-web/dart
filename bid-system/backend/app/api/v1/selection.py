"""공고 선별 API — E1 엔진 GO/NO_GO/WATCH 판정"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...database import get_db
from ...services import BidSelectionService
from .auth import get_current_user

router = APIRouter(prefix="/selection", tags=["공고 선별"])
_svc = BidSelectionService()


@router.post("/evaluate/{bid_id}")
def evaluate_bid(
    bid_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """단일 공고 선별 평가 — GO/NO_GO/WATCH 판정 + EV 계산"""
    return _svc.evaluate_bid(db, bid_id, user.id)


@router.get("/go-list")
def get_go_list(
    days: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """최근 n일 GO 목록 반환 — 점수 내림차순"""
    return _svc.get_go_list(db, user.id, days)


@router.post("/evaluate-batch")
def evaluate_batch(
    body: dict,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    여러 공고 일괄 평가.
    body: {"bid_ids": [1, 2, 3, ...]}
    """
    bid_ids = body.get("bid_ids", [])
    results = []
    for bid_id in bid_ids[:50]:  # 한 번에 최대 50개
        try:
            r = _svc.evaluate_bid(db, bid_id, user.id)
            results.append(r)
        except Exception as e:
            results.append({"bid_id": bid_id, "error": str(e)})
    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return {"results": results, "total": len(results)}

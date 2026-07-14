"""실제 투찰 결과 API — E6 피드백 루프"""
from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...database import get_db
from ...schemas import ActualOutcomeCreate, ActualOutcomeOut
from ...services import ActualOutcomeService
from ...models import ActualBidOutcome
from .auth import get_current_user

router = APIRouter(prefix="/outcomes", tags=["투찰 결과"])
_svc = ActualOutcomeService()


@router.post("", response_model=dict)
def record_outcome(
    body: ActualOutcomeCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    실제 투찰 결과 기록.
    낙찰(WON) / 패찰(LOST) / 적격탈락(DISQUALIFIED) 입력 시
    피드백 루프가 자동으로 실행됩니다.
    """
    return _svc.record_outcome(db, user.id, body.model_dump())


@router.get("", response_model=List[ActualOutcomeOut])
def list_outcomes(
    limit: int = Query(20, ge=1, le=100),
    result: str = Query(None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """내 투찰 결과 목록 조회"""
    q = db.query(ActualBidOutcome).filter(ActualBidOutcome.user_id == user.id)
    if result:
        q = q.filter(ActualBidOutcome.result == result.upper())
    rows = q.order_by(ActualBidOutcome.created_at.desc()).limit(limit).all()
    return rows


@router.get("/stats")
def outcome_stats(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """투찰 결과 통계 요약 (피드백 루프 품질 지표)"""
    from sqlalchemy import func
    from ...models import ActualBidOutcome

    total = db.query(func.count(ActualBidOutcome.id)).filter(
        ActualBidOutcome.user_id == user.id
    ).scalar() or 0
    wins  = db.query(func.count(ActualBidOutcome.id)).filter(
        ActualBidOutcome.user_id == user.id,
        ActualBidOutcome.result == "WON",
    ).scalar() or 0
    disq  = db.query(func.count(ActualBidOutcome.id)).filter(
        ActualBidOutcome.user_id == user.id,
        ActualBidOutcome.result == "DISQUALIFIED",
    ).scalar() or 0

    srate_mae_row = db.execute(
        __import__("sqlalchemy").text(
            "SELECT AVG(ABS(predicted_srate - actual_srate)) as mae "
            "FROM actual_bid_outcomes "
            "WHERE user_id = :uid AND predicted_srate IS NOT NULL AND actual_srate IS NOT NULL"
        ),
        {"uid": user.id},
    ).fetchone()
    srate_mae = float(srate_mae_row.mae) if srate_mae_row and srate_mae_row.mae else None

    return {
        "total":          total,
        "wins":           wins,
        "losses":         total - wins - disq,
        "disqualified":   disq,
        "win_rate":       round(wins / total, 4) if total > 0 else 0.0,
        "srate_mae":      round(srate_mae, 6) if srate_mae else None,
        "qualify_rate":   round(1.0 - disq / total, 4) if total > 0 else None,
    }

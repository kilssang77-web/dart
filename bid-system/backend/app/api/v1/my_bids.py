from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional

from ...database import get_db
from ...models import MyBidRecord, User
from ...schemas import MyBidRecordCreate, MyBidRecordUpdate, MyBidRecordOut, MyBidAnalysisResponse
from ...services import MyBidAnalysisService
from ...common.security import get_current_user

router = APIRouter(prefix="/my-bids", tags=["투찰이력"])


@router.get("", response_model=List[MyBidRecordOut])
def list_my_bids(
    result: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(MyBidRecord).filter(MyBidRecord.user_id == user.id)
    if result:
        q = q.filter(MyBidRecord.result == result)
    total = q.count()
    items = q.order_by(MyBidRecord.created_at.desc()).offset((page - 1) * size).limit(size).all()
    return items


@router.get("/analysis", response_model=MyBidAnalysisResponse)
def my_bid_analysis(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return MyBidAnalysisService(db).analyze(user.id)


@router.get("/stats")
def my_bid_stats(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = db.query(MyBidRecord).filter(MyBidRecord.user_id == user.id).all()
    total = len(rows)
    won   = sum(1 for r in rows if r.result == "won")
    lost  = sum(1 for r in rows if r.result == "lost")

    rates = [float(r.submitted_rate) for r in rows if r.submitted_rate is not None]
    rec_rates = [float(r.recommendation_rate) for r in rows if r.recommendation_rate is not None]
    winner_rates = [float(r.actual_winner_rate) for r in rows
                    if r.actual_winner_rate is not None and r.result in ("won", "lost")]

    rate_diffs = []
    for r in rows:
        if r.recommendation_rate is not None and r.submitted_rate is not None:
            rate_diffs.append(abs(float(r.submitted_rate) - float(r.recommendation_rate)))

    return {
        "total": total,
        "won": won,
        "lost": lost,
        "pending": total - won - lost,
        "win_rate": round(won / max(won + lost, 1), 4),
        "avg_submitted_rate": round(sum(rates) / len(rates), 4) if rates else None,
        "avg_recommendation_rate": round(sum(rec_rates) / len(rec_rates), 4) if rec_rates else None,
        "avg_winner_rate": round(sum(winner_rates) / len(winner_rates), 4) if winner_rates else None,
        "avg_rate_diff_from_rec": round(sum(rate_diffs) / len(rate_diffs), 4) if rate_diffs else None,
    }


@router.post("", response_model=MyBidRecordOut, status_code=201)
def create_my_bid(
    body: MyBidRecordCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rec = MyBidRecord(
        user_id=user.id,
        bid_id=body.bid_id,
        title=body.title,
        agency_name=body.agency_name,
        bid_date=body.bid_date,
        base_amount=body.base_amount or 0,
        submitted_rate=body.submitted_rate,
        recommendation_rate=body.recommendation_rate,
        note=body.note,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


@router.put("/{record_id}", response_model=MyBidRecordOut)
def update_my_bid(
    record_id: int,
    body: MyBidRecordUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rec = db.query(MyBidRecord).filter(
        MyBidRecord.id == record_id,
        MyBidRecord.user_id == user.id,
    ).first()
    if not rec:
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다.")
    if body.result is not None:
        rec.result = body.result
    if body.actual_winner_rate is not None:
        rec.actual_winner_rate = body.actual_winner_rate
    if body.note is not None:
        rec.note = body.note
    if body.submitted_rate is not None:
        rec.submitted_rate = body.submitted_rate
    db.commit()
    db.refresh(rec)
    return rec


@router.delete("/{record_id}", status_code=204)
def delete_my_bid(
    record_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rec = db.query(MyBidRecord).filter(
        MyBidRecord.id == record_id,
        MyBidRecord.user_id == user.id,
    ).first()
    if not rec:
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다.")
    db.delete(rec)
    db.commit()
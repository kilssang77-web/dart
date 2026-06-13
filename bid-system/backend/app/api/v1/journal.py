"""
투찰 저널 API — 피드백 루프 핵심 엔드포인트.

POST /journal               투찰 결정 기록 (시뮬레이션 후 확정 시)
PUT  /journal/{id}/result   개찰 결과 입력 (개찰 후)
GET  /journal               내 투찰 이력 목록
GET  /journal/stats         피드백 현황 + 모델 성능 지표
GET  /journal/pending       결과 입력 대기 목록 (오늘의 할 일)
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...database import get_db
from ...schemas import JournalCreateRequest, JournalResultRequest, JournalOut
from ...services import JournalService
from ...common.security import get_current_user

router = APIRouter(prefix="/journal", tags=["journal"])

_svc = JournalService()


@router.post("", response_model=JournalOut)
def create_journal(
    req: JournalCreateRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """투찰률 확정 후 저널 기록. pred_log_id로 AI추천과 연결."""
    return _svc.create(db, user.id, req)


@router.put("/{journal_id}/result", response_model=JournalOut)
def record_result(
    journal_id: int,
    req: JournalResultRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """개찰 결과 입력. rate_gap / srate_error 자동 계산."""
    return _svc.record_result(db, journal_id, user.id, req)


@router.get("", response_model=dict)
def list_journals(
    result: str = Query(None, description="낙찰/패찰/무효/취소/pending"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """내 투찰 저널 목록."""
    return _svc.list_journals(db, user.id, result_filter=result, page=page, size=size)


@router.get("/stats")
def journal_stats(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """피드백 루프 현황 — 낙찰률 / 사정률 MAE / 결과입력 완결률."""
    return _svc.get_stats(db, user.id)


@router.get("/pending")
def pending_results(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """결과 입력 대기 목록 — '오늘 할 일' 화면용."""
    from sqlalchemy import text
    from datetime import datetime, timedelta

    rows = db.execute(text("""
        SELECT j.id, j.bid_id, j.announcement_no,
               b.title, ag.name as agency_name, b.bid_open_date,
               j.submitted_rate, j.submitted_amount,
               j.recommended_rate, j.pred_win_prob,
               j.created_at
        FROM bid_journal j
        LEFT JOIN bids b ON b.id = j.bid_id
        LEFT JOIN agencies ag ON ag.id = b.agency_id
        WHERE j.user_id = :uid
          AND j.result IS NULL
          AND j.submitted_rate IS NOT NULL
          AND (b.bid_open_date IS NULL OR b.bid_open_date <= NOW())
        ORDER BY b.bid_open_date DESC NULLS LAST
        LIMIT 20
    """), {"uid": user.id}).fetchall()

    return {
        "count": len(rows),
        "items": [
            {
                "journal_id":      r[0],
                "bid_id":          r[1],
                "announcement_no": r[2],
                "title":           r[3],
                "agency_name":     r[4],
                "bid_open_date":   r[5].isoformat() if r[5] else None,
                "submitted_rate":  float(r[6]) if r[6] else None,
                "submitted_amount":r[7],
                "recommended_rate":float(r[8]) if r[8] else None,
                "pred_win_prob":   float(r[9]) if r[9] else None,
                "created_at":      r[10].isoformat() if r[10] else None,
            }
            for r in rows
        ],
    }

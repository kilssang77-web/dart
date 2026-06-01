from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date

from ...database import get_db
from ...models import User, Agency, Industry, Region
from ...schemas import BidCreate, BidResultCreate
from ...services import BidService, get_active_industry_ids
from ...common.security import get_current_user

router = APIRouter(prefix="/bids", tags=["입찰"])
svc = BidService()


@router.get("")
def list_bids(
    agency_id:   Optional[int]  = Query(None),
    industry_id: Optional[int]  = Query(None),
    region_id:   Optional[int]  = Query(None),
    status:      Optional[str]  = Query(None),
    date_from:   Optional[date] = Query(None),
    date_to:     Optional[date] = Query(None),
    keyword:     Optional[str]  = Query(None),
    sort_by:     str            = Query('notice_date'),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return svc.list_bids(
        db, agency_id=agency_id, industry_id=industry_id, region_id=region_id,
        status=status, date_from=date_from, date_to=date_to,
        keyword=keyword, page=page, size=size, sort_by=sort_by,
    )


@router.get("/meta")
def get_meta(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """프론트엔드 필터용 기준 데이터."""
    active_ids = get_active_industry_ids(db)
    if active_ids is None:
        industries_q = db.query(Industry).all()
    elif not active_ids:
        industries_q = []
    else:
        industries_q = db.query(Industry).filter(Industry.id.in_(active_ids)).all()
    return {
        "agencies":   [{"id": a.id, "name": a.name} for a in db.query(Agency).all()],
        "industries": [{"id": i.id, "name": i.name} for i in industries_q],
        "regions":    [{"id": r.id, "name": r.name} for r in db.query(Region).all()],
    }


@router.get("/keyword-matches")
def keyword_matches(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """활성 키워드별 매칭 공고 수 + 최근 공고 반환."""
    return svc.get_keyword_matches(db)


@router.get("/{bid_id}")
def get_bid(bid_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    result = svc.get_bid_detail(db, bid_id)
    if not result:
        raise HTTPException(status_code=404, detail="입찰 정보를 찾을 수 없습니다.")
    return result


@router.get("/{bid_id}/similar")
def similar_bids(bid_id: int, top_k: int = Query(8, ge=1, le=20),
                 db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return svc.find_similar_bids(db, bid_id, top_k)


@router.post("", status_code=201)
def create_bid(
    body: BidCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role not in ("admin", "analyst"):
        raise HTTPException(status_code=403, detail="권한이 없습니다.")
    bid = svc.create_bid(db, body)
    return {"id": bid.id, "announcement_no": bid.announcement_no}
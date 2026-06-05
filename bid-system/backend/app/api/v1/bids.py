from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date

from ...database import get_db
from ...models import User, Agency, Industry, Region, Bid
from ...schemas import BidCreate, BidResultCreate, BookmarkResponse, OpportunityScoreResponse, BidRecommendItem, JointPartnersResponse, FinalRecommendResponse
from ...services import BidService, BookmarkService, get_active_industry_ids, OpportunityScoreService, JointQualService, FinalRecommendService
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
    size: int = Query(20, ge=1, le=500),
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


@router.get("/search")
def search_bids(
    announcement_no: str = Query("", min_length=1),
    limit: int = Query(10, ge=1, le=20),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """공고번호 자동완성 검색 (경량)."""
    rows = (
        db.query(Bid, Agency.name.label("agency_name"))
        .join(Agency, Bid.agency_id == Agency.id, isouter=True)
        .filter(Bid.announcement_no.ilike(f"%{announcement_no}%"))
        .limit(limit)
        .all()
    )
    return [
        {
            "id": bid.id,
            "announcement_no": bid.announcement_no,
            "title": bid.title,
            "agency_name": agency_name,
            "base_amount": bid.base_amount,
        }
        for bid, agency_name in rows
    ]


@router.get("/keyword-matches")
def keyword_matches(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """활성 키워드별 매칭 공고 수 + 최근 공고 반환."""
    return svc.get_keyword_matches(db)


@router.get("/recommended", response_model=list[BidRecommendItem])
def recommended_bids(
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return OpportunityScoreService(db).get_top_recommended(user.id, limit)


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


@router.get("/bookmarks")
def list_bookmarks(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    svc_bm = BookmarkService(db)
    return svc_bm.list_bookmarks(user.id, page=page, size=size)


@router.post("/{bid_id}/bookmark", status_code=204)
def add_bookmark(
    bid_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    BookmarkService(db).add(bid_id=bid_id, user_id=user.id)


@router.delete("/{bid_id}/bookmark", status_code=204)
def remove_bookmark(
    bid_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    BookmarkService(db).remove(bid_id=bid_id, user_id=user.id)


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

@router.get("/{bid_id}/opportunity-score", response_model=OpportunityScoreResponse)
def opportunity_score(
    bid_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return OpportunityScoreService(db).score(bid_id, user.id)


@router.get("/{bid_id}/joint-partners", response_model=JointPartnersResponse)
def joint_partners(
    bid_id: int,
    user_track: float = Query(0, ge=0, description="귀사 보유 실적금액(원)"),
    participation_rate: float = Query(0.6, ge=0.1, le=1.0, description="귀사 참여지분율"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return JointQualService(db).find_matching_partners(bid_id, user_track, participation_rate)


@router.get("/{bid_id}/final-recommend", response_model=FinalRecommendResponse)
def final_recommend(
    bid_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """사정율통계·프리즘·예가·트렌드·개인화를 합산한 최종 투찰 사정율 종합 추천."""
    return FinalRecommendService(db).get(bid_id, user.id)

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, datetime, timezone, timedelta

from ...database import get_db
from ...models import User, Agency, Industry, Region, Bid
from ...schemas import BidCreate, BidResultCreate, BookmarkResponse, OpportunityScoreResponse, BidRecommendItem, JointPartnersResponse, JointSimRequest, JointSimResponse, FinalRecommendResponse, BestRateResponse
from ...services import BidService, BookmarkService, get_active_industry_ids, OpportunityScoreService, JointQualService, JointSimulateService, FinalRecommendService, InpoParticipantService, RivalRadarService, ActualWinZoneService, HotZoneService, BestRateService
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
    yega_method:     Optional[str]  = Query(None),
    contract_method: Optional[str]  = Query(None),
    base_amount_min: Optional[int]  = Query(None),
    base_amount_max: Optional[int]  = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return svc.list_bids(
        db, agency_id=agency_id, industry_id=industry_id, region_id=region_id,
        status=status, date_from=date_from, date_to=date_to,
        keyword=keyword, page=page, size=size, sort_by=sort_by,
        yega_method=yega_method, contract_method=contract_method,
        base_amount_min=base_amount_min, base_amount_max=base_amount_max,
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


@router.get("/upcoming-openings")
def upcoming_openings(
    days: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """개찰 임박 공고 목록 — bid_open_date 기준 D-0 ~ D+days."""
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(days=days)

    rows = (
        db.query(Bid, Agency.name.label("agency_name"), Industry.name.label("industry_name"))
        .join(Agency, Bid.agency_id == Agency.id, isouter=True)
        .join(Industry, Bid.industry_id == Industry.id, isouter=True)
        .filter(
            Bid.bid_open_date.isnot(None),
            Bid.bid_open_date >= now,
            Bid.bid_open_date <= deadline,
            Bid.status == "open",
        )
        .order_by(Bid.bid_open_date.asc())
        .limit(50)
        .all()
    )

    results = []
    for bid, agency_name, industry_name in rows:
        open_dt = bid.bid_open_date
        if open_dt.tzinfo is None:
            open_dt = open_dt.replace(tzinfo=timezone.utc)
        delta = open_dt - now
        days_left = int(delta.total_seconds() // 86400)
        hours_left = int(delta.total_seconds() % 86400 // 3600)

        if delta.total_seconds() < 0:
            urgency = "past"
        elif days_left == 0:
            urgency = "today"
        elif days_left == 1:
            urgency = "tomorrow"
        elif days_left <= 3:
            urgency = "soon"
        else:
            urgency = "normal"

        results.append({
            "id":              bid.id,
            "announcement_no": bid.announcement_no,
            "title":           bid.title,
            "agency_name":     agency_name or bid.agency_name or "",
            "industry_name":   industry_name or "",
            "base_amount":     bid.base_amount or 0,
            "bid_open_date":   bid.bid_open_date.isoformat() if bid.bid_open_date else None,
            "days_left":       days_left,
            "hours_left":      hours_left,
            "urgency":         urgency,
            "source":          bid.source or "",
        })

    return {"items": results, "total": len(results), "days": days}


@router.get("/search")
def search_bids(
    announcement_no: str = Query("", min_length=0),
    q: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=20),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """공고번호 또는 공고명 검색 (활성 공종 필터 미적용)."""
    base_q = (
        db.query(Bid, Agency.name.label("agency_name"))
        .join(Agency, Bid.agency_id == Agency.id, isouter=True)
    )
    if q:
        from sqlalchemy import or_
        base_q = base_q.filter(
            or_(Bid.title.ilike(f"%{q}%"), Bid.announcement_no.ilike(f"%{q}%"))
        )
    elif announcement_no:
        base_q = base_q.filter(Bid.announcement_no.ilike(f"%{announcement_no}%"))
    rows = base_q.limit(limit).all()
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


@router.get("/bookmarks")
def list_bookmarks(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    svc_bm = BookmarkService(db)
    return svc_bm.list_bookmarks(user.id, page=page, size=size)


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


@router.post("/{bid_id}/joint-simulate", response_model=JointSimResponse)
def joint_simulate(
    bid_id: int,
    body: JointSimRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """파트너 구성·지분율 조합으로 적격심사 통과 여부 및 최저 투찰금액 산출."""
    return JointSimulateService(db).simulate(
        bid_id,
        [p.model_dump() for p in body.partners],
    )


@router.get("/{bid_id}/final-recommend", response_model=FinalRecommendResponse)
def final_recommend(
    bid_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """사정율통계·프리즘·예가·트렌드·개인화를 합산한 최종 투찰 사정율 종합 추천."""
    return FinalRecommendService(db).get(bid_id, user.id)


@router.get("/{bid_id}/inpo-participants")
def inpo_participants(
    bid_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """inpo21c 실측 전참여자 목록 반환."""
    return InpoParticipantService().get(db, bid_id)


@router.get("/{bid_id}/rival-radar")
def rival_radar(
    bid_id: int,
    top_k: int = Query(15, ge=1, le=30),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """공고 참여 경쟁사 레이더 — 동반입찰 패턴 분석."""
    return RivalRadarService().get(db, bid_id, top_k)


@router.get("/{bid_id}/actual-win-zones")
def actual_win_zones(
    bid_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """inpo21c 실측 낙찰 구간 분포."""
    return ActualWinZoneService().get(db, bid_id)


@router.get("/{bid_id}/hot-zones")
def hot_zones(
    bid_id: int,
    period: str = Query("24M", regex="^(12M|24M|48M)$"),
    db: Session  = Depends(get_db),
    _: User      = Depends(get_current_user),
):
    """Hot Zone 분포 — inpo21c_participants.bid_rate 기반 KDE 피크 탐지 + 담합 탐지."""
    try:
        return HotZoneService().get(db, bid_id, period_type=period)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/{bid_id}/best-rate", response_model=BestRateResponse)
def best_rate(
    bid_id: int,
    period: str = Query("24M", regex="^(12M|24M|48M)$"),
    db: Session  = Depends(get_db),
    _: User      = Depends(get_current_user),
):
    """원클릭 최적 투찰율 추천 — Option D 실증 승자 분포 기반."""
    try:
        return BestRateService().get(db, bid_id, period_type=period)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/{bid_id}/yega")
def bid_yega(
    bid_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """복수예가 목록 (inpo21c_yega)."""
    from ...models import Bid as BidModel
    from sqlalchemy import text as sa_text
    bid = db.query(BidModel).filter(BidModel.id == bid_id).first()
    if not bid or not bid.announcement_no:
        return {"items": []}
    rows = db.execute(sa_text("""
        SELECT y.yega_no, y.amount, y.base_ratio, y.base_ratio_pct, y.is_selected
        FROM inpo21c_yega y
        JOIN inpo21c_bids ib ON ib.inpo21c_bid_id = y.inpo21c_bid_id
        WHERE ib.announcement_no LIKE :ano
        ORDER BY y.yega_no
    """), {"ano": bid.announcement_no + "%"}).fetchall()
    return {
        "items": [
            {
                "yega_no":       r[0],
                "amount":        r[1],
                "base_ratio":    float(r[2]) if r[2] else None,
                "base_ratio_pct":float(r[3]) if r[3] else None,
                "is_selected":   bool(r[4]),
            }
            for r in rows
        ]
    }


@router.get("/{bid_id}/prism-histogram")
def prism_histogram(
    bid_id: int,
    period: str = Query("24M", regex="^(12M|24M|48M)$"),
    db: Session  = Depends(get_db),
    _: User      = Depends(get_current_user),
):
    """
    발주처 사정율 빈도 히스토그램 + TOP 낙찰 구간 + A값 + 실제 투찰금액 계산.

    - histogram: 0.001 단위 빈도 분포 (count / win_count / win_rate)
    - top_zones: 낙찰 확률 가중 상위 10개 구간
    - a_ratio  : 발주처 예정가/기초금액 비율
    - bid_prices: top_zones별 실제 투찰금액 (원)
    """
    from ...ml.assessment import get_prism_zones
    from ...ml.a_value import calc_bid_price

    bid = db.query(Bid).filter(Bid.id == bid_id).first()
    if not bid:
        raise HTTPException(404, "공고를 찾을 수 없습니다")

    result = get_prism_zones(db, bid.agency_id, period_type=period)
    a_ratio = result["a_ratio"]
    base_amount = bid.base_amount or 0

    # top_zones에 실제 투찰금액 계산 추가
    for z in result["top_zones"]:
        z["bid_price"] = calc_bid_price(base_amount, z["srate"], a_ratio) if base_amount > 0 else None

    result["base_amount"]    = base_amount
    result["bid_id"]         = bid_id
    result["agency_id"]      = bid.agency_id
    return result

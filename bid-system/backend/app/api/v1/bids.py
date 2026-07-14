from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, datetime, timezone, timedelta

from ...database import get_db
from ...models import User, Agency, Industry, Region, Bid
from ...schemas import BidCreate, BidResultCreate, BookmarkResponse, OpportunityScoreResponse, BidRecommendItem, JointPartnersResponse, JointSimRequest, JointSimResponse, FinalRecommendResponse, BestRateResponse
from ...services import BidService, BookmarkService, get_active_industry_ids, OpportunityScoreService, JointQualService, JointSimulateService, FinalRecommendService, InpoParticipantService, RivalRadarService, ActualWinZoneService, HotZoneService, BestRateService
from ...common.security import get_current_user
from ...common.cache import get_redis, cache_get, cache_set

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
    """프론트엔드 필터용 기준 데이터 — Redis 600초 캐시."""
    from ...common import agency_cache as _ac
    from sqlalchemy import text as _t

    from ...common.cache import local_cache_get, local_cache_set
    rc = get_redis()
    cached = cache_get(rc, "bids:meta") or local_cache_get("bids:meta")
    if cached is not None:
        return cached

    # agencies: startup 로드된 인메모리 캐시 사용 (ORM 17883행 제거)
    ac = _ac.get_all()
    if ac:
        agencies = [{"id": k, "name": v} for k, v in sorted(ac.items(), key=lambda x: x[1])]
    else:
        agencies = [{"id": r[0], "name": r[1]}
                    for r in db.execute(_t("SELECT id, name FROM agencies ORDER BY name")).fetchall()]

    active_ids = get_active_industry_ids(db)
    if active_ids is None:
        industries_q = db.execute(_t("SELECT id, name FROM industries ORDER BY name")).fetchall()
        industries = [{"id": r[0], "name": r[1]} for r in industries_q]
    elif not active_ids:
        industries = []
    else:
        industries_q = db.execute(
            _t("SELECT id, name FROM industries WHERE id = ANY(:ids) ORDER BY name"),
            {"ids": list(active_ids)}
        ).fetchall()
        industries = [{"id": r[0], "name": r[1]} for r in industries_q]

    regions = [{"id": r[0], "name": r[1]}
               for r in db.execute(_t("SELECT id, name FROM regions ORDER BY name")).fetchall()]

    result = {"agencies": agencies, "industries": industries, "regions": regions}
    cache_set(rc, "bids:meta", result, ttl=600)
    local_cache_set("bids:meta", result, ttl=600)
    return result


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
    """AI 추천 — 사용자별 Redis 120초 캐시."""
    rc = get_redis()
    cache_key = f"bids:recommended:{user.id}:{limit}"
    cached = cache_get(rc, cache_key)
    if cached is not None:
        return cached
    result = OpportunityScoreService(db).get_top_recommended(user.id, limit)
    serializable = [item.model_dump() if hasattr(item, "model_dump") else item for item in result]
    cache_set(rc, cache_key, serializable, ttl=120)
    return result


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


@router.get("/{bid_id}/participant-stats")
def participant_stats(
    bid_id: int,
    db: Session = Depends(get_db),
    _: User     = Depends(get_current_user),
):
    """
    참여자 수 예측 — inpo21c 실증 데이터 기반.

    - current_count   : G2B에서 수집된 현재 참여자수 (개찰 전 0, 개찰 후 실측)
    - expected        : inpo21c 동일기관 역사 기반 예상 참여자수 통계
    - competition_level: LOW / MEDIUM / HIGH (예상 경쟁 강도)
    - is_accepting    : 현재 접수 중 여부
    """
    from sqlalchemy import text

    bid = db.query(Bid).filter(Bid.id == bid_id).first()
    if not bid:
        raise HTTPException(404, "공고를 찾을 수 없습니다")

    now = datetime.now(tz=timezone.utc)
    is_accepting = (
        bid.bid_close_date is not None and
        bid.bid_close_date.replace(tzinfo=timezone.utc) > now
    ) if bid.bid_close_date else False

    # 기관명 조회
    agency = db.query(Agency).filter(Agency.id == bid.agency_id).first() if bid.agency_id else None
    agency_name = agency.name if agency else None

    # inpo21c 동일 기관 참여자수 분포 (복수예가 공사만)
    inpo_stats = None
    if agency_name:
        row = db.execute(text("""
            SELECT
                COUNT(DISTINCT ib.inpo21c_bid_id) AS n_bids,
                ROUND(AVG(pc.n)::numeric, 1)       AS avg_n,
                PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY pc.n::float8) AS p25,
                PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY pc.n::float8) AS p50,
                PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY pc.n::float8) AS p75,
                MIN(pc.n) AS min_n,
                MAX(pc.n) AS max_n
            FROM inpo21c_bids ib
            JOIN (
                SELECT inpo21c_bid_id, COUNT(*) AS n
                FROM inpo21c_participants
                WHERE company_name != '유찰'
                GROUP BY inpo21c_bid_id
                HAVING COUNT(*) >= 2
            ) pc ON pc.inpo21c_bid_id = ib.inpo21c_bid_id
            WHERE (
                TRIM(ib.agency_name) = TRIM(:aname)
                OR TRIM(ib.agency_name) LIKE '%' || TRIM(:aname) || '%'
                OR TRIM(:aname) LIKE '%' || TRIM(ib.agency_name) || '%'
            )
            AND ib.yega_ratio BETWEEN 87 AND 105
        """), {"aname": agency_name}).fetchone()

        if row and row[0] and int(row[0]) >= 3:
            inpo_stats = {
                "n_bids": int(row[0]),
                "avg":    float(row[1]) if row[1] else None,
                "p25":    float(row[2]) if row[2] else None,
                "p50":    float(row[3]) if row[3] else None,
                "p75":    float(row[4]) if row[4] else None,
                "min":    int(row[5]) if row[5] else None,
                "max":    int(row[6]) if row[6] else None,
            }

    # 전국 평균 (fallback)
    global_row = db.execute(text("""
        SELECT ROUND(AVG(pc.n)::numeric, 1),
               PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY pc.n::float8)
        FROM (
            SELECT inpo21c_bid_id, COUNT(*) AS n
            FROM inpo21c_participants
            WHERE company_name != '유찰'
            GROUP BY inpo21c_bid_id
            HAVING COUNT(*) BETWEEN 2 AND 100
        ) pc
        JOIN inpo21c_bids ib ON ib.inpo21c_bid_id = pc.inpo21c_bid_id
        WHERE ib.yega_ratio BETWEEN 87 AND 105
    """)).fetchone()
    global_avg = float(global_row[0]) if global_row and global_row[0] else 15.0
    global_median = float(global_row[1]) if global_row and global_row[1] else 12.0

    expected_median = (inpo_stats["p50"] if inpo_stats and inpo_stats["p50"] else global_median)

    # 경쟁 강도 분류
    if expected_median <= 10:
        level = "LOW"
        level_label = "낮음 (소수 경쟁)"
    elif expected_median <= 30:
        level = "MEDIUM"
        level_label = "보통"
    else:
        level = "HIGH"
        level_label = "높음 (다수 경쟁)"

    return {
        "bid_id":           bid_id,
        "is_accepting":     is_accepting,
        "current_count":    int(bid.participant_count) if bid.participant_count else 0,
        "current_label":    "개찰 완료" if not is_accepting and bid.participant_count else ("접수 중" if is_accepting else "집계 전"),
        "inpo_stats":       inpo_stats,
        "global_avg":       global_avg,
        "expected_median":  expected_median,
        "competition_level":level,
        "competition_label":level_label,
        "data_source":      "inpo21c_agency" if inpo_stats else "inpo21c_global",
        "agency_name":      agency_name,
    }


@router.get("/{bid_id}/similar-wins")
def similar_wins(
    bid_id: int,
    limit: int = Query(8, ge=3, le=20),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    유사 공고 실제 낙찰 이력.
    같은 기관+공종, ±60% 금액 범위, 실제 낙찰자 데이터 포함 공고 반환.
    info21c 대체 핵심 기능 — 실전 낙찰율 직접 표시.
    """
    from sqlalchemy import text

    bid = db.query(Bid).filter(Bid.id == bid_id).first()
    if not bid:
        raise HTTPException(404, "공고를 찾을 수 없습니다")

    base_amount = bid.base_amount or 0
    lower = max(1, int(base_amount * 0.4))
    upper = int(base_amount * 2.5)

    rows = db.execute(text("""
        WITH winners AS (
            SELECT br.bid_id,
                   br.bid_rate   AS winner_rate,
                   br.assessment_rate
            FROM bid_results br
            WHERE br.is_winner = true
        ),
        participant_counts AS (
            SELECT bid_id, COUNT(*) AS n_bidders
            FROM bid_results
            GROUP BY bid_id
        )
        SELECT
            b.id,
            b.title,
            b.base_amount,
            b.bid_open_date,
            b.announcement_no,
            a.name  AS agency_name,
            i.name  AS industry_name,
            w.winner_rate,
            w.assessment_rate,
            COALESCE(pc.n_bidders, 0) AS n_bidders
        FROM bids b
        LEFT JOIN agencies a ON a.id = b.agency_id
        LEFT JOIN industries i ON i.id = b.industry_id
        INNER JOIN winners w ON w.bid_id = b.id
        LEFT JOIN participant_counts pc ON pc.bid_id = b.id
        WHERE b.id != :bid_id
          AND b.agency_id = :agency_id
          AND b.industry_id = :industry_id
          AND b.base_amount BETWEEN :lower AND :upper
        ORDER BY b.bid_open_date DESC NULLS LAST
        LIMIT :lim
    """), {
        "bid_id":     bid_id,
        "agency_id":  bid.agency_id,
        "industry_id": bid.industry_id,
        "lower":      lower,
        "upper":      upper,
        "lim":        limit,
    }).fetchall()

    # 기관+공종 결과 부족 시 기관만으로 fallback
    if len(rows) < 3 and bid.agency_id:
        rows = db.execute(text("""
            WITH winners AS (
                SELECT br.bid_id, br.bid_rate AS winner_rate, br.assessment_rate
                FROM bid_results br WHERE br.is_winner = true
            ),
            participant_counts AS (
                SELECT bid_id, COUNT(*) AS n_bidders FROM bid_results GROUP BY bid_id
            )
            SELECT b.id, b.title, b.base_amount, b.bid_open_date, b.announcement_no,
                   a.name AS agency_name, i.name AS industry_name,
                   w.winner_rate, w.assessment_rate, COALESCE(pc.n_bidders, 0)
            FROM bids b
            LEFT JOIN agencies a ON a.id = b.agency_id
            LEFT JOIN industries i ON i.id = b.industry_id
            INNER JOIN winners w ON w.bid_id = b.id
            LEFT JOIN participant_counts pc ON pc.bid_id = b.id
            WHERE b.id != :bid_id
              AND b.agency_id = :agency_id
              AND b.base_amount BETWEEN :lower AND :upper
            ORDER BY b.bid_open_date DESC NULLS LAST
            LIMIT :lim
        """), {
            "bid_id": bid_id, "agency_id": bid.agency_id,
            "lower": lower, "upper": upper, "lim": limit,
        }).fetchall()

    items = [
        {
            "bid_id":         int(r[0]),
            "title":          r[1],
            "base_amount":    int(r[2]) if r[2] else 0,
            "bid_open_date":  r[3].isoformat() if r[3] else None,
            "announcement_no": r[4],
            "agency_name":    r[5] or "",
            "industry_name":  r[6] or "",
            "winner_rate":    float(r[7]) if r[7] else None,
            "assessment_rate": float(r[8]) if r[8] else None,
            "n_bidders":      int(r[9]),
        }
        for r in rows
    ]

    winner_rates = [x["winner_rate"] for x in items if x["winner_rate"]]
    return {
        "bid_id":  bid_id,
        "items":   items,
        "summary": {
            "count":           len(items),
            "avg_winner_rate": round(sum(winner_rates) / len(winner_rates), 4) if winner_rates else None,
            "min_winner_rate": round(min(winner_rates), 4) if winner_rates else None,
            "max_winner_rate": round(max(winner_rates), 4) if winner_rates else None,
            "agency_match":    bid.agency_id is not None,
            "industry_match":  bid.industry_id is not None,
        },
    }


@router.get("/{bid_id}/inline-decision")
def inline_decision(
    bid_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    추천 카드 인라인 의사결정 — GO/NO-GO + 추천금액 + 유사낙찰이력을 단일 호출로 반환.
    TodayPage 카드 확장 패널 전용.
    """
    from ...decision_service import DecisionService
    from sqlalchemy import text

    # ── 빠른 의사결정 ──────────────────────────────────────────
    qd = DecisionService().get_quick_decision(db, bid_id, user_id=user.id)
    if not qd:
        raise HTTPException(404, "공고를 찾을 수 없습니다")

    bid = db.query(Bid).filter(Bid.id == bid_id).first()
    base_amount = bid.base_amount or 0

    # ── 유사 낙찰 이력 (최근 5건) ──────────────────────────────
    lower = max(1, int(base_amount * 0.4))
    upper = int(base_amount * 2.5)

    sim_rows = db.execute(text("""
        WITH winners AS (
            SELECT br.bid_id, br.bid_rate AS winner_rate
            FROM bid_results br WHERE br.is_winner = true
        )
        SELECT b.title, b.base_amount, b.bid_open_date, w.winner_rate,
               a.name AS agency_name
        FROM bids b
        INNER JOIN winners w ON w.bid_id = b.id
        LEFT JOIN agencies a ON a.id = b.agency_id
        WHERE b.id != :bid_id
          AND b.agency_id = :agency_id
          AND b.base_amount BETWEEN :lower AND :upper
        ORDER BY b.bid_open_date DESC NULLS LAST
        LIMIT 5
    """), {
        "bid_id": bid_id, "agency_id": bid.agency_id,
        "lower": lower, "upper": upper,
    }).fetchall()

    similar_wins = [
        {
            "title":        r[0],
            "base_amount":  int(r[1]) if r[1] else 0,
            "date":         r[2].strftime("%Y-%m-%d") if r[2] else None,
            "winner_rate":  float(r[3]) if r[3] else None,
            "agency_name":  r[4] or "",
        }
        for r in sim_rows
    ]

    winner_rates = [x["winner_rate"] for x in similar_wins if x["winner_rate"]]
    avg_winner_rate = round(sum(winner_rates) / len(winner_rates), 4) if winner_rates else None

    return {
        **qd,
        "similar_wins":      similar_wins,
        "avg_winner_rate":   avg_winner_rate,
        "similar_wins_count": len(similar_wins),
    }

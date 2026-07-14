"""사전규격 공고 API — Phase 2 (HrcspSsstndrdInfoService 수집 데이터)"""
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text

from ...database import get_db
from ...models import User
from ...common.security import get_current_user

router = APIRouter(prefix="/pre-spec", tags=["사전규격"])


@router.get("/list")
def list_pre_spec(
    order_agency: Optional[str] = Query(None, description="발주기관명 필터"),
    industry: Optional[str] = Query(None, description="업종명 필터"),
    days_back: int = Query(30, description="최근 N일 이내"),
    matched_only: bool = Query(False, description="공고 매핑된 건만"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """사전규격 목록 조회 — 필터·페이지네이션 지원."""
    conditions = ["ps.reg_date >= NOW() - (:days * INTERVAL '1 day')"]
    params: dict = {"days": days_back, "offset": (page - 1) * size, "limit": size}

    if order_agency:
        conditions.append("ps.order_agency ILIKE :agency")
        params["agency"] = f"%{order_agency}%"
    if industry:
        conditions.append("ps.industry_name ILIKE :industry")
        params["industry"] = f"%{industry}%"
    if matched_only:
        conditions.append("ps.bid_id IS NOT NULL")

    where = " AND ".join(conditions)
    rows = db.execute(text(f"""
        SELECT
            ps.id, ps.pre_spec_no, ps.title, ps.order_agency, ps.demand_agency,
            ps.estimated_amount, ps.industry_name,
            ps.reg_date, ps.end_date,
            ps.bid_announcement_no, ps.bid_id, ps.matched_at,
            b.title AS bid_title, b.bid_open_date
        FROM pre_spec_notices ps
        LEFT JOIN bids b ON b.id = ps.bid_id
        WHERE {where}
        ORDER BY ps.reg_date DESC
        LIMIT :limit OFFSET :offset
    """), params).fetchall()

    total = db.execute(text(f"""
        SELECT COUNT(*) FROM pre_spec_notices ps WHERE {where}
    """), params).scalar() or 0

    items = []
    for r in rows:
        items.append({
            "id": r[0],
            "pre_spec_no": r[1],
            "title": r[2],
            "order_agency": r[3],
            "demand_agency": r[4],
            "estimated_amount": r[5],
            "industry_name": r[6],
            "reg_date": r[7].isoformat() if r[7] else None,
            "end_date": r[8].isoformat() if r[8] else None,
            "bid_announcement_no": r[9],
            "bid_id": r[10],
            "matched_at": r[11].isoformat() if r[11] else None,
            "bid_title": r[12],
            "bid_open_date": r[13].isoformat() if r[13] else None,
            "is_matched": r[10] is not None,
        })

    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/summary")
def pre_spec_summary(
    days_back: int = Query(30),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """사전규격 요약 통계."""
    row = db.execute(text("""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE bid_id IS NOT NULL) AS matched,
            COUNT(DISTINCT order_agency) AS agencies,
            SUM(estimated_amount) FILTER (WHERE estimated_amount > 0) AS total_amount
        FROM pre_spec_notices
        WHERE reg_date >= NOW() - (:days * INTERVAL '1 day')
    """), {"days": days_back}).fetchone()

    return {
        "total": row[0] if row else 0,
        "matched": row[1] if row else 0,
        "agencies": row[2] if row else 0,
        "total_amount": row[3] if row else 0,
        "days_back": days_back,
    }


@router.get("/predictions")
def pre_spec_predictions(
    days_back: int = Query(60, description="최근 N일 이내 사전규격 대상"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """사전규격 → 입찰공고 전환 예측.

    이력에서 전환율·전환 소요일을 계산하고, 미매핑 사전규격에 대해
    예상 공고 날짜와 전환 확률을 반환한다.
    urgency: imminent (≤3일) / upcoming (3-14일) / future (>14일) / overdue (지남)
    """
    # 1) 글로벌 + 기관별 전환 통계
    stats_rows = db.execute(text("""
        WITH matched AS (
            SELECT
                order_agency,
                EXTRACT(EPOCH FROM (matched_at - end_date))/86400.0 AS gap_days
            FROM pre_spec_notices
            WHERE bid_id IS NOT NULL AND matched_at IS NOT NULL AND end_date IS NOT NULL
        ),
        global_stats AS (
            SELECT
                NULL::text       AS order_agency,
                AVG(gap_days)    AS avg_gap,
                COUNT(*)         AS matched_n
            FROM matched
        ),
        agency_stats AS (
            SELECT
                order_agency,
                AVG(gap_days)    AS avg_gap,
                COUNT(*)         AS matched_n
            FROM matched
            GROUP BY order_agency
            HAVING COUNT(*) >= 2
        ),
        agency_totals AS (
            SELECT order_agency, COUNT(*) AS total_n
            FROM pre_spec_notices
            GROUP BY order_agency
        )
        SELECT
            COALESCE(a.order_agency, 'GLOBAL')   AS agency,
            a.avg_gap,
            a.matched_n,
            COALESCE(t.total_n, a.matched_n)     AS total_n
        FROM agency_stats a
        LEFT JOIN agency_totals t ON t.order_agency = a.order_agency
        UNION ALL
        SELECT 'GLOBAL', g.avg_gap, g.matched_n,
               (SELECT COUNT(*) FROM pre_spec_notices) AS total_n
        FROM global_stats g
    """)).fetchall()

    global_avg_gap = 0.0
    global_conv_rate = 0.4
    agency_gap: dict[str, float] = {}
    agency_rate: dict[str, float] = {}

    for row in stats_rows:
        agency, avg_gap, matched_n, total_n = row[0], row[1], row[2], row[3]
        conv_rate = float(matched_n) / float(total_n) if total_n else 0.4
        if agency == "GLOBAL":
            global_avg_gap = float(avg_gap or 0)
            global_conv_rate = conv_rate
        else:
            agency_gap[agency] = float(avg_gap or 0)
            agency_rate[agency] = conv_rate

    # 2) 미매핑 사전규격 목록
    unmatched = db.execute(text("""
        SELECT
            id, pre_spec_no, title, order_agency, demand_agency,
            estimated_amount, industry_name, reg_date, end_date
        FROM pre_spec_notices
        WHERE bid_id IS NULL
          AND reg_date >= NOW() - INTERVAL ':days days'
        ORDER BY end_date ASC NULLS LAST
    """.replace(":days days", f"{int(days_back)} days"))).fetchall()

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    predictions = []
    for row in unmatched:
        pid, pre_spec_no, title, agency, demand, est_amount, industry, reg_date, end_date = row

        gap = agency_gap.get(agency, global_avg_gap)
        conv_prob = agency_rate.get(agency, global_conv_rate)
        source = "agency" if agency in agency_gap else "global"

        if end_date:
            from datetime import timedelta
            ed = end_date if end_date.tzinfo else end_date.replace(tzinfo=timezone.utc)
            est_bid_dt = ed + timedelta(days=gap)
            days_to_bid = (est_bid_dt - now).total_seconds() / 86400
            if days_to_bid < 0:
                urgency = "overdue"
            elif days_to_bid <= 3:
                urgency = "imminent"
            elif days_to_bid <= 14:
                urgency = "upcoming"
            else:
                urgency = "future"
        else:
            est_bid_dt = None
            days_to_bid = None
            urgency = "unknown"

        predictions.append({
            "id": pid,
            "pre_spec_no": pre_spec_no,
            "title": title,
            "order_agency": agency,
            "demand_agency": demand,
            "estimated_amount": est_amount,
            "industry_name": industry,
            "reg_date": reg_date.isoformat() if reg_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "est_bid_date": est_bid_dt.isoformat() if est_bid_dt else None,
            "days_to_bid": round(days_to_bid, 1) if days_to_bid is not None else None,
            "conv_prob": round(conv_prob, 3),
            "conv_stats_source": source,
            "urgency": urgency,
        })

    # urgency 순서: imminent > upcoming > future > overdue > unknown
    _urgency_order = {"imminent": 0, "upcoming": 1, "future": 2, "overdue": 3, "unknown": 4}
    predictions.sort(key=lambda x: (_urgency_order.get(x["urgency"], 4), x["days_to_bid"] or 9999))

    return {
        "predictions": predictions,
        "stats": {
            "global_avg_gap_days": round(global_avg_gap, 1),
            "global_conv_rate": round(global_conv_rate, 3),
            "agency_count": len(agency_gap),
        },
    }


@router.post("/collect", status_code=202)
def trigger_collect(
    background_tasks: BackgroundTasks,
    days_back: int = Query(7, description="수집 일수"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """사전규격 수동 수집 트리거 (admin 전용)."""
    if current_user.role != "admin":
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="관리자 전용")

    def _collect():
        from app.database import SessionLocal
        from app.collector.service import collect_pre_spec_notices
        _db = SessionLocal()
        try:
            collect_pre_spec_notices(_db, days_back=days_back)
        finally:
            _db.close()

    background_tasks.add_task(_collect)
    return {"message": f"사전규격 수집 시작 (최근 {days_back}일)"}

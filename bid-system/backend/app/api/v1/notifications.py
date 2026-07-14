from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import User
from ...schemas import NotificationListResponse, NotificationOut
from ...services import NotificationService
from ...common.security import get_current_user

router = APIRouter(prefix="/notifications", tags=["알림"])


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    svc = NotificationService(db)
    return NotificationListResponse(
        items=svc.list_for_user(current.id, unread_only=unread_only, limit=limit),
        unread_count=svc.unread_count(current.id),
    )


@router.get("/unread-count")
def unread_count(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return {"count": NotificationService(db).unread_count(current.id)}


@router.post("/{notification_id}/read", status_code=204)
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    NotificationService(db).mark_read(notification_id, current.id)


@router.post("/read-all", status_code=204)
def mark_all_read(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    NotificationService(db).mark_all_read(current.id)


@router.get("/intel")
def intelligence_alerts(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """
    조기경보 인텔리전스 알림.
    - 경쟁사 최근 3회 연속 낙찰 감지
    - 기관별 사정율 최근 2주 급변 (±2%p)
    - 오늘/내일 개찰 중 AI추천 미입력 공고
    """
    alerts = []

    # 1. 경쟁사 연속 낙찰 감지 (최근 30일, 동일 기관 3연속 이상)
    streak_rows = db.execute(text("""
        WITH ranked AS (
            SELECT
                c.name  AS competitor_name,
                a.name  AS agency_name,
                br.created_at,
                ROW_NUMBER() OVER (PARTITION BY br.competitor_id, bi.agency_id ORDER BY bi.bid_open_date DESC) AS rn
            FROM bid_results br
            JOIN bids bi ON bi.id = br.bid_id
            JOIN competitors c ON c.id = br.competitor_id
            JOIN agencies a ON a.id = bi.agency_id
            WHERE br.is_winner = TRUE
              AND bi.bid_open_date >= NOW() - INTERVAL '30 days'
        )
        SELECT competitor_name, agency_name, COUNT(*) AS streak
        FROM ranked
        WHERE rn <= 5
        GROUP BY competitor_name, agency_name
        HAVING COUNT(*) >= 3
        ORDER BY streak DESC
        LIMIT 5
    """)).fetchall()

    for r in streak_rows:
        alerts.append({
            "type":     "competitor_streak",
            "level":    "warn",
            "title":    f"경쟁사 {r[0]} — {r[1]}에서 {r[2]}연속 낙찰",
            "body":     f"최근 30일 내 {r[1]} 기관 공고에서 {r[0]}이 {r[2]}회 연속 낙찰했습니다. 해당 기관 투찰 시 경쟁사 투찰 구간을 재확인하세요.",
            "agency":   r[1],
            "competitor": r[0],
            "streak":   int(r[2]),
        })

    # 2. 기관별 사정율 급변 감지 (최근 2주 vs 이전 2주 평균 차이 ±2%p)
    srate_spike_rows = db.execute(text("""
        WITH recent AS (
            SELECT bi.agency_id, a.name AS agency_name,
                   AVG(br_w.bid_rate) AS recent_avg
            FROM bid_results br_w
            JOIN bids bi ON bi.id = br_w.bid_id
            JOIN agencies a ON a.id = bi.agency_id
            WHERE br_w.is_winner = TRUE
              AND bi.bid_open_date >= NOW() - INTERVAL '14 days'
            GROUP BY bi.agency_id, a.name
            HAVING COUNT(*) >= 2
        ),
        prior AS (
            SELECT bi.agency_id,
                   AVG(br_w.bid_rate) AS prior_avg
            FROM bid_results br_w
            JOIN bids bi ON bi.id = br_w.bid_id
            WHERE br_w.is_winner = TRUE
              AND bi.bid_open_date BETWEEN NOW() - INTERVAL '28 days' AND NOW() - INTERVAL '14 days'
            GROUP BY bi.agency_id
            HAVING COUNT(*) >= 2
        )
        SELECT r.agency_name, r.recent_avg, p.prior_avg,
               ABS(r.recent_avg - p.prior_avg) AS delta
        FROM recent r
        JOIN prior p ON p.agency_id = r.agency_id
        WHERE ABS(r.recent_avg - p.prior_avg) >= 0.02
        ORDER BY delta DESC
        LIMIT 5
    """)).fetchall()

    for r in srate_spike_rows:
        direction = "상승" if float(r[1]) > float(r[2]) else "하락"
        alerts.append({
            "type":     "srate_spike",
            "level":    "warn",
            "title":    f"{r[0]} 낙찰률 {direction} — {abs(float(r[3]) * 100):.1f}%p 변동",
            "body":     f"최근 2주 낙찰률 {float(r[1]) * 100:.2f}% vs 이전 2주 {float(r[2]) * 100:.2f}%. 사정율 예측 재확인 권장.",
            "agency":   r[0],
            "recent":   round(float(r[1]), 4),
            "prior":    round(float(r[2]), 4),
            "delta":    round(float(r[3]), 4),
        })

    # 3. 오늘·내일 개찰 중 아직 투찰 결과 미입력 공고
    pending_open_rows = db.execute(text("""
        SELECT be.id, be.title, a.name AS agency_name, be.bid_open_date, be.status
        FROM bid_executions be
        LEFT JOIN bids bi ON bi.id = be.bid_id
        LEFT JOIN agencies a ON a.id = bi.agency_id
        WHERE be.user_id = :uid
          AND be.status IN ('투찰완료', '개찰대기')
          AND be.bid_open_date BETWEEN NOW() - INTERVAL '1 hour' AND NOW() + INTERVAL '48 hours'
        ORDER BY be.bid_open_date
        LIMIT 10
    """), {"uid": current.id}).fetchall()

    if pending_open_rows:
        for r in pending_open_rows:
            alerts.append({
                "type":   "pending_open",
                "level":  "info",
                "title":  f"개찰 임박 — {r[1]}",
                "body":   f"{r[2] or ''} | 개찰 예정: {r[3].strftime('%m/%d %H:%M') if r[3] else '?'}. 개찰 후 결과를 입력해주세요.",
                "exec_id": int(r[0]),
                "open_date": r[3].isoformat() if r[3] else None,
            })

    return {
        "total": len(alerts),
        "alerts": alerts,
    }

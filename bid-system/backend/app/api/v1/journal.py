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
from ...schemas import JournalCreateRequest, JournalResultRequest, JournalOut, ManualJournalRequest
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


@router.post("/manual", response_model=JournalOut)
def create_manual_journal(
    req: ManualJournalRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """시스템 외부 투찰 건 수동 등록. 공고번호 + 투찰률 + 결과를 한 번에 기록."""
    return _svc.create_manual(db, user.id, req)


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


@router.get("/gap-analysis")
def gap_analysis(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """투찰 패턴 분석 — 우리 투찰률 vs 낙찰자 거리 분포 + 월별 추세"""
    from sqlalchemy import text

    # 전체 요약
    summary = db.execute(text("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN result='낙찰' THEN 1 END) as wins,
            ROUND(AVG(ABS(winner_rate - submitted_rate)::numeric) * 100, 3) as avg_abs_gap,
            ROUND(AVG((winner_rate - submitted_rate)::numeric) * 100, 3) as avg_signed_gap,
            COUNT(CASE WHEN ABS(winner_rate - submitted_rate) <= 0.005 THEN 1 END) as within_0_5pct,
            COUNT(CASE WHEN ABS(winner_rate - submitted_rate) <= 0.01 THEN 1 END) as within_1pct,
            COUNT(CASE WHEN ABS(winner_rate - submitted_rate) <= 0.02 THEN 1 END) as within_2pct
        FROM bid_journal
        WHERE winner_rate IS NOT NULL AND submitted_rate IS NOT NULL
          AND user_id = :uid
    """), {"uid": user.id}).fetchone()

    # 월별 추세 (최근 12개월)
    monthly = db.execute(text("""
        SELECT
            TO_CHAR(submitted_at, 'YYYY-MM') as month,
            COUNT(*) as total,
            COUNT(CASE WHEN result='낙찰' THEN 1 END) as wins,
            ROUND(AVG(ABS(winner_rate - submitted_rate)::numeric) * 100, 3) as avg_gap
        FROM bid_journal
        WHERE winner_rate IS NOT NULL AND submitted_rate IS NOT NULL
          AND submitted_at IS NOT NULL AND user_id = :uid
          AND submitted_at >= NOW() - INTERVAL '12 months'
        GROUP BY 1
        ORDER BY 1
    """), {"uid": user.id}).fetchall()

    # gap 분포 히스토그램 (0~20%, 1% 버킷)
    hist = db.execute(text("""
        SELECT
            LEAST(FLOOR(ABS(winner_rate - submitted_rate) * 100)::int, 19) as bucket,
            COUNT(*) as cnt
        FROM bid_journal
        WHERE winner_rate IS NOT NULL AND submitted_rate IS NOT NULL
          AND user_id = :uid
        GROUP BY 1
        ORDER BY 1
    """), {"uid": user.id}).fetchall()

    hist_dict = {int(r[0]): int(r[1]) for r in hist}
    histogram = [{"bucket_pct": i, "count": hist_dict.get(i, 0)} for i in range(20)]

    # 전략별 성과
    by_strategy = db.execute(text("""
        SELECT
            COALESCE(strategy_chosen, 'unknown') as strategy,
            COUNT(*) as total,
            COUNT(CASE WHEN result='낙찰' THEN 1 END) as wins,
            ROUND(AVG(ABS(winner_rate - submitted_rate)::numeric) * 100, 3) as avg_gap
        FROM bid_journal
        WHERE submitted_rate IS NOT NULL AND user_id = :uid
        GROUP BY 1
        ORDER BY 3 DESC
    """), {"uid": user.id}).fetchall()

    total = int(summary[0]) if summary[0] else 0
    wins = int(summary[1]) if summary[1] else 0

    return {
        "summary": {
            "total": total,
            "wins": wins,
            "win_rate": round(wins / total, 4) if total > 0 else 0,
            "avg_abs_gap_pct": float(summary[2]) if summary[2] else None,
            "avg_signed_gap_pct": float(summary[3]) if summary[3] else None,
            "within_0_5pct": int(summary[4]) if summary[4] else 0,
            "within_1pct": int(summary[5]) if summary[5] else 0,
            "within_2pct": int(summary[6]) if summary[6] else 0,
        },
        "monthly": [
            {"month": r[0], "total": int(r[1]), "wins": int(r[2]), "avg_gap": float(r[3]) if r[3] else None}
            for r in monthly
        ],
        "histogram": histogram,
        "by_strategy": [
            {"strategy": r[0], "total": int(r[1]), "wins": int(r[2]), "avg_gap": float(r[3]) if r[3] else None}
            for r in by_strategy
        ],
    }


@router.get("/recommendation-effect")
def recommendation_effect(
    tolerance: float = Query(0.003, description="추천 추종 판정 허용 오차 (기본 0.3%)"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    AI 추천 추종 효과 분석.
    submitted_rate ≈ recommended_rate (±tolerance) 이면 '추종', 아니면 '이탈'.
    두 그룹의 낙찰률·평균 rate_gap을 비교한다.
    """
    from sqlalchemy import text

    rows = db.execute(text("""
        SELECT
            j.submitted_rate,
            j.recommended_rate,
            j.result,
            j.rate_gap,
            j.pred_win_prob,
            j.strategy_chosen
        FROM bid_journal j
        WHERE j.user_id = :uid
          AND j.submitted_rate IS NOT NULL
          AND j.recommended_rate IS NOT NULL
          AND j.result IS NOT NULL
    """), {"uid": user.id}).fetchall()

    followed, deviated = [], []
    for r in rows:
        diff = abs(float(r[0]) - float(r[1]))
        rec = {
            "result": r[2],
            "rate_gap": float(r[3]) if r[3] else None,
            "pred_win_prob": float(r[4]) if r[4] else None,
            "strategy": r[5],
        }
        (followed if diff <= tolerance else deviated).append(rec)

    def _stats(items):
        if not items:
            return {"n": 0, "win_rate": None, "avg_abs_gap": None, "avg_pred_win_prob": None}
        wins = sum(1 for x in items if x["result"] == "낙찰")
        gaps = [abs(x["rate_gap"]) for x in items if x["rate_gap"] is not None]
        probs = [x["pred_win_prob"] for x in items if x["pred_win_prob"] is not None]
        return {
            "n": len(items),
            "win_rate": round(wins / len(items), 4),
            "avg_abs_gap": round(sum(gaps) / len(gaps), 6) if gaps else None,
            "avg_pred_win_prob": round(sum(probs) / len(probs), 4) if probs else None,
        }

    f_stats = _stats(followed)
    d_stats = _stats(deviated)

    lift = None
    if f_stats["win_rate"] is not None and d_stats["win_rate"] is not None and d_stats["n"] > 0:
        baseline = d_stats["win_rate"] or 0.001
        lift = round((f_stats["win_rate"] - d_stats["win_rate"]) / baseline * 100, 1)

    # 전략별 분포
    by_strategy: dict = {}
    for item in followed:
        s = item["strategy"] or "unknown"
        by_strategy.setdefault(s, {"followed_n": 0, "followed_wins": 0})
        by_strategy[s]["followed_n"] += 1
        if item["result"] == "낙찰":
            by_strategy[s]["followed_wins"] += 1

    return {
        "tolerance_pct": round(tolerance * 100, 2),
        "followed": f_stats,
        "deviated": d_stats,
        "lift_pct": lift,
        "message": (
            f"추천 추종 시 낙찰률 {f_stats['win_rate']*100:.1f}% vs 이탈 시 {d_stats['win_rate']*100:.1f}% "
            f"(+{lift}% lift)" if lift is not None and f_stats["win_rate"] and d_stats["win_rate"]
            else "데이터 부족"
        ),
        "by_strategy": [
            {"strategy": k, **v, "win_rate": round(v["followed_wins"] / v["followed_n"], 4) if v["followed_n"] else None}
            for k, v in by_strategy.items()
        ],
    }


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


@router.post("/auto-register-from-inpo21c")
def auto_register_from_inpo21c(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """inpo21c 수집 데이터에서 우리 회사 참여 건을 자동으로 bid_journal에 등록."""
    from app.journal_service import auto_register_from_inpo21c as _svc_fn
    return _svc_fn(db, user.id)

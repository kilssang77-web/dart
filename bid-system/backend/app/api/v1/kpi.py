"""KPI 대시보드 API — E8 경영진 의사결정 엔진"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ...database import get_db
from ...schemas import KPIDashboardResponse
from ...services import KpiService
from .auth import get_current_user

router = APIRouter(prefix="/kpi", tags=["KPI 대시보드"])
_svc = KpiService()


@router.get("/dashboard", response_model=KPIDashboardResponse)
def get_dashboard(
    period_type: str = Query("MONTHLY", regex="^(DAILY|WEEKLY|MONTHLY)$"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    수주율 KPI 대시보드.

    수주건수 / 수주율 / 월 목표 달성률 / 적격통과율 /
    사정율 예측 MAE / 낙찰확률 캘리브레이션 오차 / 경고 메시지 반환.
    """
    return _svc.get_dashboard(db, user.id, period_type)


@router.get("/ml-health")
def ml_health(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    모델 품질 헬스체크 — 일반 사용자 접근 가능.

    반환:
      - fallback_rate: 전역 평균 사용 비율 (agency/industry 데이터 없어서 global fallback 사용)
      - mae_7d / mae_30d: 7일·30일 rolling 사정율 예측 MAE
      - ece: 낙찰확률 캘리브레이션 오차 (최근 결과 기준)
      - retrain_count_30d: 30일 내 재학습 횟수
      - last_retrain_at: 최근 재학습 시각
      - data_quality_dist: {agency, industry, global} 분포
    """
    # 1. assessment_rate_stats에서 데이터 품질 레벨 분포
    stats_rows = db.execute(text("""
        SELECT group_type, COUNT(*) AS cnt, AVG(sample_count) AS avg_samples
        FROM assessment_rate_stats
        GROUP BY group_type
    """)).fetchall()

    total_stats = sum(int(r[1]) for r in stats_rows)
    dist: dict = {"agency": 0, "industry": 0, "global": 0}
    for r in stats_rows:
        dist[r[0]] = int(r[1])

    # fallback_rate: agency 데이터 없는 비율 추정
    # agency 통계 수 / (agency 통계 수 + global fallback 예상 수)
    agency_cnt = dist.get("agency", 0)
    # 전체 수집 기관 수 (agencies 테이블)
    total_agencies_row = db.execute(text("SELECT COUNT(*) FROM agencies")).fetchone()
    total_agencies = int(total_agencies_row[0]) if total_agencies_row else 1
    fallback_rate = round(max(0.0, 1.0 - agency_cnt / max(total_agencies, 1)), 4)

    # 2. bid_journal에서 rolling MAE (7일·30일)
    mae_row = db.execute(text("""
        SELECT
          AVG(CASE WHEN created_at >= NOW() - INTERVAL '7 days'  THEN ABS(srate_error) END) AS mae_7d,
          AVG(CASE WHEN created_at >= NOW() - INTERVAL '30 days' THEN ABS(srate_error) END) AS mae_30d,
          COUNT(CASE WHEN created_at >= NOW() - INTERVAL '7 days'  AND srate_error IS NOT NULL THEN 1 END) AS n_7d,
          COUNT(CASE WHEN created_at >= NOW() - INTERVAL '30 days' AND srate_error IS NOT NULL THEN 1 END) AS n_30d
        FROM bid_journal
        WHERE srate_error IS NOT NULL
    """)).fetchone()

    mae_7d  = round(float(mae_row[0]), 4) if mae_row and mae_row[0] is not None else None
    mae_30d = round(float(mae_row[1]), 4) if mae_row and mae_row[1] is not None else None
    n_7d    = int(mae_row[2]) if mae_row else 0
    n_30d   = int(mae_row[3]) if mae_row else 0

    # 3. 낙찰확률 ECE (최근 30일)
    ece_rows = db.execute(text("""
        SELECT
          FLOOR(pred_win_prob * 10) / 10.0 AS bucket,
          COUNT(*) AS n,
          AVG(CASE WHEN result = '낙찰' THEN 1.0 ELSE 0.0 END) AS actual,
          AVG(pred_win_prob) AS avg_pred
        FROM bid_journal
        WHERE pred_win_prob IS NOT NULL
          AND result IN ('낙찰', '패찰')
          AND created_at >= NOW() - INTERVAL '30 days'
        GROUP BY bucket
    """)).fetchall()

    ece = None
    if ece_rows:
        total_n = sum(int(r[1]) for r in ece_rows)
        if total_n > 0:
            ece = round(sum((int(r[1]) / total_n) * abs(float(r[2] or 0) - float(r[3] or 0)) for r in ece_rows), 4)

    # 4. 재학습 이력 (prediction_logs_v2 기준 model_version 변경 감지)
    retrain_rows = db.execute(text("""
        SELECT model_version, MIN(created_at) AS first_seen, COUNT(*) AS cnt
        FROM prediction_logs_v2
        WHERE created_at >= NOW() - INTERVAL '30 days'
          AND model_version IS NOT NULL
        GROUP BY model_version
        ORDER BY first_seen DESC
        LIMIT 5
    """)).fetchall()

    retrain_history = [
        {"model_version": r[0], "first_seen": r[1].isoformat() if r[1] else None, "usage_count": int(r[2])}
        for r in retrain_rows
    ]
    retrain_count_30d = max(0, len(retrain_history) - 1)  # 버전 변경 횟수
    last_retrain_at = retrain_history[0]["first_seen"] if retrain_history else None

    # 5. MAE 7일 트렌드 (일별)
    trend_rows = db.execute(text("""
        SELECT
          DATE_TRUNC('day', created_at)::date AS day,
          AVG(ABS(srate_error)) AS mae,
          COUNT(*) AS n
        FROM bid_journal
        WHERE srate_error IS NOT NULL
          AND created_at >= NOW() - INTERVAL '14 days'
        GROUP BY day
        ORDER BY day
    """)).fetchall()

    mae_trend = [
        {"day": r[0].isoformat() if r[0] else None, "mae": round(float(r[1]), 4) if r[1] else None, "n": int(r[2])}
        for r in trend_rows
    ]

    # 6. 추천 준수율 요약
    rec_rows = db.execute(text("""
        SELECT
          COUNT(*) AS total,
          COUNT(CASE WHEN ABS(submitted_rate - recommended_rate) <= 0.003 THEN 1 END) AS followed,
          AVG(CASE WHEN ABS(submitted_rate - recommended_rate) <= 0.003 AND result = '낙찰' THEN 1.0
                   WHEN ABS(submitted_rate - recommended_rate) <= 0.003 AND result = '패찰' THEN 0.0 END) AS followed_win,
          AVG(CASE WHEN ABS(submitted_rate - recommended_rate) > 0.003 AND result = '낙찰' THEN 1.0
                   WHEN ABS(submitted_rate - recommended_rate) > 0.003 AND result = '패찰' THEN 0.0 END) AS deviated_win
        FROM bid_journal
        WHERE submitted_rate IS NOT NULL
          AND recommended_rate IS NOT NULL
          AND result IS NOT NULL
    """)).fetchone()

    follow_summary = None
    if rec_rows and rec_rows[0] and int(rec_rows[0]) >= 3:
        f_win = round(float(rec_rows[2]), 4) if rec_rows[2] is not None else None
        d_win = round(float(rec_rows[3]), 4) if rec_rows[3] is not None else None
        lift  = round((f_win - d_win) / max(d_win or 0.001, 0.001) * 100, 1) if (f_win and d_win) else None
        follow_summary = {
            "total":        int(rec_rows[0]),
            "followed":     int(rec_rows[1]),
            "follow_rate":  round(int(rec_rows[1]) / int(rec_rows[0]), 4) if rec_rows[0] else 0,
            "followed_win_rate": f_win,
            "deviated_win_rate": d_win,
            "lift_pct":     lift,
        }

    return {
        "fallback_rate":       fallback_rate,
        "data_quality_dist":   dist,
        "total_agency_stats":  agency_cnt,
        "total_agencies":      total_agencies,
        "mae_7d":              mae_7d,
        "mae_30d":             mae_30d,
        "mae_n_7d":            n_7d,
        "mae_n_30d":           n_30d,
        "ece_30d":             ece,
        "retrain_count_30d":   retrain_count_30d,
        "last_retrain_at":     last_retrain_at,
        "retrain_history":     retrain_history,
        "mae_trend":           mae_trend,
        "follow_summary":      follow_summary,
        "interpretation": {
            "fallback": "좋음" if fallback_rate < 0.3 else "보통" if fallback_rate < 0.6 else "데이터 부족",
            "mae_7d":   "좋음" if mae_7d is not None and mae_7d < 0.005 else
                        "보통" if mae_7d is not None and mae_7d < 0.015 else
                        "개선필요" if mae_7d is not None else "데이터 없음",
        },
    }


@router.post("/snapshot")
def force_snapshot(
    period_type: str = Query("MONTHLY"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """KPI 스냅샷 강제 재계산 + 저장"""
    from datetime import date
    from ...ml.feedback import build_kpi_snapshot
    kpi = build_kpi_snapshot(db, user.id, date.today(), period_type)
    if kpi:
        kpi["user_id"]     = user.id
        kpi["period_type"] = period_type
        _svc.upsert_snapshot(db, kpi)
    return {"ok": True, "kpi": kpi}

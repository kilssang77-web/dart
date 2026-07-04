from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timezone, timedelta

from ...database import get_db
from ...models import User
from ...services import StatisticsService, SrateTrendService
from ...schemas import SrateDistributionResponse
from ...common.security import get_current_user

router = APIRouter(prefix="/stats", tags=["통계"])
svc = StatisticsService()
svc_trend = SrateTrendService()


@router.get("/overview")
def overview(
    months: int = Query(12, ge=1, le=60),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return svc.overview(db, months)


@router.get("/agencies")
def agency_stats(
    months: int = Query(12, ge=1, le=60),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return svc.agency_stats(db, months)


@router.get("/regions")
def region_stats(
    months: int = Query(12, ge=1, le=60),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return svc.region_stats(db, months)


@router.get("/industries")
def industry_stats(
    months: int = Query(12, ge=1, le=60),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return svc.industry_stats(db, months)


@router.get("/rate-distribution")
def rate_distribution(
    industry_id: Optional[int] = Query(None),
    months: int = Query(12, ge=1, le=60),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return svc.rate_distribution(db, industry_id, months)


@router.get("/heatmap")
def heatmap(
    months: int = Query(24, ge=1, le=60),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return svc.heatmap(db, months)


@router.get("/cluster")
def cluster_analysis(
    industry_id: Optional[int] = Query(None),
    months: int = Query(24, ge=3, le=60),
    k: int = Query(4, ge=2, le=8),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return svc.cluster_analysis(db, industry_id=industry_id, months=months, k=k)


@router.get("/srate-distribution")
def srate_distribution(
    agency_id:   Optional[int] = Query(None),
    industry_id: Optional[int] = Query(None),
    months: int = Query(24, ge=1, le=60),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return svc.srate_distribution_detail(db, agency_id=agency_id, industry_id=industry_id, months=months)


@router.get("/srate-trend")
def srate_trend(
    agency_id: Optional[int] = Query(None),
    industry_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return svc_trend.get_trend(db, agency_id, industry_id)


@router.get("/top-srate-trends")
def top_srate_trends(
    limit: int = Query(3, ge=1, le=10),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return svc_trend.get_top_trends(db, limit)


@router.get("/model-info")
def model_info(
    months: int = Query(12, ge=1, le=60),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return svc.model_info(db, months)


@router.get("/recommendation-compliance")
def recommendation_compliance(
    days: int = Query(90, ge=14, le=365),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    시스템 추천 이행율 & 낙찰률 비교.

    - recommended_rate IS NOT NULL → 추천 시스템이 투찰율을 제안한 건
    - |submitted_rate - recommended_rate| <= 0.003 → 추천 이행 (±0.3% 허용)
    - status IN ('낙찰','패찰') → 결과 있는 건
    - follow_win_rate vs deviate_win_rate 비교로 시스템 가치 측정
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    rows = db.execute(text("""
        SELECT
            be.id,
            be.title,
            be.agency_name,
            be.submitted_rate,
            be.recommended_rate,
            be.status,
            be.bid_open_date,
            be.winner_rate,
            be.base_amount
        FROM bid_executions be
        WHERE be.user_id = :uid
          AND be.created_at >= :since
        ORDER BY be.created_at DESC
    """), {"uid": user.id, "since": since}).fetchall()

    total = len(rows)
    with_rec = [r for r in rows if r[4] is not None]       # recommended_rate not null
    concluded = [r for r in with_rec if r[5] in ("낙찰", "패찰")]

    def _followed(r) -> bool:
        if r[3] is None or r[4] is None:
            return False
        return abs(float(r[3]) - float(r[4])) <= 0.003

    followed   = [r for r in with_rec if _followed(r)]
    deviated   = [r for r in with_rec if not _followed(r)]
    followed_concluded = [r for r in followed if r[5] in ("낙찰", "패찰")]
    deviated_concluded = [r for r in deviated if r[5] in ("낙찰", "패찰")]

    def _win_rate(lst):
        if not lst:
            return None
        wins = sum(1 for r in lst if r[5] == "낙찰")
        return round(wins / len(lst), 4)

    # 최근 미실행 공고는 여기서 추적 불가 (recommendation API 호출 로그 없음)
    # 대신 "추천율이 있는 bid_executions" 기준 분석

    recent_items = [
        {
            "id":               int(r[0]),
            "title":            r[1],
            "agency_name":      r[2],
            "submitted_rate":   float(r[3]) if r[3] else None,
            "recommended_rate": float(r[4]) if r[4] else None,
            "status":           r[5],
            "bid_open_date":    r[6].strftime("%Y-%m-%d") if r[6] else None,
            "winner_rate":      float(r[7]) if r[7] else None,
            "base_amount":      int(r[8]) if r[8] else 0,
            "followed":         _followed(r) if r[4] is not None else None,
        }
        for r in rows[:20]
    ]

    return {
        "period_days":           days,
        "total_executions":      total,
        "with_recommendation":   len(with_rec),
        "followed_count":        len(followed),
        "deviated_count":        len(deviated),
        "follow_rate":           round(len(followed) / len(with_rec), 4) if with_rec else None,
        "concluded_count":       len(concluded),
        "outcomes": {
            "followed": {
                "count":    len(followed_concluded),
                "win_rate": _win_rate(followed_concluded),
                "wins":     sum(1 for r in followed_concluded if r[5] == "낙찰"),
            },
            "deviated": {
                "count":    len(deviated_concluded),
                "win_rate": _win_rate(deviated_concluded),
                "wins":     sum(1 for r in deviated_concluded if r[5] == "낙찰"),
            },
        },
        "recent_items":          recent_items,
    }


@router.get("/our-win-map")
def our_win_map(
    months: int = Query(24, ge=3, le=60),
    top_agencies: int = Query(15, ge=5, le=30),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    우리 회사 발주기관 × 공종 승률 히트맵.
    bid_executions 기준 우리 낙찰률을 기관-공종 매트릭스로 반환.
    """
    # bid_executions 기반 (수동 입력 + SUCVIEW 파일 업로드)
    exec_rows = db.execute(text("""
        WITH exec_data AS (
            SELECT
                COALESCE(be.agency_name, b.name) AS agency_name,
                COALESCE(be.industry_name, ind.name) AS industry_name,
                be.status,
                be.base_amount,
                be.bid_open_date
            FROM bid_executions be
            LEFT JOIN bids bi ON bi.id = be.bid_id
            LEFT JOIN agencies b ON b.id = bi.agency_id
            LEFT JOIN industries ind ON ind.id = bi.industry_id
            WHERE be.user_id = :uid
              AND be.status IN ('낙찰', '패찰')
              AND be.bid_open_date >= NOW() - INTERVAL ':months months'
        )
        SELECT
            agency_name,
            industry_name,
            COUNT(*) AS total,
            COUNT(CASE WHEN status = '낙찰' THEN 1 END) AS wins,
            SUM(base_amount) AS total_amount,
            SUM(CASE WHEN status = '낙찰' THEN base_amount END) AS win_amount
        FROM exec_data
        WHERE agency_name IS NOT NULL
        GROUP BY agency_name, industry_name
        HAVING COUNT(*) >= 1
        ORDER BY total DESC
    """.replace(':months', str(months))), {"uid": user.id}).fetchall()

    # journal 기반 보완 (bid_executions 없는 경우)
    journal_rows = db.execute(text("""
        WITH j_data AS (
            SELECT
                a.name AS agency_name,
                ind.name AS industry_name,
                j.result,
                b.base_amount,
                j.submitted_at
            FROM bid_journal j
            JOIN bids b ON b.id = j.bid_id
            LEFT JOIN agencies a ON a.id = b.agency_id
            LEFT JOIN industries ind ON ind.id = b.industry_id
            WHERE j.user_id = :uid
              AND j.result IN ('낙찰', '패찰')
              AND j.submitted_at >= NOW() - INTERVAL ':months months'
        )
        SELECT
            agency_name,
            industry_name,
            COUNT(*) AS total,
            COUNT(CASE WHEN result = '낙찰' THEN 1 END) AS wins,
            SUM(base_amount) AS total_amount,
            SUM(CASE WHEN result = '낙찰' THEN base_amount END) AS win_amount
        FROM j_data
        WHERE agency_name IS NOT NULL
        GROUP BY agency_name, industry_name
        HAVING COUNT(*) >= 1
    """.replace(':months', str(months))), {"uid": user.id}).fetchall()

    # 두 소스 병합 (기관명+공종 기준 upsert)
    merged: dict = {}
    for rows in [exec_rows, journal_rows]:
        for r in rows:
            key = (r[0] or "기타", r[1] or "기타")
            if key not in merged:
                merged[key] = {"total": 0, "wins": 0, "total_amount": 0, "win_amount": 0}
            merged[key]["total"] += int(r[2] or 0)
            merged[key]["wins"]  += int(r[3] or 0)
            merged[key]["total_amount"] += int(r[4] or 0)
            merged[key]["win_amount"]   += int(r[5] or 0) if r[5] else 0

    # 상위 기관 선택 (총 참여 건수 기준)
    agency_totals: dict = {}
    for (agency, _), v in merged.items():
        agency_totals[agency] = agency_totals.get(agency, 0) + v["total"]
    top_agency_names = sorted(agency_totals, key=lambda x: -agency_totals[x])[:top_agencies]

    # 공종 목록
    industry_names = sorted({ind for (_, ind) in merged.keys()})

    # 매트릭스 생성
    matrix = []
    for agency in top_agency_names:
        row_data = {"agency": agency, "total": agency_totals[agency], "cells": {}}
        for ind in industry_names:
            v = merged.get((agency, ind))
            if v and v["total"] > 0:
                row_data["cells"][ind] = {
                    "total":    v["total"],
                    "wins":     v["wins"],
                    "win_rate": round(v["wins"] / v["total"], 4),
                    "win_amount": v["win_amount"],
                }
        matrix.append(row_data)

    # 전체 요약
    all_total = sum(v["total"] for v in merged.values())
    all_wins  = sum(v["wins"]  for v in merged.values())

    return {
        "months":         months,
        "agencies":       top_agency_names,
        "industries":     industry_names,
        "matrix":         matrix,
        "summary": {
            "total_bids":  all_total,
            "total_wins":  all_wins,
            "overall_win_rate": round(all_wins / all_total, 4) if all_total > 0 else 0,
        },
    }
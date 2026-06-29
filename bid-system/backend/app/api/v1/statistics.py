from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import Optional

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
"""
Phase 4 ML 피처 — 사전규격·계약정보 기반 추가 피처

pre_spec_gap_days     : 사전규격 → 공고 게시까지 평균 일수 (기관별)
agency_contract_freq  : 기관의 최근 12개월 계약 빈도 (건/월)
joint_bid_prob        : 기관 계약 중 공동수급 비율 (0~1)
competitor_busy_score : 주요 경쟁사 현재 공사 부담도 (0~10, 높을수록 경쟁약화 예상)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


def load_p4_features(
    db: Session,
    agency_id: Optional[int],
    bid_id: Optional[int] = None,
    announcement_no: Optional[str] = None,
    competitor_biz_reg_nos: Optional[list[str]] = None,
) -> dict:
    """
    Phase 4 피처를 한 번에 조회하여 dict로 반환.

    Returns:
        pre_spec_gap_days     : int | None
        agency_contract_freq  : float | None  (건/월, 최근 12개월)
        joint_bid_prob        : float | None  (0.0 ~ 1.0)
        competitor_busy_score : float | None  (0.0 ~ 10.0)
        has_pre_spec          : bool
    """
    result: dict = {
        "pre_spec_gap_days":     None,
        "agency_contract_freq":  None,
        "joint_bid_prob":        None,
        "competitor_busy_score": None,
        "has_pre_spec":          False,
    }

    # ── 1. pre_spec_gap_days ────────────────────────────────────────
    # bid에 연결된 사전규격이 있으면, 사전규격 등록일→공고 공개일 gap 계산
    if bid_id:
        try:
            row = db.execute(text("""
                SELECT ps.reg_date, b.created_at
                FROM pre_spec_notices ps
                JOIN bids b ON b.id = :bid_id
                WHERE ps.bid_id = :bid_id
                ORDER BY ps.reg_date ASC
                LIMIT 1
            """), {"bid_id": bid_id}).fetchone()
            if row and row[0] and row[1]:
                reg_dt = row[0]
                pub_dt = row[1]
                if hasattr(reg_dt, "date"):
                    reg_dt = reg_dt.replace(tzinfo=None)
                if hasattr(pub_dt, "date"):
                    pub_dt = pub_dt.replace(tzinfo=None)
                gap = (pub_dt - reg_dt).days
                if gap >= 0:
                    result["pre_spec_gap_days"] = gap
                    result["has_pre_spec"] = True
        except Exception:
            pass

    # bid_id 없어도 announcement_no로 사전규격 존재 확인
    if not result["has_pre_spec"] and announcement_no:
        try:
            cnt = db.execute(text("""
                SELECT COUNT(*) FROM pre_spec_notices
                WHERE bid_announcement_no = :an
            """), {"an": announcement_no}).scalar()
            result["has_pre_spec"] = (cnt or 0) > 0
        except Exception:
            pass

    if not agency_id:
        return result

    # ── 2. agency_contract_freq (건/월, 최근 12개월) ─────────────────
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=365)
        cnt_row = db.execute(text("""
            SELECT COUNT(*) FROM bid_contracts
            WHERE agency_code = (
                SELECT code FROM agencies WHERE id = :aid LIMIT 1
            )
            AND contract_date >= :cutoff
        """), {"aid": agency_id, "cutoff": cutoff}).fetchone()
        if cnt_row and cnt_row[0] is not None:
            result["agency_contract_freq"] = round(cnt_row[0] / 12.0, 2)
    except Exception:
        pass

    # agency_code 없이 이름으로 폴백
    if result["agency_contract_freq"] is None:
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=365)
            cnt_row = db.execute(text("""
                SELECT COUNT(*) FROM bid_contracts bc
                JOIN agencies a ON a.name = bc.agency_name
                WHERE a.id = :aid
                AND bc.contract_date >= :cutoff
            """), {"aid": agency_id, "cutoff": cutoff}).fetchone()
            if cnt_row and cnt_row[0] is not None:
                result["agency_contract_freq"] = round(cnt_row[0] / 12.0, 2)
        except Exception:
            pass

    # ── 3. joint_bid_prob (공동수급 비율, 최근 2년) ──────────────────
    try:
        cutoff2y = datetime.now(timezone.utc) - timedelta(days=730)
        row = db.execute(text("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN joint_contract = 'Y' THEN 1 ELSE 0 END) AS joint_cnt
            FROM bid_contracts bc
            JOIN agencies a ON a.name = bc.agency_name
            WHERE a.id = :aid
              AND bc.contract_date >= :cutoff
        """), {"aid": agency_id, "cutoff": cutoff2y}).fetchone()
        if row and row[0] and row[0] > 0:
            result["joint_bid_prob"] = round(row[1] / row[0], 3)
    except Exception:
        pass

    # ── 4. competitor_busy_score ─────────────────────────────────────
    # 주요 경쟁사(biz_reg_no 목록)의 현재 진행 중인 계약 건수 기반
    if competitor_biz_reg_nos:
        try:
            today = datetime.now(timezone.utc).date()
            busy_count = 0
            for brn in competitor_biz_reg_nos:
                if not brn:
                    continue
                row = db.execute(text("""
                    SELECT COUNT(*) FROM bid_contracts
                    WHERE start_date <= :today
                      AND (completion_date IS NULL OR completion_date >= :today)
                      AND EXISTS (
                          SELECT 1 FROM jsonb_array_elements(company_list) AS el
                          WHERE el->>'bizRegNo' = :brn
                      )
                """), {"today": today, "brn": brn}).fetchone()
                if row:
                    busy_count += (row[0] or 0)

            n_comp = max(1, len([b for b in competitor_biz_reg_nos if b]))
            score = min(10.0, (busy_count / n_comp) * 2.5)
            result["competitor_busy_score"] = round(score, 2)
        except Exception:
            pass

    return result


def agency_pre_spec_lead_time(db: Session, agency_id: int, months: int = 12) -> dict:
    """기관별 사전규격→공고 리드타임 통계 (평균/중위수 일수)."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30)
        rows = db.execute(text("""
            SELECT
                EXTRACT(DAY FROM (b.created_at - ps.reg_date))::int AS gap_days
            FROM pre_spec_notices ps
            JOIN bids b ON b.id = ps.bid_id
            JOIN agencies a ON a.name = ps.order_agency
            WHERE a.id = :aid
              AND ps.reg_date >= :cutoff
              AND b.created_at > ps.reg_date
        """), {"aid": agency_id, "cutoff": cutoff}).fetchall()

        gaps = [r[0] for r in rows if r[0] is not None and r[0] >= 0]
        if not gaps:
            return {"mean": None, "median": None, "n": 0}
        gaps.sort()
        mid = len(gaps) // 2
        median = gaps[mid] if len(gaps) % 2 else (gaps[mid - 1] + gaps[mid]) / 2
        return {"mean": round(sum(gaps) / len(gaps), 1), "median": median, "n": len(gaps)}
    except Exception:
        return {"mean": None, "median": None, "n": 0}

"""
Option D: 실증 승자 분포 기반 최적 투찰율 추천 모듈

inpo21c_participants 실제 낙찰자 bid_rate 분포에서
백분위(P65~P75) 기반 최적 투찰율을 직접 도출한다.

핵심 원칙:
  - 시뮬레이션 추정 오차 제거 → 실측 데이터 직접 활용
  - 경쟁 강도(평균 응찰사 수) 기반 동적 백분위 선택
  - A값(사정율) 분포 기반 2단계 추천 지원
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# 유효 투찰율 범위 (기초금액 대비)
BID_RATE_MIN = 0.840
BID_RATE_MAX = 0.990

# 유효 사정율 범위 (예정가격/기초금액)
ASSESSMENT_RATE_MIN = 0.80
ASSESSMENT_RATE_MAX = 1.10

# 유효 예정대비 투찰율 범위 (bid_rate / assessment_rate)
RELATIVE_RATE_MIN = 0.85
RELATIVE_RATE_MAX = 1.02


def get_winner_percentiles(
    db: Session,
    agency_id: Optional[int],
    industry_id: Optional[int],
    base_amount: int,
    period_type: str = "24M",
    amount_range_pct: float = 0.35,
) -> dict:
    """
    유사 공고 실제 낙찰자 bid_rate 분포에서 백분위 기반 추천값 계산.

    필터: 동일 기관 + 기초금액 ±35% + 최근 period
    기관 데이터 부족(< 10건) 시 전국 동일 금액대 fallback.

    Returns:
        count:                 샘플 수
        p25/p50/p65/p70/p75/p85: 백분위 투찰율
        target_percentile:     선택된 백분위 (경쟁 강도 기반)
        target_rate:           최종 권장 투찰율
        avg_competitors:       평균 응찰사 수
        competition_intensity: 'high' | 'normal' | 'low'
        data_source:           'agency' | 'national'
    """
    period_months = {"12M": 12, "24M": 24, "48M": 48}.get(period_type, 24)
    cutoff = f"NOW() - INTERVAL '{period_months} months'"

    amount_lo = base_amount * (1 - amount_range_pct)
    amount_hi = base_amount * (1 + amount_range_pct)

    source = "national"
    rows = []

    if agency_id:
        rows = db.execute(text(f"""
            SELECT ip.bid_rate::float
            FROM inpo21c_participants ip
            JOIN inpo21c_bids ib USING (inpo21c_bid_id)
            JOIN agencies a ON (
                TRIM(a.name) = TRIM(ib.agency_name)
                OR TRIM(ib.agency_name) LIKE '%%' || TRIM(a.name) || '%%'
                OR TRIM(a.name) LIKE '%%' || TRIM(ib.agency_name) || '%%'
            )
            WHERE ip.is_winner = TRUE
              AND a.id = :aid
              AND ib.base_amount BETWEEN :lo AND :hi
              AND ib.open_datetime >= {cutoff}
              AND ip.bid_rate BETWEEN :rmin AND :rmax
        """), {"aid": agency_id, "lo": amount_lo, "hi": amount_hi,
               "rmin": BID_RATE_MIN, "rmax": BID_RATE_MAX}).fetchall()

        if len(rows) >= 10:
            source = "agency"
        else:
            rows = []

    if not rows:
        rows = db.execute(text(f"""
            SELECT ip.bid_rate::float
            FROM inpo21c_participants ip
            JOIN inpo21c_bids ib USING (inpo21c_bid_id)
            WHERE ip.is_winner = TRUE
              AND ib.base_amount BETWEEN :lo AND :hi
              AND ib.open_datetime >= {cutoff}
              AND ip.bid_rate BETWEEN :rmin AND :rmax
        """), {"lo": amount_lo, "hi": amount_hi,
               "rmin": BID_RATE_MIN, "rmax": BID_RATE_MAX}).fetchall()
        source = "national"

    if len(rows) < 5:
        return _empty_winner_dist()

    rates = np.array([float(r[0]) for r in rows])

    # 경쟁 강도: 기관별 평균 응찰사 수
    avg_competitors = _get_avg_competitors(db, agency_id, amount_lo, amount_hi, cutoff)

    # 경쟁 강도 → 타겟 백분위 결정
    if avg_competitors >= 10:
        intensity   = "high"
        target_pct  = 55
    elif avg_competitors <= 4:
        intensity   = "low"
        target_pct  = 75
    else:
        intensity   = "normal"
        target_pct  = 65

    p25  = round(float(np.percentile(rates, 25)),  4)
    p50  = round(float(np.percentile(rates, 50)),  4)
    p65  = round(float(np.percentile(rates, 65)),  4)
    p70  = round(float(np.percentile(rates, 70)),  4)
    p75  = round(float(np.percentile(rates, 75)),  4)
    p85  = round(float(np.percentile(rates, 85)),  4)
    target_rate = round(float(np.percentile(rates, target_pct)), 4)

    logger.debug(
        "winner_dist [%s] n=%d src=%s p50=%.4f p65=%.4f p75=%.4f",
        period_type, len(rates), source, p50, p65, p75,
    )

    return {
        "count":                 len(rates),
        "p25":                   p25,
        "p50":                   p50,
        "p65":                   p65,
        "p70":                   p70,
        "p75":                   p75,
        "p85":                   p85,
        "target_percentile":     target_pct,
        "target_rate":           target_rate,
        "avg_competitors":       round(avg_competitors, 1),
        "competition_intensity": intensity,
        "data_source":           source,
    }


def get_assessment_rate_dist(
    db: Session,
    agency_id: Optional[int],
    period_type: str = "24M",
) -> dict:
    """
    발주처별 사정율(예정가격/기초금액) 분포.

    inpo21c_bids.estimated_amount / base_amount 실측값 사용.
    기관 데이터 부족 시 전국 평균 fallback.

    Returns: p25/p50/p75/mean/std/count/source
    """
    period_months = {"12M": 12, "24M": 24, "48M": 48}.get(period_type, 24)
    cutoff = f"NOW() - INTERVAL '{period_months} months'"

    source = "national"
    rows = []

    if agency_id:
        rows = db.execute(text(f"""
            SELECT ib.estimated_amount::float / NULLIF(ib.base_amount, 0) AS arate
            FROM inpo21c_bids ib
            JOIN agencies a ON (
                TRIM(a.name) = TRIM(ib.agency_name)
                OR TRIM(ib.agency_name) LIKE '%%' || TRIM(a.name) || '%%'
                OR TRIM(a.name) LIKE '%%' || TRIM(ib.agency_name) || '%%'
            )
            WHERE a.id = :aid
              AND ib.estimated_amount IS NOT NULL
              AND ib.base_amount > 0
              AND ib.estimated_amount::float / ib.base_amount
                  BETWEEN :rmin AND :rmax
              AND ABS(ib.estimated_amount::float / ib.base_amount - (10.0/11.0)) > 0.002
              AND ib.open_datetime >= {cutoff}
        """), {"aid": agency_id,
               "rmin": ASSESSMENT_RATE_MIN, "rmax": ASSESSMENT_RATE_MAX}).fetchall()

        if len(rows) >= 5:
            source = "agency"
        else:
            rows = []

    if not rows:
        rows = db.execute(text(f"""
            SELECT ib.estimated_amount::float / NULLIF(ib.base_amount, 0) AS arate
            FROM inpo21c_bids ib
            WHERE ib.estimated_amount IS NOT NULL
              AND ib.base_amount > 0
              AND ib.estimated_amount::float / ib.base_amount
                  BETWEEN :rmin AND :rmax
              AND ABS(ib.estimated_amount::float / ib.base_amount - (10.0/11.0)) > 0.002
              AND ib.open_datetime >= {cutoff}
        """), {"rmin": ASSESSMENT_RATE_MIN, "rmax": ASSESSMENT_RATE_MAX}).fetchall()
        source = "national"

    if len(rows) < 3:
        return {"p50": None, "p75": None, "mean": None, "std": None,
                "count": 0, "source": "none"}

    arates = np.array([float(r[0]) for r in rows if r[0]])

    return {
        "p25":    round(float(np.percentile(arates, 25)), 4),
        "p50":    round(float(np.percentile(arates, 50)), 4),
        "p75":    round(float(np.percentile(arates, 75)), 4),
        "mean":   round(float(arates.mean()),             4),
        "std":    round(float(arates.std()),              4),
        "count":  len(arates),
        "source": source,
    }


def get_relative_rate_dist(
    db: Session,
    agency_id: Optional[int],
    industry_id: Optional[int],
    period_type: str = "24M",
) -> dict:
    """
    낙찰자의 예정대비 투찰율(bid_rate / assessment_rate) 분포.

    A값 근접도 분석: 낙찰자가 예정가격 대비 몇 % 수준에 투찰했는가.
    이 비율의 최적 백분위 × 예측 A값 = 최종 권장 bid_rate.

    Returns: p50/p65/p70/p75/mean/std/count/source
    """
    period_months = {"12M": 12, "24M": 24, "48M": 48}.get(period_type, 24)
    cutoff = f"NOW() - INTERVAL '{period_months} months'"

    source = "national"
    rows = []

    if agency_id:
        rows = db.execute(text(f"""
            SELECT ip.bid_rate::float
                   / NULLIF(ib.estimated_amount::float / ib.base_amount, 0)
                   AS rel_rate
            FROM inpo21c_participants ip
            JOIN inpo21c_bids ib USING (inpo21c_bid_id)
            JOIN agencies a ON (
                TRIM(a.name) = TRIM(ib.agency_name)
                OR TRIM(ib.agency_name) LIKE '%%' || TRIM(a.name) || '%%'
                OR TRIM(a.name) LIKE '%%' || TRIM(ib.agency_name) || '%%'
            )
            WHERE ip.is_winner = TRUE
              AND a.id = :aid
              AND ib.estimated_amount IS NOT NULL
              AND ib.base_amount > 0
              AND ip.bid_rate BETWEEN :bmin AND :bmax
              AND ib.estimated_amount::float / ib.base_amount
                  BETWEEN :amin AND :amax
              AND ib.open_datetime >= {cutoff}
        """), {"aid": agency_id,
               "bmin": BID_RATE_MIN, "bmax": BID_RATE_MAX,
               "amin": ASSESSMENT_RATE_MIN, "amax": ASSESSMENT_RATE_MAX}).fetchall()

        if len(rows) >= 5:
            source = "agency"
        else:
            rows = []

    if not rows:
        rows = db.execute(text(f"""
            SELECT ip.bid_rate::float
                   / NULLIF(ib.estimated_amount::float / ib.base_amount, 0)
                   AS rel_rate
            FROM inpo21c_participants ip
            JOIN inpo21c_bids ib USING (inpo21c_bid_id)
            WHERE ip.is_winner = TRUE
              AND ib.estimated_amount IS NOT NULL
              AND ib.base_amount > 0
              AND ip.bid_rate BETWEEN :bmin AND :bmax
              AND ib.estimated_amount::float / ib.base_amount
                  BETWEEN :amin AND :amax
              AND ib.open_datetime >= {cutoff}
        """), {"bmin": BID_RATE_MIN, "bmax": BID_RATE_MAX,
               "amin": ASSESSMENT_RATE_MIN, "amax": ASSESSMENT_RATE_MAX}).fetchall()
        source = "national"

    if len(rows) < 5:
        return {"p50": None, "p65": None, "p70": None, "p75": None,
                "mean": None, "std": None, "count": 0, "source": "none"}

    rel = np.array([
        float(r[0]) for r in rows
        if r[0] and RELATIVE_RATE_MIN <= float(r[0]) <= RELATIVE_RATE_MAX
    ])

    if len(rel) < 5:
        return {"p50": None, "p65": None, "p70": None, "p75": None,
                "mean": None, "std": None, "count": 0, "source": "none"}

    return {
        "p50":    round(float(np.percentile(rel, 50)), 4),
        "p65":    round(float(np.percentile(rel, 65)), 4),
        "p70":    round(float(np.percentile(rel, 70)), 4),
        "p75":    round(float(np.percentile(rel, 75)), 4),
        "mean":   round(float(rel.mean()),             4),
        "std":    round(float(rel.std()),              4),
        "count":  len(rel),
        "source": source,
    }


# ──────────────────────────────────────────────
# 내부 헬퍼
# ──────────────────────────────────────────────

def _get_avg_competitors(
    db: Session,
    agency_id: Optional[int],
    amount_lo: float,
    amount_hi: float,
    cutoff: str,
) -> float:
    """기관+금액대 기준 평균 응찰사 수."""
    if agency_id:
        row = db.execute(text(f"""
            SELECT AVG(c)::float
            FROM (
                SELECT COUNT(*) AS c
                FROM inpo21c_participants ip
                JOIN inpo21c_bids ib USING (inpo21c_bid_id)
                JOIN agencies a ON (
                    TRIM(a.name) = TRIM(ib.agency_name)
                    OR TRIM(ib.agency_name) LIKE '%%' || TRIM(a.name) || '%%'
                    OR TRIM(a.name) LIKE '%%' || TRIM(ib.agency_name) || '%%'
                )
                WHERE a.id = :aid
                  AND ib.base_amount BETWEEN :lo AND :hi
                  AND ib.open_datetime >= {cutoff}
                  AND ip.company_name != '유찰'
                GROUP BY ib.inpo21c_bid_id
                HAVING COUNT(*) >= 2
            ) t
        """), {"aid": agency_id, "lo": amount_lo, "hi": amount_hi}).fetchone()

        if row and row[0]:
            return float(row[0])

    # 전국 평균 fallback
    row = db.execute(text(f"""
        SELECT AVG(c)::float
        FROM (
            SELECT COUNT(*) AS c
            FROM inpo21c_participants ip
            JOIN inpo21c_bids ib USING (inpo21c_bid_id)
            WHERE ib.base_amount BETWEEN :lo AND :hi
              AND ib.open_datetime >= {cutoff}
              AND ip.company_name != '유찰'
            GROUP BY ib.inpo21c_bid_id
            HAVING COUNT(*) >= 2
        ) t
    """), {"lo": amount_lo, "hi": amount_hi}).fetchone()

    return float(row[0]) if row and row[0] else 8.0


def _empty_winner_dist() -> dict:
    return {
        "count": 0, "p25": None, "p50": None,
        "p65": None, "p70": None, "p75": None, "p85": None,
        "target_percentile": 65, "target_rate": None,
        "avg_competitors": 8.0, "competition_intensity": "normal",
        "data_source": "none",
    }

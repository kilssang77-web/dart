"""
Hot Zone 탐지 — inpo21c_participants 직접 쿼리 + rate_frequency_tables KDE 기반.

★ 용어 정의 (이 모듈에서 사용하는 "srate" / "rate" 의미)
  - srate (peaks 내부)  : bid_rate = 투찰금액 / 기초금액  (범위: 0.860~0.970)
  - assessment_rate     : 예정가격 / 기초금액            (범위: 0.970~1.030, 복수예가)
  - relative_rate       : 투찰금액 / 예정가격 = bid_rate / assessment_rate

  get_hot_zones()의 peaks[].srate   → bid_rate (기초대비)
  get_best_rate()의 recommended_srate → bid_rate (기초대비)
  assessment.py의 srate_center/std   → assessment_rate (예정/기초)
"""
from __future__ import annotations

import math
import logging
from typing import Optional

import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# 복수예가 낙찰 집중 구간 (0.860~0.970 포괄 — 복수예가 srate≈1.0 포함)
RATE_MIN = 0.860
RATE_MAX = 0.970


def _query_bid_rate_dist(
    db: Session,
    agency_id: Optional[int],
    period_months: int = 24,
) -> tuple[list, str]:
    """
    inpo21c_participants.bid_rate 기반 투찰율 구간별 낙찰 분포 조회.

    agency_id가 있으면 기관 전용, 없거나 데이터 부족이면 전국 집계.
    Returns (rows, source) — rows: (bucket, total, winners)
    """
    cutoff_sql = f"NOW() - INTERVAL '{period_months} months'"
    source = "national"

    if agency_id:
        rows = db.execute(text(f"""
            SELECT ROUND(ip.bid_rate::numeric, 3)                 AS bucket,
                   COUNT(*)                                        AS total,
                   SUM(CASE WHEN ip.is_winner THEN 1 ELSE 0 END) AS winners
            FROM inpo21c_participants ip
            JOIN inpo21c_bids ib USING (inpo21c_bid_id)
            JOIN agencies a ON (
                TRIM(a.name) = TRIM(ib.agency_name)
                OR TRIM(ib.agency_name) LIKE '%%' || TRIM(a.name) || '%%'
                OR TRIM(a.name) LIKE '%%' || TRIM(ib.agency_name) || '%%'
            )
            WHERE a.id = :aid
              AND ip.bid_rate BETWEEN :rmin AND :rmax
              AND ib.open_datetime >= {cutoff_sql}
            GROUP BY bucket
            ORDER BY bucket
        """), {"aid": agency_id, "rmin": RATE_MIN, "rmax": RATE_MAX}).fetchall()

        if rows and sum(int(r[2]) for r in rows) >= 10:
            source = "agency"
            return rows, source

    rows = db.execute(text(f"""
        SELECT ROUND(ip.bid_rate::numeric, 3)                 AS bucket,
               COUNT(*)                                        AS total,
               SUM(CASE WHEN ip.is_winner THEN 1 ELSE 0 END) AS winners
        FROM inpo21c_participants ip
        JOIN inpo21c_bids ib USING (inpo21c_bid_id)
        WHERE ip.bid_rate BETWEEN :rmin AND :rmax
          AND ib.open_datetime >= {cutoff_sql}
        GROUP BY bucket
        ORDER BY bucket
    """), {"rmin": RATE_MIN, "rmax": RATE_MAX}).fetchall()

    return rows, source


def get_hot_zones(
    db: Session,
    agency_id: Optional[int],
    period_type: str = "24M",
    min_win_count: int = 3,
    prominence: float = 0.05,
) -> dict:
    """
    inpo21c_participants.bid_rate KDE로 Hot Zone 탐지.

    Args:
        agency_id: 기관 ID (None이면 전국)
        period_type: "12M" | "24M" | "48M"
        min_win_count: 최소 낙찰 건수
        prominence: find_peaks prominence (smoothed signal 최댓값 대비 비율)

    Returns:
        peaks       : Hot Zone 목록 (srate, win_rate, score, rank)
        best_rate   : 최고 점수 단일 구간
        kde_x/kde_y : 시각화용 KDE 곡선
        data_source : "agency" | "national"
    """
    from scipy.signal import find_peaks
    from scipy.ndimage import gaussian_filter1d

    period_months = {"12M": 12, "24M": 24, "48M": 48}.get(period_type, 24)
    rows, source = _query_bid_rate_dist(db, agency_id, period_months)

    if not rows:
        return _empty_result(source)

    srates    = np.array([float(r[0]) for r in rows])
    totals    = np.array([max(int(r[1]), 0) for r in rows])
    win_counts = np.array([max(int(r[2]), 0) for r in rows])
    win_rates  = np.where(totals > 0, win_counts / totals, 0.0)

    # KDE: gaussian smoothing on win_rate × log(total+1) signal
    signal = win_rates * np.log1p(win_counts)
    sigma = 1.5  # ≈ 0.0015 스무딩 반경 (0.001 버킷 단위)
    smoothed = gaussian_filter1d(signal, sigma=sigma)

    # 피크 탐지
    max_val = smoothed.max()
    if max_val <= 0:
        return _empty_result(source)

    peak_idxs, _ = find_peaks(
        smoothed,
        distance=4,   # 최소 0.004 간격
        prominence=prominence * max_val,
    )

    peaks = []
    for idx in peak_idxs:
        if int(win_counts[idx]) < min_win_count:
            continue
        sr  = float(srates[idx])
        wr  = float(win_rates[idx])
        wc  = int(win_counts[idx])
        tc  = int(totals[idx])
        score = wr * math.log1p(wc)
        peaks.append({
            "srate":     round(sr, 4),
            "win_rate":  round(wr, 4),
            "win_count": wc,
            "total":     tc,
            "score":     round(score, 4),
        })

    peaks.sort(key=lambda p: p["score"], reverse=True)
    for i, p in enumerate(peaks, 1):
        p["rank"] = i

    best_rate = peaks[0]["srate"] if peaks else None

    kde_x = [round(float(v), 3) for v in srates]
    kde_y = [round(float(v), 6) for v in smoothed]

    return {
        "peaks":       peaks[:10],
        "best_rate":   best_rate,
        "kde_x":       kde_x,
        "kde_y":       kde_y,
        "data_source": source,
        "period_type": period_type,
        "total_wins":  int(win_counts.sum()),
        "total_bids":  int(totals.sum()),
    }


def _empty_result(source: str) -> dict:
    return {
        "peaks": [], "best_rate": None,
        "kde_x": [], "kde_y": [],
        "data_source": source, "period_type": "24M",
        "total_wins": 0, "total_bids": 0,
    }


def get_best_rate(
    db: Session,
    agency_id: Optional[int],
    base_amount: int = 0,
    a_ratio: float = 0.9100,
    period_type: str = "24M",
) -> dict:
    """
    Option D: 실증 승자 분포 기반 최적 투찰율 계산.

    추천 우선순위:
    1) 승자분포 타겟 + Hot Zone 버킷 일치  → winner+hotzone  (신뢰도 최고)
    2) 승자분포 타겟 단독 (count >= 10)    → winner
    3) A값 예측 × 예정대비 최적율          → assessment_based
    4) Hot Zone 1위 + Prism 일치 (±0.005) → hotzone+prism   (기존 fallback)
    5) Hot Zone 1위 단독 (win_count >= 10) → hotzone
    6) Prism Top 1위 단독                 → prism
    7) 전국 최빈 낙찰 구간 0.898          → fallback
    """
    from .assessment import get_prism_zones, get_agency_a_ratio
    from .winner_dist import (
        get_winner_percentiles,
        get_assessment_rate_dist,
        get_relative_rate_dist,
    )

    hot        = get_hot_zones(db, agency_id, period_type=period_type)
    prism      = get_prism_zones(db, agency_id, period_type=period_type)
    winner     = get_winner_percentiles(db, agency_id, None, base_amount, period_type)
    arate_dist = get_assessment_rate_dist(db, agency_id, period_type)
    rel_dist   = get_relative_rate_dist(db, agency_id, None, period_type)
    a_ratio_actual = get_agency_a_ratio(db, agency_id)

    recommended_srate: Optional[float] = None
    source     = "fallback"
    confidence = 0.30

    target_rate  = winner.get("target_rate")
    target_pct   = winner.get("target_percentile", 65)
    winner_count = winner.get("count", 0)
    intensity    = winner.get("competition_intensity", "normal")

    # ── 1/2: 승자분포 기반 ────────────────────────────────
    if target_rate and winner_count >= 10:
        if hot["best_rate"]:
            hot_bucket    = round(hot["best_rate"], 3)
            target_bucket = round(target_rate, 3)
            bucket_match  = abs(hot_bucket - target_bucket) <= 0.002

            if bucket_match:
                recommended_srate = target_rate
                source     = "winner+hotzone"
                confidence = min(0.95, 0.70 + min(winner_count, 100) / 500)
            else:
                # 버킷 불일치 → 승자분포만 사용 (실증 데이터 우선)
                recommended_srate = target_rate
                source     = "winner"
                confidence = min(0.82, 0.58 + min(winner_count, 100) / 500)
        else:
            recommended_srate = target_rate
            source     = "winner"
            confidence = min(0.80, 0.55 + min(winner_count, 100) / 500)

    # ── 3: A값 × 예정대비 최적율 ────────────────────────
    if recommended_srate is None:
        arate_p50 = arate_dist.get("p50")
        rel_key   = "p75" if intensity == "low" else "p65"
        rel_opt   = rel_dist.get(rel_key)

        if arate_p50 and rel_opt and arate_dist.get("count", 0) >= 5:
            calc = round(arate_p50 * rel_opt, 4)
            if 0.840 <= calc <= 0.990:
                recommended_srate = calc
                source     = "assessment_based"
                confidence = min(0.72, 0.45 + min(arate_dist["count"], 50) / 250)

    # ── 4~6: 기존 Hot Zone + Prism fallback ─────────────
    if recommended_srate is None:
        if hot["best_rate"] and prism["top_zones"]:
            prism_top1 = prism["top_zones"][0]["srate"]
            diff = abs(hot["best_rate"] - prism_top1)

            if diff <= 0.005:
                recommended_srate = hot["best_rate"]
                source     = "hotzone+prism"
                confidence = min(0.70, 0.50 + hot["peaks"][0]["win_rate"])
            elif hot["peaks"][0]["win_count"] >= 10:
                recommended_srate = hot["best_rate"]
                source     = "hotzone"
                confidence = min(0.65, 0.45 + hot["peaks"][0]["win_rate"])
            else:
                recommended_srate = prism_top1
                source     = "prism"
                confidence = min(0.60, 0.40 + prism["top_zones"][0]["win_rate"])

        elif hot["best_rate"]:
            recommended_srate = hot["best_rate"]
            source     = "hotzone"
            confidence = min(0.60, 0.38 + hot["peaks"][0]["win_rate"])

        elif prism["top_zones"]:
            recommended_srate = prism["top_zones"][0]["srate"]
            source     = "prism"
            confidence = min(0.55, 0.35 + prism["top_zones"][0]["win_rate"])

        else:
            recommended_srate = 0.898
            source     = "fallback"
            confidence = 0.30

    recommended_price = None
    if base_amount > 0 and recommended_srate:
        recommended_price = int(base_amount * recommended_srate)

    return {
        "recommended_srate":     round(float(recommended_srate), 4) if recommended_srate else None,
        "recommended_price":     recommended_price,
        "confidence":            round(confidence, 3),
        "source":                source,
        "a_ratio":               a_ratio_actual,
        "hotzone_peaks":         hot["peaks"][:5],
        "prism_top":             prism["top_zones"][:5],
        "data_source":           hot["data_source"],
        "period_type":           period_type,
        # Option D 추가 필드
        "winner_percentiles": {
            "p25": winner.get("p25"),
            "p50": winner.get("p50"),
            "p65": winner.get("p65"),
            "p70": winner.get("p70"),
            "p75": winner.get("p75"),
            "p85": winner.get("p85"),
        },
        "winner_count":          winner_count,
        "target_percentile":     target_pct,
        "competition_intensity": intensity,
        "avg_competitors":       winner.get("avg_competitors", 8.0),
        "assessment_rate_est":   arate_dist.get("p50"),
    }

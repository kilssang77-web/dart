"""C-4: 담합 의심 탐지 — CV 기반 이상 투찰 패턴 감지."""
from __future__ import annotations

import logging
from typing import Optional
import numpy as np

logger = logging.getLogger(__name__)

# CV 임계값 (이 이하면 담합 의심)
CV_COLLUSION_THRESHOLD = 0.0030   # 0.30%
CV_SUSPICIOUS_THRESHOLD = 0.0055  # 0.55%

# 동일 구간 밀집도 기준 (전체 참가자 중 이 비율 이상이 0.002 범위 내에 있으면 의심)
CLUSTER_DENSITY_THRESHOLD = 0.60

# 거의 동일한 투찰 기준
NEAR_IDENTICAL_DELTA = 0.0010


def detect_collusion(
    bid_rates: list[float],
    announcement_no: str = "",
    min_participants: int = 3,
) -> dict:
    """
    복수예가 투찰률 목록에서 담합 패턴을 탐지한다.

    Parameters
    ----------
    bid_rates : 투찰률 목록 (예: [0.8802, 0.8815, ...]) — estimated_price 대비 분율
    announcement_no : 공고번호 (로깅용)
    min_participants : 최소 참가자 수 (미만이면 분석 불가)

    Returns
    -------
    dict with keys:
        flag       : "clean" | "suspicious" | "collusion"
        score      : float 0.0~1.0 (높을수록 의심도 높음)
        cv         : 변동계수
        n          : 참가자 수
        near_identical_pairs : 거의 동일 투찰 쌍 수
        cluster_density : 최대 밀집 구간 비율
        reasons    : list[str]
    """
    rates = [r for r in bid_rates if 0.70 <= r <= 1.05]
    n = len(rates)

    if n < min_participants:
        return {
            "flag": "insufficient_data",
            "score": 0.0,
            "cv": None,
            "n": n,
            "near_identical_pairs": 0,
            "cluster_density": 0.0,
            "reasons": [f"참가자 {n}명 — 분석 최소 {min_participants}명 필요"],
        }

    arr = np.array(rates, dtype=np.float64)
    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=1)) if n > 1 else 0.0
    cv = std / mean if mean > 0 else 0.0

    # 거의 동일 투찰 쌍 탐지
    near_identical_pairs = 0
    sorted_arr = np.sort(arr)
    for i in range(len(sorted_arr) - 1):
        if sorted_arr[i + 1] - sorted_arr[i] <= NEAR_IDENTICAL_DELTA:
            near_identical_pairs += 1

    # 최대 밀집 구간 비율 (슬라이딩 윈도우 0.002 범위)
    window = 0.002
    max_in_window = 0
    for ref in arr:
        count_in = int(np.sum((arr >= ref - window / 2) & (arr <= ref + window / 2)))
        max_in_window = max(max_in_window, count_in)
    cluster_density = max_in_window / n if n > 0 else 0.0

    # 점수 계산 (0~1)
    score = 0.0
    reasons: list[str] = []

    # CV 기반
    if cv <= CV_COLLUSION_THRESHOLD:
        score += 0.50
        reasons.append(f"CV={cv:.4f} — 매우 낮음 (담합 강한 의심)")
    elif cv <= CV_SUSPICIOUS_THRESHOLD:
        score += 0.25
        reasons.append(f"CV={cv:.4f} — 낮음 (주의)")

    # 근사 동일 투찰
    near_ratio = near_identical_pairs / max(n - 1, 1)
    if near_ratio >= 0.5:
        score += 0.25
        reasons.append(f"거의 동일 투찰쌍 {near_identical_pairs}개 ({near_ratio:.0%})")
    elif near_ratio >= 0.25:
        score += 0.10
        reasons.append(f"거의 동일 투찰쌍 {near_identical_pairs}개")

    # 밀집도
    if cluster_density >= CLUSTER_DENSITY_THRESHOLD:
        score += 0.25
        reasons.append(f"±0.1% 구간 내 {max_in_window}/{n}명 ({cluster_density:.0%}) 집중")
    elif cluster_density >= 0.40:
        score += 0.10
        reasons.append(f"±0.1% 구간 내 {max_in_window}/{n}명 집중")

    score = min(score, 1.0)

    if score >= 0.65:
        flag = "collusion"
    elif score >= 0.30:
        flag = "suspicious"
    else:
        flag = "clean"

    if not reasons:
        reasons.append("이상 패턴 없음")

    return {
        "flag": flag,
        "score": round(score, 3),
        "cv": round(cv, 5),
        "n": n,
        "mean_rate": round(mean, 5),
        "std_rate": round(std, 5),
        "near_identical_pairs": near_identical_pairs,
        "cluster_density": round(cluster_density, 3),
        "reasons": reasons,
        "announcement_no": announcement_no,
    }


def scan_recent_collusion(db, days: int = 30, limit: int = 200) -> list[dict]:
    """
    최근 N일간 수집된 공고 중 담합 의심 건을 일괄 스캔한다.

    Returns list of dicts with announcement_no, flag, score, n, reasons
    sorted by score descending.
    """
    from sqlalchemy import text as sa_text
    from datetime import datetime, timedelta

    cutoff = datetime.now() - timedelta(days=days)
    rows = db.execute(sa_text("""
        SELECT p.inpo21c_bid_id, p.bid_rate
        FROM inpo21c_participants p
        WHERE p.created_at >= :cutoff
          AND p.bid_rate BETWEEN 0.70 AND 1.05
        ORDER BY p.inpo21c_bid_id, p.bid_rate
    """), {"cutoff": cutoff}).fetchall()

    grouped: dict[str, list[float]] = {}
    for bid_id, rate in rows:
        grouped.setdefault(str(bid_id), []).append(float(rate))

    results = []
    for ano, rates in list(grouped.items())[:limit]:
        if len(rates) < 3:
            continue
        result = detect_collusion(rates, announcement_no=ano)
        if result["flag"] in ("suspicious", "collusion"):
            results.append(result)

    results.sort(key=lambda x: x["score"], reverse=True)
    return results

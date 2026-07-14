"""
inpo21c 31,800건 기반 경쟁사 행동 예측.

1. 특정 공고에 참여할 확률 (agency/industry 히스토리 기반)
2. 참여 시 투찰 구간 분포 (base_ratio 히스토그램)
"""
import math
import logging
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

ZONE_SIZE = 0.005
ZONE_MIN = 0.860
ZONE_MAX = 0.930
AMOUNT_TOLERANCE = 0.30  # ±30%


def predict_participation(competitor_id: int, bid: dict, db: Session) -> dict:
    """
    경쟁사의 공고 참여 확률 예측.

    조건 우선순위:
      1차: 동일 발주처 + 동일 공종 (3건 이상)
      2차: 동일 발주처만 (3건 이상)
      3차: 전체 이력 기반 (fallback)

    Args:
        bid: {agency_id, industry_id, base_amount}
    Returns:
        {probability, basis, confidence}
    """
    agency_id = bid.get("agency_id")
    industry_id = bid.get("industry_id")

    # 1차: 발주처 + 공종 조건
    if agency_id and industry_id:
        row = db.execute(text("""
            SELECT
                COUNT(DISTINCT b.id)                                          AS total_bids,
                COUNT(DISTINCT CASE WHEN br.competitor_id = :cid THEN b.id END) AS comp_bids
            FROM bids b
            LEFT JOIN bid_results br
                   ON br.bid_id = b.id AND br.competitor_id = :cid
            WHERE b.agency_id    = :agency_id
              AND b.industry_id  = :industry_id
        """), {"cid": competitor_id, "agency_id": agency_id, "industry_id": industry_id}).fetchone()

        if row and row[0] >= 3:
            total, participated = int(row[0]), int(row[1])
            prob = participated / total
            basis = f"동일 발주처·공종 {total}건 중 {participated}건 참여"
            confidence = "high" if total >= 20 else "medium" if total >= 5 else "low"
            return {"probability": round(prob, 3), "basis": basis, "confidence": confidence}

    # 2차: 발주처만
    if agency_id:
        row = db.execute(text("""
            SELECT
                COUNT(DISTINCT b.id)                                          AS total_bids,
                COUNT(DISTINCT CASE WHEN br.competitor_id = :cid THEN b.id END) AS comp_bids
            FROM bids b
            LEFT JOIN bid_results br
                   ON br.bid_id = b.id AND br.competitor_id = :cid
            WHERE b.agency_id = :agency_id
        """), {"cid": competitor_id, "agency_id": agency_id}).fetchone()

        if row and row[0] >= 3:
            total, participated = int(row[0]), int(row[1])
            prob = participated / total
            basis = f"동일 발주처 {total}건 중 {participated}건 참여"
            confidence = "high" if total >= 20 else "medium" if total >= 5 else "low"
            return {"probability": round(prob, 3), "basis": basis, "confidence": confidence}

    # 3차: 전체 이력 기반 fallback
    row = db.execute(text(
        "SELECT COUNT(DISTINCT bid_id) FROM bid_results WHERE competitor_id = :cid"
    ), {"cid": competitor_id}).fetchone()
    total_participated = int(row[0]) if row else 0

    total_bids = db.execute(text("SELECT COUNT(*) FROM bids")).scalar() or 1
    prob = min(total_participated / total_bids, 1.0)
    basis = f"전체 이력 {total_participated}건 참여 기반 (발주처·공종 이력 부족)"
    return {"probability": round(prob, 3), "basis": basis, "confidence": "low"}


def predict_bid_zone(competitor_id: int, base_amount: int, db: Session) -> dict:
    """
    참여 시 투찰 구간 분포 예측.

    inpo21c_participants에서 biz_reg_no 기준으로 base_ratio 분포를 조회.
    bid_amount / base_ratio 역산으로 금액 ±30% 필터 적용.
    0.005 버킷 히스토그램 반환.

    Returns:
        {zones, peak_zone, sample_count}
    """
    from ..models import Competitor

    competitor = db.query(Competitor).filter(Competitor.id == competitor_id).first()
    if not competitor or not competitor.biz_reg_no:
        return {"zones": [], "peak_zone": None, "sample_count": 0}

    lo_amount = base_amount * (1 - AMOUNT_TOLERANCE)
    hi_amount = base_amount * (1 + AMOUNT_TOLERANCE)

    # 1차: 금액 필터 적용 (bid_amount / base_ratio 로 기초금액 역산)
    rows = db.execute(text("""
        SELECT base_ratio::float
        FROM inpo21c_participants
        WHERE biz_reg_no  = :biz_reg_no
          AND base_ratio  IS NOT NULL
          AND base_ratio  > 0
          AND base_ratio  BETWEEN :zone_min AND :zone_max
          AND bid_amount  IS NOT NULL
          AND bid_amount  / base_ratio BETWEEN :lo_amount AND :hi_amount
    """), {
        "biz_reg_no": competitor.biz_reg_no,
        "zone_min": ZONE_MIN,
        "zone_max": ZONE_MAX,
        "lo_amount": lo_amount,
        "hi_amount": hi_amount,
    }).fetchall()

    # 데이터 부족 시 금액 필터 없이 재시도
    if len(rows) < 10:
        rows = db.execute(text("""
            SELECT base_ratio::float
            FROM inpo21c_participants
            WHERE biz_reg_no = :biz_reg_no
              AND base_ratio IS NOT NULL
              AND base_ratio BETWEEN :zone_min AND :zone_max
        """), {
            "biz_reg_no": competitor.biz_reg_no,
            "zone_min": ZONE_MIN,
            "zone_max": ZONE_MAX,
        }).fetchall()

    if not rows:
        return {"zones": [], "peak_zone": None, "sample_count": 0}

    total = len(rows)
    bucket_counts: dict[float, int] = {}
    for (ratio,) in rows:
        key = round(math.floor(ratio / ZONE_SIZE) * ZONE_SIZE, 3)
        bucket_counts[key] = bucket_counts.get(key, 0) + 1

    zones = [
        {
            "range_lo": lo,
            "range_hi": round(lo + ZONE_SIZE, 3),
            "pct":      round(cnt / total * 100, 1),
        }
        for lo, cnt in sorted(bucket_counts.items())
    ]
    peak_zone = max(zones, key=lambda z: z["pct"]) if zones else None

    return {"zones": zones, "peak_zone": peak_zone, "sample_count": total}

"""
inpo21c 전 참여자 데이터 기반 실증 경쟁사 분포 모델.

G2B API는 낙찰자 1명만 반환하지만, inpo21c는 전 참여자 데이터를 포함.
실증 분포를 Monte Carlo 시뮬레이션에 공급하여 낙찰확률 예측 정확도 향상.
"""
import numpy as np
import logging
from typing import Optional, Tuple, List
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# 경쟁업체 수 버킷 (lo, hi inclusive)
_COUNT_BUCKETS: List[Tuple[int, int]] = [
    (1,  5),
    (6,  10),
    (11, 20),
    (21, 40),
    (41, 100),
    (101, 9999),
]


def _get_bucket(n: int) -> Tuple[int, int]:
    for lo, hi in _COUNT_BUCKETS:
        if lo <= n <= hi:
            return lo, hi
    return _COUNT_BUCKETS[-1]


def get_inpo_raw_rates(
    db: Session,
    expected_count: int,
    n_samples: int = 3000,
) -> Optional[np.ndarray]:
    """
    inpo21c 실증 투찰률 배열 반환 (비낙찰자만, base_ratio 기준).

    1차: 경쟁업체 수 버킷이 유사한 입찰들에서 샘플링.
    2차 폴백: 버킷 데이터 부족 시 전체 inpo21c 데이터 사용
               (base_ratio 분포 패턴은 경쟁 규모와 무관하게 안정적).

    Returns:
        ndarray shape (n,) — base_ratio(투찰/기초) 값들
        None — 전체 데이터도 50건 미만
    """
    lo, hi = _get_bucket(expected_count)

    rows = db.execute(text("""
        SELECT ip.base_ratio::float
        FROM inpo21c_participants ip
        INNER JOIN (
            SELECT inpo21c_bid_id
            FROM inpo21c_participants
            GROUP BY inpo21c_bid_id
            HAVING COUNT(*) BETWEEN :lo AND :hi
        ) valid_bids ON ip.inpo21c_bid_id = valid_bids.inpo21c_bid_id
        WHERE ip.base_ratio IS NOT NULL
          AND ip.base_ratio BETWEEN 0.860 AND 0.930
          AND ip.is_winner = FALSE
        ORDER BY RANDOM()
        LIMIT :lim
    """), {"lo": lo, "hi": hi, "lim": n_samples}).fetchall()

    # 버킷 데이터 부족 시 전체 inpo21c에서 폴백 샘플링
    if len(rows) < 50:
        rows = db.execute(text("""
            SELECT base_ratio::float
            FROM inpo21c_participants
            WHERE base_ratio IS NOT NULL
              AND base_ratio BETWEEN 0.860 AND 0.930
              AND is_winner = FALSE
            ORDER BY RANDOM()
            LIMIT :lim
        """), {"lim": n_samples}).fetchall()

    if len(rows) < 50:
        logger.debug("inpo21c 전체 분포 부족: %d건", len(rows))
        return None

    return np.array([float(r[0]) for r in rows])


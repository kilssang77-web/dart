"""
A값(예정가격) 자동 계산 + 낙찰하한가 산출 유틸리티

나라장터 복수예가 방식:
  A값(예정가격) = 기초금액 × 사정율
  낙찰하한가    = A값 × 낙찰하한율
"""

# 낙찰하한율 테이블 — simulation.py에서 이전 (공종명 키워드 → 비율)
FLOOR_RATE_TABLE: dict = {
    "전기공사업":    0.86745,
    "정보통신공사업": 0.86745,
    "소방시설공사업": 0.86745,
}
DEFAULT_FLOOR_RATE: float = 0.87745


def calc_floor_rate(industry_name: str) -> float:
    """공종명으로 낙찰하한율 반환 (미매칭 시 87.745%)."""
    if not industry_name:
        return DEFAULT_FLOOR_RATE
    for keyword, rate in FLOOR_RATE_TABLE.items():
        if keyword in industry_name:
            return rate
    return DEFAULT_FLOOR_RATE


def calc_a_value(base_amount: int, srate_center: float) -> int:
    """기초금액 × 사정율 중앙값 → A값(예정가격 추정)."""
    return round(base_amount * srate_center)


def calc_a_value_from_ratio(base_amount: int, a_ratio: float = 0.910) -> int:
    """
    기초금액 × A값비율(예정가/기초금액) → 예정가격 추정.
    inpo21c 실증 전국 평균 a_ratio = 0.910.

    실제 투찰금액 = calc_a_value_from_ratio(base_amount, a_ratio) × 추천_사정율
    """
    return round(base_amount * a_ratio)


def calc_bid_price(base_amount: int, srate: float, a_ratio: float = 0.910) -> int:
    """
    기초금액 + A값비율 + 사정율 → 실제 투찰금액 계산.
    투찰금액 = 기초금액 × a_ratio × srate
    """
    return round(base_amount * a_ratio * srate)


def calc_floor_price(a_value: int, floor_rate: float) -> int:
    """A값 × 낙찰하한율 → 낙찰하한가."""
    return round(a_value * floor_rate)


def calc_bid_range(
    base_amount: int,
    srate_center: float,
    srate_std: float,
    industry_name: str,
    srate_p10: float | None = None,
    srate_p25: float | None = None,
    srate_p75: float | None = None,
    srate_p90: float | None = None,
) -> dict:
    """
    A값·낙찰하한가·사정율 예측 범위 종합 계산.

    Returns:
        a_value: 예정가격(A값) 추정값
        floor_price: 낙찰하한가
        floor_rate: 낙찰하한율
        srate_center: 사정율 중앙값
        srate_range: {p10, p25, p50, p75, p90}
    """
    sigma = max(0.002, min(srate_std, 0.020))
    p10 = srate_p10 if srate_p10 is not None else srate_center - 1.28 * sigma
    p25 = srate_p25 if srate_p25 is not None else srate_center - 0.674 * sigma
    p75 = srate_p75 if srate_p75 is not None else srate_center + 0.674 * sigma
    p90 = srate_p90 if srate_p90 is not None else srate_center + 1.28 * sigma

    a_val    = calc_a_value(base_amount, srate_center)
    fl_rate  = calc_floor_rate(industry_name)
    fl_price = calc_floor_price(a_val, fl_rate)

    return {
        "a_value":      a_val,
        "floor_price":  fl_price,
        "floor_rate":   fl_rate,
        "srate_center": round(srate_center, 6),
        "srate_range": {
            "p10": round(p10, 6),
            "p25": round(p25, 6),
            "p50": round(srate_center, 6),
            "p75": round(p75, 6),
            "p90": round(p90, 6),
        },
    }

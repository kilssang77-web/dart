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


def load_agency_a_ratio(db, agency_id: int, period_months: int = 24) -> dict:
    """
    inpo21c 낙찰자 역산으로 기관별 A값 비율(a_ratio = 예정가/기초금액) 학습.

    낙찰자 투찰률(base_ratio)은 ≈ 투찰금액/기초금액.
    복수예가 구조에서 낙찰자 base_ratio ≈ srate (사정율).
    따라서 a_ratio(=예정가/기초금액) 는 winner들의 base_ratio 분포 중앙값으로 근사.

    Returns:
        agency_a_ratio: 기관별 A값 비율 (없으면 None)
        sample_count: 학습에 사용된 샘플 수
        confidence: 신뢰도 (0~1)
    """
    from sqlalchemy import text as _text
    if not db or not agency_id:
        return {"agency_a_ratio": None, "sample_count": 0, "confidence": 0.0}

    try:
        row = db.execute(_text("""
            SELECT
                ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY ip.base_ratio::float8), 5) AS median_ratio,
                ROUND(STDDEV(ip.base_ratio)::numeric, 5) AS std_ratio,
                COUNT(*) AS n
            FROM inpo21c_participants ip
            JOIN inpo21c_bids ib ON ib.inpo21c_bid_id = ip.inpo21c_bid_id
            JOIN agencies a ON (
                TRIM(a.name) = TRIM(ib.agency_name)
                OR TRIM(ib.agency_name) LIKE '%%' || TRIM(a.name) || '%%'
                OR TRIM(a.name) LIKE '%%' || TRIM(ib.agency_name) || '%%'
            )
            WHERE a.id = :aid
              AND ip.is_winner = TRUE
              AND ip.base_ratio BETWEEN 0.80 AND 1.05
              AND ib.open_datetime >= NOW() - INTERVAL ':m months'
        """.replace(":m", str(period_months))), {"aid": agency_id}).fetchone()

        if not row or row[0] is None:
            return {"agency_a_ratio": None, "sample_count": 0, "confidence": 0.0}

        n = int(row[2])
        median_ratio = float(row[0])
        confidence = min(1.0, n / 30)  # 30건 이상이면 신뢰도 1.0
        return {
            "agency_a_ratio": round(median_ratio, 5),
            "sample_count": n,
            "confidence": round(confidence, 3),
            "std": float(row[1]) if row[1] else None,
        }
    except Exception:
        if db:
            try:
                db.rollback()
            except Exception:
                pass
        return {"agency_a_ratio": None, "sample_count": 0, "confidence": 0.0}


def calc_floor_rate_with_agency(db, agency_id: int, industry_name: str) -> dict:
    """
    낙찰하한율 + 기관 A값 비율 통합 반환.
    decision_service에서 호출해 추천 투찰율의 기준점을 보정한다.
    """
    floor_rate = calc_floor_rate(industry_name)
    a_ratio_data = load_agency_a_ratio(db, agency_id)
    a_ratio = a_ratio_data.get("agency_a_ratio") or 0.910

    return {
        "floor_rate": floor_rate,
        "a_ratio": a_ratio,
        "a_ratio_source": "agency" if a_ratio_data.get("agency_a_ratio") else "national_avg",
        "a_ratio_sample_count": a_ratio_data.get("sample_count", 0),
        "a_ratio_confidence": a_ratio_data.get("confidence", 0.0),
    }


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

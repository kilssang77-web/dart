"""
예가 빈도 분석 — 복수예가 C(15,4) 조합 빈도 분석 (Prism형)

나라장터 복수예가 메커니즘:
  1. A값(예비가격 기초금액) ± 2% 범위에서 15개 예비가격 후보 생성
  2. 15개 중 4개 무작위 추첨
  3. 4개 평균 = 예정가격

C(15,4) = 1,365개 모든 조합의 평균을 계산 → 빈도 분포
→ 가장 자주 나오는 금액 구간 = 예정가격 집중 구간
"""
from itertools import combinations
from collections import Counter
from typing import Optional, List


def _round_unit(amount: int) -> int:
    """계약 규모별 반올림 단위 (나라장터 관행)"""
    if amount < 100_000_000:       return 1_000       # 1억 미만: 천원
    elif amount < 1_000_000_000:   return 10_000      # 1억~10억: 만원
    elif amount < 10_000_000_000:  return 100_000     # 10억~100억: 십만원
    else:                          return 1_000_000   # 100억 이상: 백만원


def calc_yega_frequency(
    base_amount: int,
    a_value: Optional[int] = None,
    srate_center: Optional[float] = None,
    spread_half: float = 0.028,
) -> dict:
    """
    복수예가 예비가격 C(15,4) 조합 빈도 분석.

    Args:
        base_amount  : 기초금액 (원)
        a_value      : A값(예비가격 기초금액, 원). 없으면 srate_center 추정
        srate_center : 사정율 예측값. a_value 없을 때 center 계산에 사용

    Returns dict:
        candidates        : 15개 예비가격 후보 (금액 + 기초금액 대비 비율)
        frequency         : 빈도 분포 전체 (확률 내림차순)
        top10             : 상위 10개
        total_combinations: 1365
        recommended_rate  : 최빈 구간 기초금액 대비 비율
        floor_rate        : 낙찰하한율
        round_unit        : 사용된 반올림 단위
        a_value_used      : 실제 사용된 A값
    """
    # ── A값 결정 ──
    if a_value and a_value > 0:
        center = int(a_value)
    elif srate_center and srate_center > 0:
        center = int(base_amount * srate_center)
    else:
        center = int(base_amount * 0.8876)  # 복수예가 실측 기반 기본값

    ru = _round_unit(center)

    # ── 15개 예비가격 후보 생성 (A값 ±spread_half, 균등 간격) ──
    # spread_half 실측값: inpo21c 데이터 기준 ±2.8% (기존 이론값 ±2.0%)
    lo = center * (1.0 - spread_half)
    hi = center * (1.0 + spread_half)
    candidates_raw = []
    for k in range(15):
        raw = lo + (hi - lo) * k / 14.0
        rounded = round(raw / ru) * ru
        candidates_raw.append(int(rounded))

    # ── C(15,4) = 1,365 조합 → 각 평균 계산 ──
    avg_list: list[int] = []
    for combo in combinations(range(15), 4):
        s = sum(candidates_raw[i] for i in combo)
        avg = round((s / 4) / ru) * ru
        avg_list.append(int(avg))

    total = len(avg_list)  # 1365

    # ── 빈도 집계 ──
    freq: Counter = Counter(avg_list)

    rows = []
    for amount, count in sorted(freq.items(), key=lambda x: x[1], reverse=True):
        rate = amount / base_amount
        rows.append({
            "amount":      amount,
            "rate":        round(rate, 6),
            "rate_pct":    round(rate * 100, 4),
            "count":       count,
            "probability": round(count / total * 100, 2),
        })

    # 누적 확률
    cum = 0.0
    for r in rows:
        cum += r["probability"]
        r["cumulative_prob"] = round(cum, 2)

    # ── 차트용 bin 집계 (0.001 단위로 묶어 막대 수 축소) ──
    bin_counter: Counter = Counter()
    for amount in avg_list:
        rate = amount / base_amount
        bin_key = round(rate, 3)
        bin_counter[bin_key] += 1

    chart_bins = [
        {"rate_pct": round(k * 100, 2), "count": v}
        for k, v in sorted(bin_counter.items())
    ]

    recommended = rows[0]["amount"] if rows else center
    recommended_rate = round(recommended / base_amount, 6)

    return {
        "base_amount":       base_amount,
        "a_value_used":      center,
        "round_unit":        ru,
        "candidates": [
            {"idx": i + 1, "amount": c, "rate": round(c / base_amount, 6)}
            for i, c in enumerate(candidates_raw)
        ],
        "frequency":          rows,
        "top10":              rows[:10],
        "chart_bins":         chart_bins,
        "total_combinations": total,
        "recommended_rate":   recommended_rate,
        "floor_rate":         0.87745,
    }


def get_agency_yega_pattern(bid_data: List[dict]) -> dict:
    """
    발주처 특화 예가 번호 빈도 패턴 분석.

    낙찰 사정율 → C(15,4) 역산으로 자주 선택된 예비가격 번호(1~15)를 추출.

    Args:
        bid_data: list of {"assessment_rate": float, "base_amount": int, "a_value": int|None}

    Returns:
        {pattern: [{number, freq_pct}], top3_numbers, dominant_zone, sample_count}
    """
    if not bid_data:
        return {"pattern": [], "top3_numbers": [], "dominant_zone": None, "sample_count": 0}

    index_counter: Counter = Counter()
    sample_count = 0

    for row in bid_data:
        assessment_rate = float(row.get("assessment_rate", 0) or 0)
        base_amount = int(row.get("base_amount", 0) or 0)
        a_value = row.get("a_value")

        if base_amount <= 0 or assessment_rate <= 0:
            continue

        # A값 결정: 명시값 우선, 없으면 사정율 역산
        if a_value and int(a_value) > 0:
            center = int(a_value)
        else:
            center = int(base_amount * assessment_rate)

        if center <= 0:
            continue

        ru = _round_unit(center)

        # 15개 예비가격 후보 생성
        candidates = []
        for k in range(15):
            raw = center * (0.98 + k * 0.04 / 14.0)
            candidates.append(int(round(raw / ru) * ru))

        # 관찰된 예정가격 (사정율 × 기초금액)
        target = int(round(assessment_rate * base_amount / ru) * ru)

        # 관찰값과 일치하는 C(15,4) 조합의 번호 집계
        matched = False
        for combo in combinations(range(15), 4):
            s = sum(candidates[i] for i in combo)
            avg = int(round((s / 4) / ru) * ru)
            if abs(avg - target) <= ru:
                for idx in combo:
                    index_counter[idx + 1] += 1  # 1-indexed
                matched = True

        if matched:
            sample_count += 1

    if not index_counter or sample_count == 0:
        return {"pattern": [], "top3_numbers": [], "dominant_zone": None, "sample_count": 0}

    total_hits = sum(index_counter.values())
    pattern = sorted(
        [{"number": num, "freq_pct": round(cnt / total_hits * 100, 1)}
         for num, cnt in index_counter.items()],
        key=lambda x: x["freq_pct"],
        reverse=True,
    )

    # 빠진 번호 0%로 채움
    present = {p["number"] for p in pattern}
    for n in range(1, 16):
        if n not in present:
            pattern.append({"number": n, "freq_pct": 0.0})
    pattern.sort(key=lambda x: x["freq_pct"], reverse=True)

    top3_numbers = [p["number"] for p in pattern[:3]]

    avg_top3 = sum(top3_numbers) / len(top3_numbers)
    if avg_top3 <= 5:
        dominant_zone = "low"
    elif avg_top3 <= 10:
        dominant_zone = "mid"
    else:
        dominant_zone = "high"

    return {
        "pattern":       pattern,
        "top3_numbers":  top3_numbers,
        "dominant_zone": dominant_zone,
        "sample_count":  sample_count,
    }


def load_inpo21c_yega_stats(db, agency_id: int) -> dict:
    """
    inpo21c_yega 실측 통계 조회.
    - 기관별 yega spread (base_ratio 분포)
    - position 추첨 빈도 (1~15번 위치별 is_selected 비율)

    Returns:
        spread_half  : 실측 반확산 (default 0.028)
        pos_weights  : 15개 위치별 추첨 가중치 (합=1.0)
        sample_n     : 샘플 수
    """
    from sqlalchemy import text as _text

    # 1. 기관별 yega spread
    spread_row = db.execute(_text("""
        SELECT
            STDDEV(iy.base_ratio / 100.0) AS spread_std,
            PERCENTILE_CONT(0.02) WITHIN GROUP(ORDER BY iy.base_ratio / 100.0) AS p02,
            PERCENTILE_CONT(0.98) WITHIN GROUP(ORDER BY iy.base_ratio / 100.0) AS p98,
            COUNT(*) AS n
        FROM inpo21c_yega iy
        JOIN inpo21c_bids ib USING (inpo21c_bid_id)
        JOIN agencies a ON a.name = ib.agency_name
        WHERE a.id = :aid
    """), {"aid": agency_id}).fetchone() if agency_id else None

    spread_half = 0.028  # inpo21c 전국 실측 기본값
    if spread_row and spread_row[1] is not None and spread_row[2] is not None:
        measured = (abs(float(spread_row[1])) + abs(float(spread_row[2]))) / 2
        if measured > 0.010:
            spread_half = round(measured, 4)

    # 2. position 추첨 빈도 (is_selected=TRUE 위치별)
    pos_rows = db.execute(_text("""
        SELECT iy.yega_no, COUNT(*) AS cnt
        FROM inpo21c_yega iy
        JOIN inpo21c_bids ib USING (inpo21c_bid_id)
        JOIN agencies a ON a.name = ib.agency_name
        WHERE a.id = :aid AND iy.is_selected = TRUE
        GROUP BY iy.yega_no
        ORDER BY iy.yega_no
    """), {"aid": agency_id}).fetchall() if agency_id else []

    pos_weights = None
    if pos_rows and sum(r[1] for r in pos_rows) >= 20:
        total = sum(r[1] for r in pos_rows)
        raw   = {r[0]: r[1] / total for r in pos_rows}
        uniform = 1.0 / 15
        # 관측값과 균등분포 블렌딩 (과적합 방지)
        n_bids = total // 4
        alpha  = min(0.6, n_bids / (n_bids + 30))
        pos_weights = [
            alpha * raw.get(i, 0.0) + (1 - alpha) * uniform
            for i in range(1, 16)
        ]
        s = sum(pos_weights)
        pos_weights = [w / s for w in pos_weights]

    return {
        "spread_half": spread_half,
        "pos_weights": pos_weights,
        "sample_n":    int(spread_row[3]) if spread_row and spread_row[3] else 0,
    }


def get_position_bid_recommendation(
    db,
    agency_id: int,
    a_value: int,
    base_amount: int,
    floor_rate: float = 0.87745,
    spread_half: float = 0.028,
    period_months: int = 24,
) -> dict:
    """
    A값 추첨 포지션 이력 기반 최적 투찰율 계산.

    핵심 로직:
      1. 기관별 is_selected=TRUE 포지션 빈도 조회 (inpo21c_yega)
      2. 상위 빈도 포지션 조합이 만드는 예정가격(사정율) 계산
      3. 낙찰하한 고려하여 최적 투찰율 반환

    Returns:
        recommended_rate    : 포지션 기반 권장 투찰율 (기초금액 대비)
        recommended_amount  : 권장 투찰금액 (원)
        expected_srate      : 예상 사정율 (예정가격/기초금액)
        top_positions       : 상위 추첨 포지션 번호 (1~15)
        position_pattern    : 15개 포지션별 선택 빈도 (%)
        confidence          : 신뢰도 (0~1, 샘플 수 기반)
        sample_count        : 분석에 사용된 입찰 건수
        data_source         : agency | national | fallback
    """
    from sqlalchemy import text as _text
    from itertools import combinations as _comb

    # ── 1. 포지션 빈도 조회 (기관별 → 전국 fallback) ─────────
    def _query_positions(aid):
        return db.execute(_text("""
            SELECT iy.yega_no, COUNT(*) AS cnt
            FROM inpo21c_yega iy
            JOIN inpo21c_bids ib USING (inpo21c_bid_id)
            JOIN agencies a ON (
                TRIM(a.name) = TRIM(ib.agency_name)
                OR TRIM(ib.agency_name) LIKE '%%' || TRIM(a.name) || '%%'
                OR TRIM(a.name) LIKE '%%' || TRIM(ib.agency_name) || '%%'
            )
            WHERE a.id = :aid AND iy.is_selected = TRUE
              AND ib.open_datetime >= NOW() - INTERVAL :period
            GROUP BY iy.yega_no
            ORDER BY iy.yega_no
        """), {"aid": aid, "period": f"'{period_months} months'"}).fetchall() if aid else []

    data_source = "fallback"
    pos_rows = _query_positions(agency_id) if agency_id else []
    total_selections = sum(r[1] for r in pos_rows)

    if total_selections >= 20:  # 기관별 데이터 충분
        data_source = "agency"
    else:  # 전국 fallback
        pos_rows = db.execute(_text("""
            SELECT yega_no, COUNT(*) AS cnt
            FROM inpo21c_yega
            WHERE is_selected = TRUE
            GROUP BY yega_no ORDER BY yega_no
        """)).fetchall()
        total_selections = sum(r[1] for r in pos_rows)
        data_source = "national" if total_selections > 0 else "fallback"

    # ── 2. 포지션별 빈도 계산 ──────────────────────────────
    freq_map = {r[0]: r[1] for r in pos_rows}
    total = max(total_selections, 1)
    position_pattern = [
        {"position": n, "freq_pct": round(freq_map.get(n, 0) / total * 100, 1)}
        for n in range(1, 16)
    ]
    position_pattern.sort(key=lambda x: x["freq_pct"], reverse=True)
    top_positions = [p["position"] for p in position_pattern[:4]]

    # ── 3. A값 범위에서 15개 예비가격 생성 ──────────────────
    ru = _round_unit(a_value)
    lo = a_value * (1.0 - spread_half)
    hi = a_value * (1.0 + spread_half)
    candidates = [
        int(round((lo + (hi - lo) * k / 14.0) / ru) * ru)
        for k in range(15)
    ]

    # ── 4. 상위 포지션 조합의 기대 사정율 계산 ───────────────
    # 빈도 가중치로 C(15,4) 조합 샘플링 → 기대 평균 계산
    weights = [freq_map.get(i + 1, 0.001) for i in range(15)]
    total_w = sum(weights)
    weights = [w / total_w for w in weights]

    combo_srates = []
    for combo in _comb(range(15), 4):
        combo_weight = sum(weights[i] for i in combo)
        avg_amount = sum(candidates[i] for i in combo) / 4
        srate = avg_amount / base_amount
        combo_srates.append((srate, combo_weight))

    # 가중 평균 사정율
    total_cw = sum(cw for _, cw in combo_srates)
    expected_srate = sum(sr * cw for sr, cw in combo_srates) / total_cw if total_cw > 0 else 0.90

    # 상위 빈도 포지션 조합의 사정율 (top4 positions)
    top_avg = sum(candidates[p - 1] for p in top_positions) / 4
    top_srate = top_avg / base_amount

    # 두 값 블렌딩 (신뢰도에 따라 가중치 다르게)
    n_bids = total_selections // 4
    alpha = min(0.75, n_bids / (n_bids + 20))  # 샘플 많을수록 top_srate 신뢰
    blended_srate = alpha * top_srate + (1 - alpha) * expected_srate

    # ── 5. 최적 투찰율 = 낙찰하한 직상 + 여유 ─────────────
    eff_floor = floor_rate * blended_srate
    recommended_rate = round(eff_floor + 0.0005, 6)
    recommended_amount = int(recommended_rate * base_amount)

    # ── 6. 신뢰도 ─────────────────────────────────────────
    confidence = round(min(0.90, alpha * (0.5 + min(n_bids, 50) / 100)), 3)

    return {
        "recommended_rate":   recommended_rate,
        "recommended_amount": recommended_amount,
        "expected_srate":     round(blended_srate, 6),
        "top_positions":      top_positions,
        "position_pattern":   position_pattern,
        "confidence":         confidence,
        "sample_count":       n_bids,
        "data_source":        data_source,
        "eff_floor":          round(eff_floor, 6),
    }


def get_inpo21c_pattern_direct(db, agency_id: int) -> dict:
    """
    inpo21c is_selected 데이터로 기관별 복수예가 추첨 패턴 직접 조회.
    get_agency_yega_pattern()의 역산 방식 대신 실측 DB 값 사용.
    """
    from sqlalchemy import text as _text

    rows = db.execute(_text("""
        SELECT iy.yega_no, COUNT(*) AS cnt
        FROM inpo21c_yega iy
        JOIN inpo21c_bids ib USING (inpo21c_bid_id)
        JOIN agencies a ON a.name = ib.agency_name
        WHERE a.id = :aid AND iy.is_selected = TRUE
        GROUP BY iy.yega_no
    """), {"aid": agency_id}).fetchall() if agency_id else []

    if not rows:
        return {"pattern": [], "top3_numbers": [], "dominant_zone": None, "sample_count": 0}

    total = sum(r[1] for r in rows)
    if total < 4:
        return {"pattern": [], "top3_numbers": [], "dominant_zone": None, "sample_count": 0}

    freq_map = {r[0]: r[1] for r in rows}
    pattern = sorted(
        [{"number": n, "freq_pct": round(freq_map.get(n, 0) / total * 100, 1)}
         for n in range(1, 16)],
        key=lambda x: x["freq_pct"],
        reverse=True,
    )
    top3 = [p["number"] for p in pattern[:3]]
    avg_top3 = sum(top3) / 3
    zone = "low" if avg_top3 <= 5 else "high" if avg_top3 > 10 else "mid"

    return {
        "pattern":       pattern,
        "top3_numbers":  top3,
        "dominant_zone": zone,
        "sample_count":  total // 4,
    }

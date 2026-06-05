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

    # ── 15개 예비가격 후보 생성 (A값 ±2%, 균등 간격) ──
    candidates_raw = []
    for k in range(15):
        raw = center * (0.98 + k * 0.04 / 14.0)
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

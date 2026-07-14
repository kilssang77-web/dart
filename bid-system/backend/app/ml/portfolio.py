"""
E7: 입찰 포트폴리오 최적화 엔진

목표: 이번 주 어떤 공고 조합에 투찰해야 수주건수가 최대인가?

핵심 통찰:
  개별 공고를 독립적으로 평가하는 것으로는 부족하다.
  보증한도, 인력, 동시 진행 건수 제약 하에서
  전체 포트폴리오의 기대 수주건수를 최대화해야 한다.

알고리즘:
  0-1 Knapsack + 그리디 근사
  (공고 수 <= 20이면 DP로 정확 풀이, 초과 시 그리디)

목표함수:
  Maximize: Σ (qualify_prob × win_prob × select_i)   ← 기대 수주건수
  Subject to:
    Σ bond_exposure × select_i ≤ remaining_bond
    Σ select_i ≤ max_concurrent_bids - active_bids
    select_i ∈ {0, 1}
    select_i = 0 if verdict == NO_GO
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
import math


@dataclass
class PortfolioBidItem:
    """포트폴리오 최적화 입력 — 공고 1건"""
    bid_id:           int
    title:            str
    base_amount:      int
    bid_date:         str             # ISO date string

    # E1 선별 결과
    verdict:          str             # GO / WATCH / NO_GO
    selection_score:  float           # 0~10
    ev_score:         int             # 기대가치 (원)

    # 확률
    qualify_prob:     float           # 적격 통과 확률
    win_prob:         float           # 낙찰 확률

    # 제약
    bond_exposure:    int             # 보증 소요액 (base_amount 기준)
    prep_hours:       float = 4.0     # 서류 준비 시간 (시간)

    # 추천 투찰률
    recommended_rate: float = 0.0


@dataclass
class PortfolioConstraints:
    """포트폴리오 제약 조건"""
    remaining_bond:      int    # 사용 가능 보증한도 잔액 (원)
    max_concurrent_bids: int    # 최대 동시 진행 건수
    active_bid_count:    int    # 현재 진행중 건수
    weekly_prep_hours:   float  # 주간 서류 준비 가용 시간
    monthly_target:      int    # 월 수주 목표
    current_month_wins:  int    # 현재 수주 건수


@dataclass
class PortfolioPlan:
    """포트폴리오 최적화 결과"""
    selected:             List[PortfolioBidItem]
    not_selected:         List[PortfolioBidItem]  # verdict != NO_GO 중 미선택
    no_go_list:           List[PortfolioBidItem]

    expected_wins:        float   # 기대 수주 건수
    expected_win_amount:  int     # 기대 수주 금액
    total_ev:             int     # 총 기대가치
    bond_usage:           int     # 선택 공고 보증 소요액 합계
    remaining_bond_after: int

    alerts:               List[str] = field(default_factory=list)
    schedule:             List[Dict] = field(default_factory=list)


def _expected_wins(item: PortfolioBidItem) -> float:
    """단일 공고의 기대 수주 기여도"""
    return item.qualify_prob * item.win_prob


def _knapsack_dp(
    items: List[PortfolioBidItem],
    capacity_bond: int,
    capacity_count: int,
) -> List[PortfolioBidItem]:
    """
    0-1 Knapsack DP (공고 수 <= 20일 때 사용).
    2차원 DP: bond 용량 × 건수 용량
    """
    n = len(items)
    # bond를 100만 원 단위로 버킷화 (메모리 제한)
    unit = 1_000_000
    cap_b = min(capacity_bond // unit, 200)  # 최대 200 버킷

    # dp[i][j] = i번째 공고까지 검토, bond j버킷 이하, 건수 제한 내 → 최대 기대수주건수
    # 공간 최적화: 1D DP + count 제약은 greedy로 근사
    dp = [0.0] * (cap_b + 1)
    chosen = [[False] * (cap_b + 1) for _ in range(n)]

    for i, item in enumerate(items):
        b_cost = min(cap_b, item.bond_exposure // unit)
        w      = _expected_wins(item)
        for j in range(cap_b, b_cost - 1, -1):
            if dp[j - b_cost] + w > dp[j]:
                dp[j] = dp[j - b_cost] + w
                chosen[i][j] = True

    # 역추적
    selected_idx = set()
    j = cap_b
    for i in range(n - 1, -1, -1):
        if chosen[i][j]:
            selected_idx.add(i)
            j -= min(cap_b, items[i].bond_exposure // unit)
        if j <= 0:
            break

    # 건수 제약 적용
    result = [items[i] for i in selected_idx]
    result.sort(key=_expected_wins, reverse=True)
    return result[:capacity_count]


def _greedy(
    items: List[PortfolioBidItem],
    capacity_bond: int,
    capacity_count: int,
) -> List[PortfolioBidItem]:
    """그리디 근사 — 기대가치/보증액 비율 기준 정렬 후 선택"""
    def ratio(item: PortfolioBidItem) -> float:
        cost = max(item.bond_exposure, 1)
        return _expected_wins(item) * 1e12 / cost

    candidates = sorted(items, key=ratio, reverse=True)
    selected: List[PortfolioBidItem] = []
    used_bond = 0

    for item in candidates:
        if len(selected) >= capacity_count:
            break
        if used_bond + item.bond_exposure <= capacity_bond:
            selected.append(item)
            used_bond += item.bond_exposure

    return selected


def optimize(
    items: List[PortfolioBidItem],
    constraints: PortfolioConstraints,
) -> PortfolioPlan:
    """
    주간 포트폴리오 최적화 메인 함수.

    1. NO_GO 항목 제외
    2. WATCH 항목: GO보다 낮은 우선순위로 처리
    3. 보증한도 + 건수 제약 하에서 기대 수주건수 최대화
    """
    # 선별 가능한 항목 (GO + WATCH)
    eligible = [i for i in items if i.verdict in ("GO", "WATCH")]
    no_go    = [i for i in items if i.verdict == "NO_GO"]

    # WATCH 항목은 ev_score에 페널티 적용
    for item in eligible:
        if item.verdict == "WATCH":
            item.win_prob    *= 0.8   # 불확실성 반영
            item.qualify_prob *= 0.9

    available_count = max(0, constraints.max_concurrent_bids - constraints.active_bid_count)

    if not eligible or available_count == 0:
        return PortfolioPlan(
            selected=[],
            not_selected=eligible,
            no_go_list=no_go,
            expected_wins=0.0,
            expected_win_amount=0,
            total_ev=0,
            bond_usage=0,
            remaining_bond_after=constraints.remaining_bond,
            alerts=["투찰 가능 슬롯 없음 또는 GO/WATCH 공고 없음"],
        )

    # DP vs 그리디 선택
    if len(eligible) <= 20:
        selected = _knapsack_dp(eligible, constraints.remaining_bond, available_count)
    else:
        selected = _greedy(eligible, constraints.remaining_bond, available_count)

    not_selected = [i for i in eligible if i not in selected]

    # 집계
    expected_wins  = sum(_expected_wins(i) for i in selected)
    total_ev       = sum(i.ev_score for i in selected)
    bond_usage     = sum(i.bond_exposure for i in selected)
    expected_amount = sum(int(i.base_amount * i.win_prob * i.qualify_prob) for i in selected)

    # 경고 생성
    alerts: List[str] = []
    remaining_after = constraints.remaining_bond - bond_usage
    if remaining_after < 0:
        alerts.append("⚠️  보증한도 초과 — 선택 공고 재검토 필요")
    if constraints.remaining_bond > 0:
        usage_rate = bond_usage / constraints.remaining_bond
        if usage_rate > 0.8:
            alerts.append(f"보증한도 {usage_rate:.0%} 사용 예정 — 여유 확보 권장")

    remaining_wins = constraints.monthly_target - constraints.current_month_wins
    if expected_wins < remaining_wins * 0.5:
        alerts.append(
            f"이달 수주 목표 달성 가능성 낮음 "
            f"(목표 {remaining_wins}건 남음, 기대 수주 {expected_wins:.1f}건)"
        )

    # 일정 생성
    schedule = _build_schedule(selected)

    return PortfolioPlan(
        selected=selected,
        not_selected=not_selected,
        no_go_list=no_go,
        expected_wins=round(expected_wins, 2),
        expected_win_amount=expected_amount,
        total_ev=total_ev,
        bond_usage=bond_usage,
        remaining_bond_after=remaining_after,
        alerts=alerts,
        schedule=schedule,
    )


def _build_schedule(selected: List[PortfolioBidItem]) -> List[Dict]:
    """투찰 일정 생성 — 날짜별 그룹"""
    from collections import defaultdict
    by_date = defaultdict(list)
    for item in selected:
        by_date[item.bid_date].append({
            "bid_id":           item.bid_id,
            "title":            item.title[:30],
            "base_amount":      item.base_amount,
            "recommended_rate": item.recommended_rate,
            "win_prob":         item.win_prob,
        })
    return [
        {"date": d, "bids": bids}
        for d, bids in sorted(by_date.items())
    ]


def compute_portfolio_stats(plan: PortfolioPlan) -> Dict:
    """포트폴리오 요약 통계"""
    selected = plan.selected
    if not selected:
        return {}

    win_probs = [i.win_prob for i in selected]
    return {
        "count":              len(selected),
        "expected_wins":      plan.expected_wins,
        "avg_win_prob":       round(sum(win_probs) / len(win_probs), 4),
        "max_win_prob":       round(max(win_probs), 4),
        "min_win_prob":       round(min(win_probs), 4),
        "total_base_amount":  sum(i.base_amount for i in selected),
        "expected_win_amount": plan.expected_win_amount,
        "bond_usage":         plan.bond_usage,
        "remaining_bond":     plan.remaining_bond_after,
    }

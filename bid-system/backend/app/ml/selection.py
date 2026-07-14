"""
E1: 공고 선별 엔진

목표: GO / NO_GO / WATCH 판정
      이길 수 없는 싸움에 투찰 자원을 낭비하지 않는다.

원칙:
  - Hard Filter 하나라도 걸리면 즉시 NO_GO
  - 통과 시 EV(기대가치) 기반 종합 점수 산출
  - GO: 점수 6.0 이상, WATCH: 3.5~6.0, NO_GO: 3.5 미만

목표함수 기여:
  낮은 승률 공고 제외 → 투찰 효율(수주율) 향상
  보증한도 초과 제외 → 재무 리스크 제거
  적격 불가 제외 → 헛수고 완전 방지
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import math


# ── 가중치 ─────────────────────────────────────────────────────────
SCORE_WEIGHTS = {
    "ev_normalized":    0.35,
    "win_prob":         0.20,
    "qualify_prob":     0.20,
    "strategic_fit":    0.15,
    "competition_ease": 0.10,
}

GO_THRESHOLD    = 6.0
WATCH_THRESHOLD = 3.5

# Hard filter 기본값
MIN_QUALIFY_PROB    = 0.50   # 적격 통과 확률 50% 미만 → NO_GO
MAX_COMPETITOR_STR  = 8.5    # 경쟁강도 8.5 초과 → NO_GO (강자 독식 시장)
MAX_BOND_USAGE_RATE = 0.90   # 보증한도 사용률 90% 초과 → NO_GO


@dataclass
class SelectionInput:
    """공고 선별에 필요한 입력 데이터 (서비스 레이어에서 조립)"""
    bid_id:               int
    base_amount:          int
    agency_id:            int
    industry_id:          Optional[int]
    region_id:            Optional[int]

    # 적격 정보
    license_match:        bool = True
    region_restriction_ok: bool = True
    qualify_prob:         float = 0.8

    # 경쟁 정보
    expected_competitor_count: int = 5
    competitor_strength_score: float = 5.0
    strong_competitor_count:   int = 0

    # 예측 정보
    best_win_prob:        float = 0.30
    estimated_margin:     float = 0.05

    # 전략 부합도
    in_target_region:     bool = False
    in_target_industry:   bool = False

    # 회사 역량
    bond_limit_total:     int = 0
    bond_limit_used:      int = 0
    max_concurrent_bids:  int = 5
    current_active_bids:  int = 0

    # 과거 이력 (이 기관+공종)
    historical_win_rate:  float = 0.20


@dataclass
class SelectionResult:
    verdict:         str             # GO / NO_GO / WATCH
    score:           float           # 0~10
    ev_score:        int             # 기대가치 (원)
    qualify_prob:    float
    win_prob_best:   float
    expected_margin: float
    competitor_risk: str             # LOW / MEDIUM / HIGH
    no_go_reasons:   List[str] = field(default_factory=list)
    score_detail:    Dict[str, float] = field(default_factory=dict)
    recommended_strategy: str = "balanced"


def _competitor_risk_label(strength: float) -> str:
    if strength >= 7.0: return "HIGH"
    if strength >= 4.0: return "MEDIUM"
    return "LOW"


def _normalize_ev(ev: int, base_amount: int) -> float:
    """기대가치를 0~10 점수로 정규화 (기초금액 대비 비율 기반)"""
    if base_amount <= 0:
        return 5.0
    ratio = ev / base_amount  # 기초금액 대비 기대가치 비율
    # 5% 이상이면 10점, 0% 이하면 0점 — 선형
    score = min(10.0, max(0.0, ratio / 0.05 * 10))
    return score


def _strategic_fit_score(inp: SelectionInput) -> float:
    score = 5.0  # 기본값
    if inp.in_target_region:    score += 2.0
    if inp.in_target_industry:  score += 2.0
    if inp.historical_win_rate >= 0.35: score += 1.0  # 이 기관에서 잘 낸 이력
    return min(10.0, score)


def _competition_ease_score(inp: SelectionInput) -> float:
    """경쟁이 약할수록 높은 점수 (역수)"""
    strength = inp.competitor_strength_score
    ease = max(0.0, 10.0 - strength)
    # 강자 경쟁사 수만큼 추가 페널티
    ease -= inp.strong_competitor_count * 0.5
    return max(0.0, min(10.0, ease))


def evaluate(inp: SelectionInput) -> SelectionResult:
    """
    공고 선별 평가 메인 함수.

    Returns:
        SelectionResult with verdict GO / NO_GO / WATCH
    """
    no_go_reasons: List[str] = []

    # ── Hard Filters ────────────────────────────────────────────────
    if not inp.license_match:
        no_go_reasons.append("license_mismatch:보유 면허 없음")

    if not inp.region_restriction_ok:
        no_go_reasons.append("region_restricted:지역 제한 불충족")

    if inp.qualify_prob < MIN_QUALIFY_PROB:
        no_go_reasons.append(
            f"low_qualify_prob:적격통과확률 {inp.qualify_prob:.0%} (기준 {MIN_QUALIFY_PROB:.0%})"
        )

    if inp.bond_limit_total > 0:
        usage_rate = inp.bond_limit_used / inp.bond_limit_total
        if usage_rate > MAX_BOND_USAGE_RATE:
            no_go_reasons.append(
                f"bond_limit:보증한도 {usage_rate:.0%} 사용 중 (기준 {MAX_BOND_USAGE_RATE:.0%})"
            )
        if inp.bond_limit_used + inp.base_amount > inp.bond_limit_total:
            no_go_reasons.append("bond_overflow:이 공고 투찰 시 보증한도 초과")

    if inp.current_active_bids >= inp.max_concurrent_bids:
        no_go_reasons.append(
            f"capacity_full:동시 투찰 한도 초과 ({inp.current_active_bids}/{inp.max_concurrent_bids})"
        )

    if inp.competitor_strength_score > MAX_COMPETITOR_STR:
        no_go_reasons.append(
            f"dominant_competition:경쟁강도 {inp.competitor_strength_score:.1f} (기준 {MAX_COMPETITOR_STR})"
        )

    if no_go_reasons:
        return SelectionResult(
            verdict="NO_GO",
            score=0.0,
            ev_score=0,
            qualify_prob=inp.qualify_prob,
            win_prob_best=inp.best_win_prob,
            expected_margin=inp.estimated_margin,
            competitor_risk=_competitor_risk_label(inp.competitor_strength_score),
            no_go_reasons=no_go_reasons,
        )

    # ── 기대가치(EV) 계산 ──────────────────────────────────────────
    ev = int(
        inp.qualify_prob
        * inp.best_win_prob
        * inp.base_amount
        * inp.estimated_margin
    )

    # ── 점수 계산 ──────────────────────────────────────────────────
    sub_scores = {
        "ev_normalized":    _normalize_ev(ev, inp.base_amount),
        "win_prob":         inp.best_win_prob * 10,
        "qualify_prob":     inp.qualify_prob * 10,
        "strategic_fit":    _strategic_fit_score(inp),
        "competition_ease": _competition_ease_score(inp),
    }

    # 가중치 합 = 1.0, 각 sub_score 0~10 → total 0~10
    total_score = sum(
        sub_scores[k] * SCORE_WEIGHTS[k]
        for k in SCORE_WEIGHTS
    )

    # ── 판정 ──────────────────────────────────────────────────────
    if total_score >= GO_THRESHOLD:
        verdict = "GO"
    elif total_score >= WATCH_THRESHOLD:
        verdict = "WATCH"
    else:
        verdict = "NO_GO"
        no_go_reasons.append(
            f"low_score:종합점수 {total_score:.1f} (GO기준 {GO_THRESHOLD})"
        )

    # ── 권장 전략 결정 ─────────────────────────────────────────────
    recommended = _pick_strategy(inp, total_score)

    return SelectionResult(
        verdict=verdict,
        score=round(total_score, 2),
        ev_score=ev,
        qualify_prob=inp.qualify_prob,
        win_prob_best=inp.best_win_prob,
        expected_margin=inp.estimated_margin,
        competitor_risk=_competitor_risk_label(inp.competitor_strength_score),
        no_go_reasons=no_go_reasons,
        score_detail={k: round(v, 2) for k, v in sub_scores.items()},
        recommended_strategy=recommended,
    )


def _pick_strategy(inp: SelectionInput, score: float) -> str:
    """종합 점수 + 경쟁 상황 → 초기 전략 힌트 (E5에서 정밀 계산)"""
    if inp.competitor_strength_score >= 7.0:
        return "aggressive"   # 강경쟁 → 공격적 투찰 필요
    if score >= 8.0:
        return "conservative"  # 우위 확실 → 마진 우선
    if inp.historical_win_rate >= 0.35:
        return "balanced"      # 이력 좋음 → 균형
    return "balanced"


def batch_evaluate(inputs: List[SelectionInput]) -> List[SelectionResult]:
    """여러 공고 일괄 평가 — 결과 GO 점수 내림차순 정렬"""
    results = [(inp, evaluate(inp)) for inp in inputs]
    results.sort(key=lambda x: x[1].score, reverse=True)
    return [r for _, r in results]


def build_go_list_summary(
    results: List[SelectionResult],
    bid_ids: List[int],
) -> List[Dict[str, Any]]:
    """프론트엔드 GO 목록 렌더링용 요약 생성"""
    summary = []
    for bid_id, result in zip(bid_ids, results):
        summary.append({
            "bid_id":          bid_id,
            "verdict":         result.verdict,
            "score":           result.score,
            "ev_score":        result.ev_score,
            "qualify_prob":    result.qualify_prob,
            "win_prob_best":   result.win_prob_best,
            "competitor_risk": result.competitor_risk,
            "no_go_reasons":   result.no_go_reasons,
            "recommended_strategy": result.recommended_strategy,
        })
    return summary

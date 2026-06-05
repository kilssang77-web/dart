---
step: 2
name: "공고별 최종 추천 투찰가 종합 화면"
relevant_docs: ["PRD", "CODING_CONVENTION", "API_GUIDE", "SCHEMA"]
relevant_references: []
---

## 목표
공고 하나를 선택하면 모든 분석(사정율통계 + 프리즘 + 예가 + 트렌드 + 개인화)을 자동으로 합산해
"권장 투찰 사정율 X.XXXX (투찰가 XXX,XXX,XXX원)" 1개를 출력하는 종합 화면.

## 구현 상세

### Backend — FinalRecommendService (services.py 추가)
```
GET /api/v1/bids/{bid_id}/final-recommend
```
반환 구조:
```json
{
  "bid_id": 123,
  "base_amount": 274720000,
  "recommended_rate": 0.8876,
  "recommended_amount": 243,820,000,
  "confidence": "medium",  // high/medium/low (데이터 충분도 기반)
  "floor_rate": 0.87745,
  "strategies": {
    "balanced":    {"rate": 0.8876, "amount": 243820000, "win_prob": 0.32},
    "aggressive":  {"rate": 0.8821, "amount": 242310000, "win_prob": 0.18},
    "conservative":{"rate": 0.8931, "amount": 245330000, "win_prob": 0.41},
    "floor_safe":  {"rate": 0.8810, "amount": 241990000, "win_prob": 0.12}
  },
  "evidence": {
    "srate_stats": {"mean": 0.8876, "sample_count": 47, "trend_direction": "up"},
    "prism_top":   {"rate": 0.8880, "probability": 5.1},
    "yega_top":    {"rate": 0.8876, "probability": 5.05},
    "personal_bias": {"rate_diff_mean": -0.003, "applied": true}
  },
  "signal": "발주처 최근 사정율 상승 추세 → 균형형 이상 추천"
}
```

합산 로직:
1. 사정율 통계 (assessment_rate_stats) → 기준 mean 확보
2. 프리즘 top1 (prism.scan_prism_zones) → 검증
3. 예가 top1 (yega.calc_yega_frequency) → A값 추정 크로스체크
4. 트렌드 방향 (SrateTrendService) → up/down 보정 ±0.001
5. 개인화 편향 (my_bid_records.rate_diff 평균) → 보정값 반영
6. confidence = sample_count 기반 (50건↑ high, 10~50 medium, 10건미만 low)

### Frontend — TenderRecommendPage 신규
라우트: `/bids/:bidId/final-recommend`
BidDetailPage "투찰가 분석" 버튼 → 이 페이지로 이동

구성:
1. 상단: 공고 요약 (발주처, 공고명, 기초금액, 개찰일)
2. 핵심 카드: 권장 사정율 (크게 표시) + 투찰금액 + 신뢰도 배지
3. 4전략 비교표: 사정율 / 투찰금액 / 예상 낙찰확률 / 추천 여부
4. 근거 패널: 사정율통계·프리즘·예가 top값과 수렴 여부 표시
5. 경고 배너: 낙찰하한율 미달 시 빨간 경고

## 기존 시그니처 유지 vs 변경
- 기존 API 변경 없음, 새 엔드포인트 추가

## 사이드 이펙트
- services.py 코드 증가 (FinalRecommendService 클래스 추가)
- App.tsx 라우트 추가

## 마이그레이션
- DB 변경 없음

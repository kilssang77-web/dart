---
step: 4
name: "자사 승률 패턴 진단"
relevant_docs: ["PRD", "CODING_CONVENTION", "API_GUIDE", "SCHEMA"]
relevant_references: []
---

## 목표
my_bid_records(618건)를 분석하여 "우리 회사가 어디서 왜 지는가"를 진단하고
편향 방향을 자동 감지해 추천가에 반영.

## 구현 상세

### Backend
```
GET /api/v1/my-bids/win-pattern
```
반환:
```json
{
  "total": 618,
  "won": 5,
  "lost": 613,
  "overall_win_rate": 0.81,
  "bias": {
    "rate_diff_mean": -0.0031,
    "direction": "above",
    "signal": "평균 0.31%p 높게 투찰하는 경향 — 낮게 조정 권장"
  },
  "by_agency": [
    {"agency_name": "...", "total": 12, "won": 1, "win_rate": 8.3, "avg_rate_diff": -0.002}
  ],
  "by_industry": [...],
  "by_year": [...],
  "loss_reasons": {
    "above_winner": 487,
    "below_floor": 23,
    "below_winner": 103
  }
}
```

편향 계산:
- `rate_diff` = submitted_rate - actual_winner_rate
- 양수 = 높게 씀(above), 음수 = 낮게 씀(below)
- |mean| > 0.003이면 "편향 있음"으로 진단

### Frontend — MyBidsPage "성과 분석" 탭 추가
- 기존 탭: 투찰이력, 역산분석
- 추가 탭 "성과 분석":
  1. 편향 진단 카드 (크게) — "평균 X%p 높게 쓰는 경향" + 방향 화살표
  2. 패배 원인 도넛차트 (높게/낮게/하한미달 비율)
  3. 발주처별 승률 테이블 (10건 이상만 표시)
  4. 연도별 승률 추이 LineChart

## 기존 시그니처 유지
- /my-bids 기존 엔드포인트 변경 없음

## 마이그레이션
- DB 변경 없음 (my_bid_records 기존 컬럼 활용)

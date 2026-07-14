---
step: 6
name: "공동도급 적격심사 시뮬레이터 고도화"
relevant_docs: ["PRD", "CODING_CONVENTION", "API_GUIDE", "SCHEMA"]
relevant_references: []
---

## 목표
현재 JointQualService.find_matching_partners는 "적격 여부 판단"만 한다.
파트너 조합을 자유롭게 구성하고 지분율을 조정하면서 "심사통과 최저 투찰가"를 실시간 계산하는 시뮬레이터 추가.

## 구현 상세

### Backend
```
POST /api/v1/bids/{bid_id}/joint-simulate
Body: {
  "partners": [
    {"competitor_id": 4623, "participation_rate": 0.4},
    {"user_track": 500000000, "participation_rate": 0.6}  // 귀사
  ]
}
```
반환:
```json
{
  "bid_id": 145216,
  "bid_amount_required": 274720000,
  "partners": [
    {
      "name": "동성건설 주식회사",
      "participation_rate": 0.4,
      "track_amount": 1200000000,
      "qual_score": 8.5,
      "passes": true
    },
    ...
  ],
  "joint_result": {
    "passes": true,
    "total_qual_score": 17.2,
    "threshold": 12.0,
    "min_bid_amount": 241990000,
    "min_bid_rate": 0.881,
    "margin": 1990000
  }
}
```

### Frontend — 신규 JointSimPage (`/bids/:bidId/joint-sim`)
BidDetailPage "공동도급 시뮬레이터" 버튼으로 진입

구성:
1. 공고 요약 (기초금액, 적격심사 기준점수)
2. 파트너 구성 패널:
   - 귀사 행: 보유실적 입력, 지분율 슬라이더
   - 파트너 추가 버튼 → 경쟁사 검색(이름 또는 사업자번호) → 자동 실적 조회
   - 각 파트너 지분율 슬라이더 (합계 100% 실시간 표시)
3. 결과 패널 (실시간 계산):
   - 통과/미통과 대형 배지
   - 합산 점수 / 기준 점수
   - 심사통과하는 최저 투찰금액 & 사정율
   - 각 파트너 개별 기여 점수

## 기존 시그니처 유지
- /bids/{id}/joint-partners 기존 API 유지
- 새 /bids/{id}/joint-simulate 추가

## 마이그레이션
- DB 변경 없음

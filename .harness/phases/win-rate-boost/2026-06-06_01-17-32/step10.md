---
step: 10
name: "발주처 예가 패턴 탭 (AgencyDetailPage)"
relevant_docs: ["PRD", "CODING_CONVENTION", "API_GUIDE", "SCHEMA"]
relevant_references: []
---

## 목표
inpo21c_yega.is_selected 실측 데이터로 계산한 위치 가중치를
사용자가 직접 볼 수 있도록 AgencyDetailPage에 "예가패턴" 탭을 추가한다.

## 구현 상세

### Backend
GET /agencies/{agency_id}/yega-pattern
```json
{
  "agency_id": 377,
  "agency_name": "대전광역시",
  "sample_n": 26,
  "spread_half": 0.028,
  "pos_weights": [0.0712, ...],  // 15개 위치별 가중치 (합=1.0)
  "has_data": true
}
```

### Frontend — AgencyDetailPage "예가패턴" 탭
- TABS에 '예가패턴' 추가
- 15-bar chart: 위치별 추첨 확률 (균등=6.7% 점선 기준선)
- 상위 3개 위치: 파란 강조 + 퍼센트 레이블
- spread_half: "실측 예가 후보 범위 ±X.XX%" 표시
- 데이터 없으면 "수집된 예가 데이터 없음" 안내

## 기존 시그니처 유지
- 기존 탭 동작 유지
- DB 변경 없음

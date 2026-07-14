---
step: 5
name: "경쟁사 행동 예측 ML"
relevant_docs: ["PRD", "CODING_CONVENTION", "API_GUIDE", "SCHEMA"]
relevant_references: []
---

## 목표
inpo21c_participants(31,800건) 기반으로 특정 공고에 특정 경쟁사가:
1. 참여할 확률
2. 참여 시 어느 사정율 구간에 써올지 예측

## 구현 상세

### Backend — ml/competitor_predict.py 신규
```python
def predict_participation(competitor_id, bid: dict, db) -> dict:
    """경쟁사 공고 참여 확률 예측"""
    # 과거 같은 agency_id / industry_id 공고 참여 이력 기반
    # 참여율 = 해당 조건 공고 수 / 전체 해당 조건 공고 수

def predict_bid_zone(competitor_id, base_amount: int, db) -> dict:
    """참여 시 투찰 구간 분포 예측"""
    # inpo21c_participants의 base_ratio 분포 → 히스토그램
    # 금액 범위 필터 (±30% 이내)
```

```
GET /api/v1/competitors/{id}/predict?bid_id={bid_id}
```
반환:
```json
{
  "competitor_id": 4623,
  "competitor_name": "동성건설 주식회사",
  "bid_id": 145216,
  "participation": {
    "probability": 0.42,
    "basis": "동일 발주처 12건 중 5건 참여",
    "confidence": "medium"
  },
  "bid_zone": {
    "zones": [
      {"range_lo": 0.900, "range_hi": 0.905, "pct": 37.9},
      ...
    ],
    "peak_zone": {"range_lo": 0.900, "range_hi": 0.905},
    "sample_count": 140
  }
}
```

### Frontend — CompetitorPage "이 공고 예측" 기능
- CompetitorPage 상단에 공고 선택 드롭다운 추가 (공고 검색)
- 선택 시 해당 경쟁사의 참여확률 + 투찰구간 카드 표시
- "이 공고 경쟁사 분석" 버튼 → 상위 5개 경쟁사의 예측 결과 일괄 표시

## 기존 시그니처 유지
- /competitors 기존 엔드포인트 변경 없음

## 마이그레이션
- DB 변경 없음 (inpo21c_participants 기존 데이터 활용)

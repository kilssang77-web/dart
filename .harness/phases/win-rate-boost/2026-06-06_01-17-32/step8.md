---
step: 8
name: "투찰 추천 UI — 사정율 예측 신뢰도 + 실측 근거 표시"
relevant_docs: ["PRD", "CODING_CONVENTION", "API_GUIDE", "SCHEMA"]
relevant_references: []
---

## 목표
ML 예정가격 예측 정확도가 향상됐지만, 사용자에게 "왜 이 투찰률인가?" 근거가 보이지 않는다.
bid-range API에 신뢰도·근거 필드를 추가하고, TenderRecommendPage에 시각적으로 표시한다.

## 구현 상세

### Backend — bid-range API 응답 확장
```python
# GET /api/v1/recommend/bid-range 응답에 추가
{
  "srate_center": 0.9854,
  "srate_range": { "p10": ..., "p90": ... },
  "srate_source": "inpo21c",   # "inpo21c" | "lgbm" | "global"
  "inpo21c_n": 26,             # 0이면 inpo21c 데이터 없음
  "confidence": 0.88           # 0.0~1.0
}
```

- `predict_srate()` 반환값에 source, inpo21c_n 추가
- `BidRangeResponse` 스키마에 필드 추가

### Frontend — TenderRecommendPage 신뢰도 배지
1. **"실측 기반" 배지**: `srate_source === "inpo21c"` 이면 파란 배지 표시
   - "📊 inpo21c 실측 {n}건 기반" 텍스트
2. **신뢰도 프로그레스바**: confidence × 100% 바 + 퍼센트 표시
3. **근거 없음 안내**: `inpo21c_n === 0` 이면 "G2B 통계 기반 (실측 데이터 없음)" 회색 배지

## 기존 시그니처 유지
- BidRangeResponse 기존 필드 모두 유지 (nullable 신규 필드 추가)
- 기존 bid-range 호출 클라이언트 영향 없음

## 마이그레이션
- DB 변경 없음

---
step: 3
name: "발주처 심층분석 (사정율 히스토그램 + 개찰 타임라인)"
relevant_docs: ["PRD", "CODING_CONVENTION", "API_GUIDE"]
relevant_references: []
---

## 목표
AgencyDetailPage에 발주처별 사정율 분포(히스토그램)와 최근 개찰 타임라인을 추가하여
info21c 파워분석 수준의 발주처 심층분석 제공.

## 구현 상세

### Backend
```
GET /api/v1/agencies/{id}/srate-histogram?months=12
```
반환:
```json
{
  "agency_id": 123,
  "agency_name": "...",
  "months": 12,
  "sample_count": 47,
  "mean": 0.8876,
  "std": 0.0124,
  "bins": [
    {"range_lo": 0.870, "range_hi": 0.875, "count": 2, "pct": 4.3},
    ...
  ],
  "percentiles": {"p10": 0.871, "p25": 0.879, "p50": 0.888, "p75": 0.895, "p90": 0.903}
}
```

```
GET /api/v1/agencies/{id}/recent-results?limit=20
```
반환: 최근 낙찰 결과 목록 (날짜, 공고명, 기초금액, 낙찰사정율, 참여업체수)

### Frontend — AgencyDetailPage 탭 추가
- 기존: 개요, 공고목록
- 추가 탭 "심층분석":
  1. 사정율 히스토그램 (BarChart, 기간 6/12/24개월 토글)
     - 평균·중앙값 수직선 표시
     - 낙찰하한율(0.87745) 빨간 선 표시
  2. 개찰 타임라인 (ScatterChart, x=날짜 y=사정율)
     - 평균선 + 추세선 오버레이
  3. 통계 요약 카드: 평균/표준편차/P10~P90

## 기존 시그니처 유지
- 기존 /agencies 엔드포인트 변경 없음, 새 하위 경로 추가

## 마이그레이션
- DB 변경 없음 (bid_results 기존 데이터 활용)

---
relevant_docs: ["ARCHITECTURE", "PRD"]
relevant_references: ["infose_info21c"]
---

# Step 1: 사정율 빈도분석 강화

## 목표
기관·공종별 사정율 분포를 히스토그램 + 최빈값 마커 + 분위수로 시각화한다.

## 작업 내용

### Backend
1. `GET /stats/srate-distribution` 파라미터 확장
   - 파일: `bid-system/backend/app/api/v1/statistics.py`
   - `agency_id: int | None`, `industry_id: int | None`, `months: int = 24` 추가
   - `bid-system/backend/app/services.py` `StatisticsService.rate_distribution()` 수정
     - `assessment_rate`(사정율) 기반 히스토그램 bins 추가 반환
     - 응답에 `mode`(최빈 bin), `p25`, `p50`, `p75`, `mean`, `std`, `sample_count` 포함
2. `schemas.py`에 `SrateDistributionResponse` 모델 추가

### Frontend
3. `bid-system/frontend/src/api/index.ts` — `statsApi.srateDistribution(params?)` 추가
4. `bid-system/frontend/src/types/index.ts` — `SrateDistributionResponse` 타입 추가
5. `bid-system/frontend/src/pages/StatisticsPage.tsx` 수정
   - 기존 탭에 "사정율 분포" 탭 추가
   - 기관/공종 드롭다운 필터 (meta API 활용)
   - Recharts `BarChart` — X축: 사정율 구간(%), Y축: 건수
   - 최빈값 `ReferenceLine` (빨간 점선)
   - 분위수 박스(p25~p75 범위 강조 영역)
   - 통계 요약 카드 (평균, 최빈값, 표준편차, 샘플수)

## Acceptance Criteria
- [ ] `/stats/srate-distribution?agency_id=1&months=12` 호출 시 히스토그램 bins + mode + 분위수 반환
- [ ] StatisticsPage "사정율 분포" 탭에서 기관/공종 선택 후 차트 갱신 확인
- [ ] 최빈값 마커가 차트에 표시됨
- [ ] 빌드 오류 없음 (`uvicorn` 기동 + `vite build` 통과)

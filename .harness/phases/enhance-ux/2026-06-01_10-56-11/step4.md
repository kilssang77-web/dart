---
relevant_docs: ["ARCHITECTURE", "PRD"]
relevant_references: ["infose_info21c"]
---

# Step 2: 발주처 심층분석 페이지

## 목표
특정 발주기관의 낙찰 패턴·사정율 분포·주요 낙찰업체를 한 페이지에서 심층 분석한다.

## 작업 내용

### Backend
1. `GET /agencies` — 기관 목록 API 추가 (검색 가능)
   - 파일: `bid-system/backend/app/api/v1/` 에 `agencies.py` 신규
   - `GET /agencies?q=<검색어>&page=1&size=20` → `{items: [{id, name, type, region_name, bid_count}], total}`
2. `GET /agencies/{id}/analysis` — 기관 심층분석 API 신규
   - `bid-system/backend/app/services.py` `AgencyAnalysisService` 신규 클래스
   - 반환 구조:
     ```
     {
       summary: { name, total_bids, avg_win_rate, avg_srate, dominant_industry },
       monthly_trend: [{ year_month, bid_count, win_rate, avg_srate }],  # 24개월
       srate_distribution: { bins[], mode, p25, p50, p75, mean },
       top_winners: [{ competitor_name, win_count, avg_bid_rate }],  # TOP 10
       amount_distribution: [{ bucket_label, count, avg_win_rate }]  # 금액대별
     }
     ```
3. `schemas.py` — `AgencySummary`, `AgencyAnalysisResponse` 추가
4. `router.py`에 agencies 라우터 등록

### Frontend
5. `bid-system/frontend/src/api/index.ts` — `agenciesApi.list()`, `agenciesApi.analysis(id)` 추가
6. `bid-system/frontend/src/types/index.ts` — `AgencyAnalysisResponse` 타입 추가
7. `bid-system/frontend/src/pages/AgenciesPage.tsx` — 기관 목록 + 검색
8. `bid-system/frontend/src/pages/AgencyDetailPage.tsx` — 심층분석 4탭 구현
   - 탭1 "추이": 월별 입찰건수·낙찰률 라인차트 (dual axis)
   - 탭2 "사정율 분포": 히스토그램 + 최빈값 마커
   - 탭3 "주요 낙찰업체": 수평 바차트 TOP 10
   - 탭4 "금액대 분포": 금액대별 건수 + 평균 낙찰가율
9. `bid-system/frontend/src/App.tsx` — `/agencies`, `/agencies/:id` 라우트 추가 (이미 있으면 경로만 확인)
10. `bid-system/frontend/src/components/layout/` — 사이드바 네비게이션에 "발주처 분석" 메뉴 추가

## Acceptance Criteria
- [ ] `/agencies/1/analysis` 응답에 monthly_trend, srate_distribution, top_winners 포함
- [ ] AgencyDetailPage 4개 탭 모두 렌더링 확인
- [ ] 기관 목록 검색 동작
- [ ] 빌드 오류 없음

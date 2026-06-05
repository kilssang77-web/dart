---
step: 2
title: "사정율 트렌드 알림 (발주처×공종 최근 3개월)"
relevant_docs: ["CODING_CONVENTION", "API_GUIDE", "SCHEMA"]
relevant_references: []
db_migration: false
---

# Step 2 — 사정율 트렌드 알림

## 목표
발주처×공종 조합의 최근 3개월 낙찰사정율이 이전 3개월 대비 오르고 있으면
"높게 쓰세요" 신호를, 내리면 "낮게 쓰세요" 신호를 RecommendPage와 DashboardPage에 표시.

## 배경
- `assessment_rate_stats` 테이블에 기관/공종별 월별 집계 이미 존재
- `bid_results.assessment_rate` 25,323건 — 직접 집계도 가능
- 트렌드 방향: (최근3개월 mean) - (이전3개월 mean) > 0.002 → 상승

## 구현 범위

### Backend
1. `app/services.py` — `SrateTrendService` 추가
   - `get_trend(db, agency_id, industry_id) -> dict`
   - 반환: {direction: "up"|"down"|"stable", delta: float,
            recent_mean: float, prev_mean: float, sample_count: int,
            signal: str}  # signal = 사람이 읽는 한국어 메시지

2. `app/api/v1/statistics.py`
   - `GET /api/v1/stats/srate-trend?agency_id=&industry_id=` 신규

3. `app/schemas.py`
   - `SrateTrendResponse` 추가

### Frontend
1. `src/api/index.ts` — `statsApi.srateTrend(agencyId, industryId)` 추가

2. `src/types/index.ts` — `SrateTrendResponse` 타입 추가

3. `src/pages/RecommendPage.tsx`
   - 공종·발주처 선택 시 트렌드 자동 조회
   - 트렌드 뱃지: ↑상승 (빨강), ↓하락 (파랑), →안정 (회색)
   - 신호 텍스트: "최근 3개월 사정율 +0.32%p 상승 중 → 균형형 이상 추천"

4. `src/pages/DashboardPage.tsx`
   - 최근 트렌드 상위 3개 발주처 알림 카드

## 사이드 이펙트
- 기존 API 변경 없음
- assessment_rate_stats 집계가 비어있으면 bid_results 직접 집계 폴백

## 테스트
- SrateTrendService 단위 테스트 (상승/하락/안정 3케이스)

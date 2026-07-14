---
step: 6
title: "낙찰 후 역산 분석 — rate_diff 분포·패턴"
relevant_docs: ["CODING_CONVENTION", "API_GUIDE", "SCHEMA"]
relevant_references: []
db_migration: false
---

# Step 6 — 낙찰 후 역산 분석

## 목표
내가 X 사정율로 냈는데 낙찰자는 Y — 격차(rate_diff) 분포를 축적해
"평균적으로 나는 낙찰자보다 얼마나 높게/낮게 쓰는가"를 시각화.
MyBidsPage에 "역산 분석" 탭으로 추가.

## 배경
- my_bid_records.rate_diff 컬럼 이미 있음 (= submitted_rate - actual_winner_rate)
- 양수: 낙찰자보다 높게 씀 (사정율 기준 낙찰자 위, 투찰률 기준 낙찰자보다 높음)
- personal.py의 PersonalBiasAnalyzer와 연동
- DefeatAnalysisService 이미 있음 → 시각화 데이터 확장

## 구현 범위

### Backend
1. `app/services.py` — `DefeatAnalysisService.get_gap_distribution(db, user_id) -> dict`
   - rate_diff 히스토그램 (0.005 버킷)
   - 반환: {buckets: list[{range_lo,range_hi,count}],
            mean_diff, median_diff, win_if_lower_by,
            consistent_direction: "too_high"|"too_low"|"mixed",
            personal_bias: PersonalBiasAnalyzer.compute() 결과}

2. `app/api/v1/my_bids.py`
   - `GET /api/v1/my-bids/gap-analysis` 신규 (기존 defeat-analysis 확장)

3. `app/schemas.py`
   - `GapAnalysisResponse` 추가

### Frontend
1. `src/api/index.ts` — `myBidsApi.gapAnalysis()` 추가

2. `src/types/index.ts` — `GapAnalysisResponse` 타입 추가

3. `src/pages/MyBidsPage.tsx`
   - "역산 분석" 탭 추가
   - BarChart: rate_diff 분포 히스토그램 (중앙 0 기준선)
   - 핵심 지표: 평균 격차, "X% 낮게 투찰하면 낙찰 가능 구간"
   - 개인화 편향 보정 요약 카드 (personal.py 결과)

## 사이드 이펙트
- rate_diff 데이터 없으면 "투찰 이력이 쌓이면 분석 가능" 안내

## 테스트
- 빈 이력, 5건 이상 이력 케이스

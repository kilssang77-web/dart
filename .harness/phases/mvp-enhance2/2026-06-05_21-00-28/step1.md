---
step: 1
title: "A값 자동 계산 + 낙찰하한가 산출"
relevant_docs: ["CODING_CONVENTION", "API_GUIDE", "SCHEMA"]
relevant_references: []
db_migration: false
---

# Step 1 — A값 자동 계산 + 낙찰하한가 산출

## 목표
나라장터 복수예가 방식에서 A값(예정가격)을 기초금액과 사정율로부터 자동 계산하고,
낙찰하한가를 즉시 산출해 RecommendPage에서 실시간 표시한다.

## 배경
- A값 = 기초금액 × 사정율(예정가격/기초금액 비율)
- 낙찰하한율은 공종별로 다름 (ml/simulation.py FLOOR_RATE_TABLE 참조)
- 낙찰하한가 = A값 × 낙찰하한율
- 현재 RecommendPage에서 base_amount만 입력받고 A값은 계산하지 않음

## 구현 범위

### Backend
1. `app/ml/a_value.py` 신규
   - `calc_a_value(base_amount, srate_center) -> int` — 기초금액 × 사정율 중앙값
   - `calc_floor_price(a_value, floor_rate) -> int` — 낙찰하한가
   - `calc_floor_rate(industry_name) -> float` — 공종명 → 낙찰하한율 (FLOOR_RATE_TABLE 위임)
   - `calc_bid_range(base_amount, srate_center, srate_std, industry_name) -> dict`
     반환: {a_value, floor_price, floor_rate, srate_range: {p10,p25,p50,p75,p90}}

2. `app/api/v1/recommend.py`
   - `GET /api/v1/recommend/bid-range?base_amount=&industry_id=&agency_id=` 신규
   - services.RecommendService._get_srate_context() 재활용
   - 반환: {a_value, floor_price, floor_rate, srate_center, srate_range, industry_name}

3. `app/schemas.py`
   - `BidRangeResponse` 추가

### Frontend
1. `src/api/index.ts`
   - `recommendApi.bidRange(params)` 추가

2. `src/types/index.ts`
   - `BidRangeResponse` 타입 추가

3. `src/pages/RecommendPage.tsx`
   - 기초금액·공종 입력 시 자동으로 bid-range API 호출 (debounce 500ms)
   - "A값 계산" 섹션 카드 추가:
     - A값(예정가격): XXX,XXX,XXX원
     - 낙찰하한가: XXX,XXX,XXX원 (하한율 X.XXX%)
     - 사정율 예측 범위: P10~P90 바 시각화

## 사이드 이펙트
- 기존 recommend v2 API 시그니처 변경 없음
- FLOOR_RATE_TABLE을 simulation.py에서 a_value.py로 이동하고 simulation.py는 import

## 테스트
- `test_a_value.py`: calc_a_value, calc_floor_price 경계값 테스트

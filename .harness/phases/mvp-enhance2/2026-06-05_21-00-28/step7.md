---
step: 7
title: "예가 번호 패턴 ML — 발주처 특화 빈도 분석"
relevant_docs: ["CODING_CONVENTION", "API_GUIDE", "SCHEMA"]
relevant_references: []
db_migration: false
---

# Step 7 — 예가 번호 패턴 ML (발주처 특화)

## 목표
복수예가 15개 조합에서 발주처별 당첨 번호 빈도 패턴을 학습해
"이 발주처는 3,7,11번 조합이 자주 낙찰" 정보를 YegaPage에 표시.

## 배경
- yega.py: Prism형 예가 빈도 분석 이미 있음
- bid_results에 yega_numbers (당첨 번호 조합) 컬럼이 있거나 A값 역산으로 추정 가능
- agency_id 파라미터를 yega 분석에 추가

## 구현 범위

### Backend
1. `app/ml/yega.py` 확장
   - `get_agency_yega_pattern(db, agency_id, industry_id=None, months=12) -> dict`
   - bid_results에서 agency_id 기준 낙찰자의 bid_rate 분포
   - 낙찰사정율 → 예가 번호 역산 (A값 기반)
   - 반환: {pattern: list[{number, freq_pct}], top3_numbers,
            dominant_zone, sample_count}

2. `app/api/v1/recommend.py`
   - `GET /api/v1/recommend/yega-frequency` 기존 엔드포인트에 `agency_id` 파라미터 추가
   - agency_id 있으면 발주처 특화 패턴 병합

3. `app/schemas.py`
   - `YegaFrequencyResponse`에 `agency_pattern` 필드 추가

### Frontend
1. `src/pages/YegaPage.tsx`
   - 발주처 선택 드롭다운 추가 (agenciesApi 활용)
   - "발주처 특화 패턴" 섹션: 해당 발주처 상위 3개 번호 하이라이트
   - 발주처 미선택 시 전체 분포 표시 (기존 동작 유지)

## 사이드 이펙트
- 기존 yega-frequency API에 agency_id 파라미터 추가 (선택, 하위 호환)

## 테스트
- get_agency_yega_pattern 발주처 데이터 없을 때 폴백 검증

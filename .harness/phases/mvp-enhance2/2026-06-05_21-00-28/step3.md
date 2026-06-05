---
step: 3
title: "프리즘 2.0 대응 — 구간별 낙찰확률 히트맵 10개 추천"
relevant_docs: ["CODING_CONVENTION", "API_GUIDE", "SCHEMA"]
relevant_references: []
db_migration: false
---

# Step 3 — 프리즘 2.0 대응 (추천구간 10개 히트맵)

## 목표
현재 4전략(공격/균형/안정/회피)을 넘어서, 사정율 구간을 0.001 단위로 스캔해
낙찰확률이 높은 상위 10개 구간을 히트맵으로 시각화. info21c 프리즘 2.0 대응.

## 배경
- inpo21c_participants 31,800건의 실증 낙찰사정율 분포 활용
- bid_results의 낙찰자 사정율 분포 활용
- 구간 스캔: 0.860 ~ 0.930 범위를 0.001 간격으로 70개 구간
- 각 구간별 낙찰확률 = Monte Carlo win_prob (실증분포 기반)

## 구현 범위

### Backend
1. `app/ml/prism.py` 신규
   - `scan_prism_zones(base_amount, industry_name, agency_id, industry_id, db,
                       n_sim=20_000) -> list[dict]`
   - 0.860~0.930 구간을 0.001 단위로 스캔 (70구간)
   - 각 구간: {rate, win_prob, floor_ok, amount, rank_est}
   - 상위 10개 추출 기준: win_prob 내림차순, floor 미달 구간 제외

2. `app/api/v1/recommend.py`
   - `POST /api/v1/recommend/prism` 신규
   - Request: RecommendV2Request 재사용
   - Response: {zones: list[PrismZone], top10: list[PrismZone], scan_meta: dict}

3. `app/schemas.py`
   - `PrismZone`, `PrismResponse` 추가

### Frontend
1. `src/api/index.ts` — `recommendApi.prism(req)` 추가

2. `src/types/index.ts` — `PrismZone`, `PrismResponse` 타입 추가

3. `src/pages/RecommendPage.tsx` 또는 `YegaPage.tsx`
   - "프리즘 분석" 탭/섹션 추가
   - 히트맵: X축=사정율 구간, Y축=낙찰확률 (BarChart)
   - 상위 10개 구간 강조 표시 (주황색 바)
   - 각 구간: 투찰금액(원), 낙찰확률(%), 예상순위

## 사이드 이펙트
- simulation.py의 monte_carlo_win_prob_empirical 재활용
- 70구간 × 20,000 시뮬 = 계산 비용 고려 → 백그라운드 캐싱 또는 n_sim=10,000으로 축소

## 테스트
- scan_prism_zones 10개 반환 검증
- floor 미달 구간 필터링 검증

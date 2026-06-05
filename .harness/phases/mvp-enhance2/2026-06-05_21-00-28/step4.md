---
step: 4
title: "경쟁사 최근 투찰 구간 실시간 모니터링"
relevant_docs: ["CODING_CONVENTION", "API_GUIDE", "SCHEMA"]
relevant_references: []
db_migration: false
---

# Step 4 — 경쟁사 최근 투찰 구간 모니터링

## 목표
inpo21c_participants 데이터로 특정 경쟁사가 최근 어느 사정율 구간에 집중하는지
CompetitorPage에서 시각화. 경쟁사 회피 전략 수립 지원.

## 배경
- inpo21c_participants: biz_reg_no, base_ratio, assessment_rate, is_winner
- competitors: biz_reg_no 으로 매핑 가능
- 최근 90일 기준 경쟁사 투찰 구간 분포 → 그들이 몰려있는 구간 회피

## 구현 범위

### Backend
1. `app/services.py` — `CompetitorZoneService` 추가
   - `get_recent_zones(db, competitor_id, days=90) -> dict`
     - inpo21c_participants JOIN competitors (biz_reg_no)
     - base_ratio 구간별 빈도 (0.005 버킷 단위)
     - 반환: {zones: list[{range_lo,range_hi,count,pct}], peak_zone, total_count,
              last_updated}

2. `app/api/v1/competitors.py`
   - `GET /api/v1/competitors/{id}/zones` 신규 (days 쿼리 파라미터)

3. `app/schemas.py`
   - `CompetitorZoneResponse` 추가

### Frontend
1. `src/api/index.ts` — `competitorApi.zones(id, days?)` 추가

2. `src/types/index.ts` — `CompetitorZoneResponse` 타입 추가

3. `src/pages/CompetitorPage.tsx`
   - "투찰 구간 분포" 탭 추가
   - BarChart: X축=사정율 구간, Y축=빈도%
   - 피크 구간 강조 + "이 구간 회피 추천" 뱃지
   - 90일/180일 토글

## 사이드 이펙트
- competitors.biz_reg_no ↔ inpo21c_participants.biz_reg_no 매핑 없으면 빈 결과
- 데이터 없는 경쟁사는 "inpo21c 데이터 없음" 메시지

## 테스트
- CompetitorZoneService 빈 결과 처리 검증

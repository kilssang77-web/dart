---
step: 5
title: "공고 자동 추천 TOP 5 + 점수 카드 (Dashboard)"
relevant_docs: ["CODING_CONVENTION", "API_GUIDE", "SCHEMA"]
relevant_references: []
db_migration: false
---

# Step 5 — 공고 자동 추천 TOP 5

## 목표
BidScoringService(이미 구현됨)를 활용해 현재 open 상태 공고 중
이번 주 입찰해야 할 TOP 5를 DashboardPage에 자동 표시.

## 배경
- BidScoringService.score_bid(): competition(40pt) + agency_track(30pt) + trend(15pt) + amount_fit(15pt)
- bid_open_date가 7일 이내인 open 공고 대상
- 사용자 ID 기반 개인화 (agency_track, amount_fit은 my_bid_records 참조)

## 구현 범위

### Backend
1. `app/services.py` — `BidScoringService.get_top_recommended(db, user_id, limit=5) -> list`
   - open 공고 필터링 (bid_open_date 7일 이내)
   - 활성 공종 필터 적용
   - 상위 limit개 반환: {bid_id, title, agency_name, score, grade, open_date,
                          base_amount, score_breakdown}

2. `app/api/v1/bids.py`
   - `GET /api/v1/bids/recommended?limit=5` 신규

3. `app/schemas.py`
   - `BidRecommendItem` 추가

### Frontend
1. `src/api/index.ts` — `bidsApi.recommended(limit?)` 추가

2. `src/types/index.ts` — `BidRecommendItem` 타입 추가

3. `src/pages/DashboardPage.tsx`
   - "이번 주 추천 공고" 섹션 추가 (기존 KPI 카드 아래)
   - 각 공고 카드: 등급 뱃지(A/B/C/D), 점수 바, 개찰일, 기초금액
   - 클릭 시 BidDetailPage로 이동
   - "추천 이유" 툴팁 (score_breakdown 기반)

## 사이드 이펙트
- my_bid_records 데이터 없는 사용자는 agency_track/amount_fit 기본값 적용
- 공고 수가 5개 미만이면 있는 것만 표시

## 테스트
- get_top_recommended 빈 DB, 정상 케이스

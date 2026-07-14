---
step: 1
name: "수집기 현황 개선 + 투찰이력 빠른입력 폼"
relevant_docs: ["PRD", "CODING_CONVENTION", "API_GUIDE", "SCHEMA"]
relevant_references: []
---

## 목표
1. 관리자 화면 수집 현황 패널에 오늘 수집량·마지막 수집 시각 실시간 표시
2. MyBidsPage에 투찰이력 빠른입력 모달 추가 (공고번호 자동완성 → 사정율/결과 입력 → rate_diff 자동계산)

## 구현 상세

### Backend
- `GET /api/v1/admin/collector-status` 개선: `today_notices`, `today_results`, `last_run_at`, `next_run_at` 필드 추가
- `POST /api/v1/my-bids` — 기존 엔드포인트 확인 및 `rate_diff` 자동계산 (submitted_rate - actual_winner_rate) 로직 보강
- `GET /api/v1/bids/search?announcement_no=` — 공고번호 자동완성용 경량 검색 엔드포인트

### Frontend
- `AdminPage.tsx`: 수집 현황 카드에 today_notices / today_results / last_run_at / next_run_at 표시
- `MyBidsPage.tsx`: "투찰 등록" 버튼 → 모달
  - 공고번호 입력 → debounce 검색 → 공고명/발주처/기초금액 자동완성
  - 투찰 사정율 입력 (기초금액 대비 %)
  - 결과 선택 (낙찰/유찰/미응찰)
  - 낙찰 시 낙찰자 사정율 입력 → rate_diff 즉시 계산 표시
  - 저장 → 목록 갱신

## 기존 시그니처 유지 vs 변경
- `POST /api/v1/my-bids`: 기존 스키마 유지 (announcement_no, rate_diff 필드 이미 존재)
- 새 엔드포인트 추가만

## 사이드 이펙트
- 없음 (읽기/쓰기 분리, 기존 데이터 변경 없음)

## 마이그레이션
- DB 변경 없음

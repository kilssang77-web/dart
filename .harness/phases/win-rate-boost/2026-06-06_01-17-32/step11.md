---
step: 11
name: "MANUAL.md v2.1 갱신 + win-rate-boost 릴리즈 노트 작성"
relevant_docs: ["PRD", "CODING_CONVENTION"]
relevant_references: []
---

## 목표
win-rate-boost steps 1~10에서 추가된 기능을 사용자 매뉴얼(MANUAL.md v2.0 → v2.1)에 반영하고,
릴리즈 노트를 작성하여 .harness/release-notes/ 에 등록한다.

## 구현 상세

### bid-system/MANUAL.md — v2.1 갱신 항목

| 섹션 | 변경 내용 |
|-----|---------|
| 1.1 핵심 기능 | steps 1~10 신규 기능 6개 추가 |
| 1.3 수집 일정 | inpo21c 일별 수집 스케줄 추가 |
| 6 AI 투찰률 추천 | 사정율 신뢰도 뱃지 설명 추가 |
| 7 내 입찰 관리 | 7.4 승률 패턴 진단 탭 추가 |
| 8 경쟁사 분석 | 행동 예측 탭 추가, 소절 번호 오류 수정 |
| 9 예가 분석 | AgencyDetailPage 예가패턴 탭 참조 추가 |
| 10 공동도급 | 적격심사 시뮬레이터 v2 상세 추가 |

### .harness/release-notes/2026-06-06_01-17-32_win-rate-boost.md — 신규 작성

### .harness/release-notes/INDEX.md — 신규 항목 추가

## 기존 시그니처 유지
- DB 변경 없음
- 코드 변경 없음 (문서만 업데이트)

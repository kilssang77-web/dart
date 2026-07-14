---
step: 1
name: "투찰 이력 Excel 내보내기 (My Bids)"
relevant_docs: ["PRD", "CODING_CONVENTION", "API_GUIDE"]
relevant_references: []
---

## 목표
MyBidsPage 투찰 이력 탭에 Excel(.xlsx) 다운로드 버튼을 추가한다.
openpyxl 기반 백엔드 엔드포인트 → 프론트엔드 다운로드 트리거.

## 구현 상세

### Backend — api/v1/my_bids.py
- `GET /api/v1/my-bids/export/excel`
  - `StreamingResponse` + `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
  - 컬럼: 공고번호, 공고제목, 발주처, 입찰일, 기초금액, 제출투찰률, 추천투찰률, 결과, 실제낙찰률, 격차(rate_diff), 비고
  - openpyxl로 헤더 굵게, 컬럼 너비 자동 조정

### Frontend — MyBidsPage.tsx
- 투찰 이력 탭 상단 "Excel 다운로드" 버튼 추가
- `api/index.ts`: `myBidsApi.exportExcel()` — Blob 응답 → `<a download>` 트리거
- 로딩 스피너 (다운로드 중 비활성화)

## 기존 시그니처 유지
- 기존 my-bids API 변경 없음

---
step: 8
title: "공동도급 적격심사 AI 매칭 + 입찰 전략 레포트 PDF"
relevant_docs: ["CODING_CONVENTION", "API_GUIDE", "SCHEMA"]
relevant_references: []
db_migration: false
---

# Step 8 — 공동도급 적격심사 AI 매칭 + 전략 레포트 PDF

## 목표 A: 공동도급 적격심사 AI 매칭
JointBidPage의 공동도급 협정사 탐색 결과와 QualificationPage의 적격심사 계산기를 연결.
"이 공고를 혼자 따기엔 실적 부족 → 어느 회사와 협정하면 통과 가능한지" 자동 계산.

## 목표 B: 입찰 전략 레포트 PDF
특정 공고의 AI 추천 결과를 1페이지 PDF로 출력.
발주처 분석 + 추천요율 4전략 + 경쟁사 + 리스크 요약.

---

## 구현 범위 A: 공동도급 적격심사 매칭

### Backend
1. `app/services.py` — `JointQualService` 추가
   - `find_matching_partners(db, bid_id, user_biz_no, user_track_amount) -> list`
   - bid의 base_amount, license_codes로 적격심사 통과 기준 계산
   - competitors DB에서 매칭 후보 반환
   - 반환: {partners: list[{competitor_id, name, biz_reg_no,
                              joint_min_rate, qualification_ok}]}

2. `app/api/v1/bids.py`
   - `GET /api/v1/bids/{id}/joint-partners?user_track=&participation_rate=` 신규

### Frontend
1. `src/pages/JointBidPage.tsx`
   - 공고 선택 후 "적격심사 AI 매칭" 버튼 추가
   - 결과: 협정 가능 업체 목록 + 최소 투찰금액 제시

---

## 구현 범위 B: 전략 레포트 PDF

### Frontend (PDF 생성은 클라이언트사이드)
1. `package.json` — `jspdf` + `html2canvas` 추가 (or `@react-pdf/renderer`)

2. `src/pages/RecommendPage.tsx`
   - "전략 레포트 출력" 버튼 추가
   - 레포트 구성 (A4 1~2페이지):
     - 공고명, 발주처, 기초금액, 개찰일
     - A값·낙찰하한가 요약
     - 사정율 트렌드 (Step 2 결과)
     - 4전략 추천요율 + 낙찰확률
     - 프리즘 TOP 5 구간 (Step 3 결과)
     - 리스크 요약
   - HTML 레이아웃을 숨겨진 div에 렌더링 후 PDF 변환

## 사이드 이펙트
- jspdf 추가로 bundle size 약 200KB 증가
- JointQualService는 competitors DB 기반 — 25,387개 중 실적 데이터 없는 업체 다수

## 테스트
- JointQualService: 매칭 없음, 1개 이상 케이스

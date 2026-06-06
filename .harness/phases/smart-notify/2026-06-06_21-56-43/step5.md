---
step: 5
name: "알림 드롭다운 + 읽음 처리 + 알림 목록 페이지"
relevant_docs: ["PRD", "CODING_CONVENTION"]
relevant_references: []
---

## 목표
알림 목록 전용 페이지를 구현한다.

## 구현 상세

### NotificationsPage.tsx
- GET /notifications (limit=50) 조회
- 읽음/미읽음 행 구분 (파란 점 표시)
- 개별 읽음 처리 (행 클릭)
- 모두 읽음 버튼
- ntype 뱃지: 키워드/사정율/시스템
- link 클릭 시 내부 페이지 이동 (useNavigate)
- 빈 상태 / 로딩 스켈레톤

### App.tsx
- /notifications 라우트 추가

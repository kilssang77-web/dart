---
step: 4
name: "Notification API + 헤더 알림 뱃지 UI"
relevant_docs: ["PRD", "CODING_CONVENTION", "API_GUIDE"]
relevant_references: []
---

## 목표
알림 CRUD API 4개 엔드포인트와 프론트엔드 헤더 벨 뱃지를 구현한다.

## 구현 상세

### Backend — api/v1/notifications.py
- GET /notifications (list, unread_only, limit 파라미터)
- GET /notifications/unread-count
- POST /notifications/{id}/read
- POST /notifications/read-all
- router.py 에 notifications_router 등록

### Frontend
- types/index.ts: Notification, NotificationListResponse 추가
- api/index.ts: notificationsApi (list, unreadCount, markRead, markAllRead)
- AppLayout.tsx: 사이드바 하단 벨 아이콘 + 미읽음 뱃지 (60초 폴링)

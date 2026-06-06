---
step: 2
name: "키워드 매칭 공고 알림 자동 생성 (수집기 연동)"
relevant_docs: ["PRD", "CODING_CONVENTION"]
relevant_references: []
---

## 목표
나라장터 공고 수집 시 활성화된 WatchKeyword 와 공고 title/agency_name 을 매칭해
신규 공고에 한해 NotificationService.create_keyword_match 를 호출한다.

## 구현 상세

### collector/service.py 변경
- `_check_keyword_match(db, bid)` 헬퍼 추가
  - WatchKeyword (is_active=True) 전체 조회
  - bid.title 에서 키워드 포함 여부 확인 (대소문자 무시)
  - 매칭된 키워드가 있으면 NotificationService(db).create_keyword_match(bid, matched) 호출
- `collect_notices` 루프에서 `is_new=True` 일 때만 `_check_keyword_match` 호출

## 기존 시그니처 유지
- collect_notices 함수 시그니처 변경 없음

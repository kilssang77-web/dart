---
step: 3
name: "사정율 급변 알림 자동 생성"
relevant_docs: ["PRD", "CODING_CONVENTION"]
relevant_references: []
---

## 목표
SrateTrendService.get_top_trends() 를 이용해 ±2%p 이상 급변 발주처를 탐지하고
NotificationService.create_srate_spike() 로 전체 공지 알림을 생성한다.

## 구현 상세

### collector/scheduler.py 변경
- `run_srate_spike_check_job()` 함수 추가
  - SPIKE_THRESHOLD_PCT = 2.0 (%p 기준)
  - SrateTrendService().get_top_trends(db, limit=10) 호출
  - delta_pct >= 2%p 이면 NotificationService.create_srate_spike() 호출
- create_scheduler() 에 srate_spike_check_daily (매일 07:00 KST) 등록

## 기존 시그니처 유지
- 스케줄러 기존 5개 job 유지, 1개 추가

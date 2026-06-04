---
relevant_docs: ["ARCHITECTURE", "CODING_CONVENTION", "API_GUIDE"]
---

# Step 3: APScheduler 통합 + 관리자 API

## 목표
FastAPI lifespan에 APScheduler 등록, 수동 트리거 및 수집 로그 조회 API 구현

## 작업 내용
1. `requirements.txt` — `apscheduler>=3.10` 추가
2. `bid-system/backend/app/collector/scheduler.py` 신규
   - `create_scheduler()` — BackgroundScheduler 생성
   - 스케줄: 매일 06:00 KST (`collect_notices`), 18:00 KST (`collect_results`)
   - `run_collection_job(collect_type)` — DB 세션 생성 후 수집 서비스 호출
3. `bid-system/backend/app/main.py` lifespan 수정
   - `@asynccontextmanager` lifespan에 스케줄러 start/shutdown 등록
4. `bid-system/backend/app/api/v1/admin.py` 보완
   - `GET /api/v1/admin/collection-logs` — CollectionLog 목록 (최신 50건)
   - `POST /api/v1/admin/collect/trigger` — 즉시 수집 실행 (백그라운드 태스크)
     - `collect_type` query param: `all` / `notices` / `results`

## Acceptance Criteria (mvp)
- [ ] 빌드 통과
- [ ] `POST /api/v1/admin/collect/trigger` → 200 + `{"message": "수집 시작됨"}` 즉시 반환
- [ ] 트리거 완료 후 `GET /api/v1/admin/collection-logs` → 새 CollectionLog 확인
- [ ] 앱 시작 로그에 "Scheduler started" 출력

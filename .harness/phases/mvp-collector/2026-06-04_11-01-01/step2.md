---
relevant_docs: ["ARCHITECTURE", "CODING_CONVENTION", "SCHEMA"]
relevant_references: ["info21c"]
---

# Step 2: 공고·낙찰결과 수집 서비스

## 목표
API 클라이언트를 사용해 DB에 공고 및 낙찰결과를 저장하는 수집 서비스 구현

## 작업 내용
1. `bid-system/backend/app/collector/service.py` 신규
   - `collect_notices(db, client, collect_type, days_back=7)` — 공사/용역/물품 공고 수집
     - `bids` 테이블 upsert (`announcement_no` 기준 중복 방지)
     - `agencies` 테이블 upsert (신규 발주처 자동 등록)
   - `collect_results(db, client, days_back=30)` — 낙찰결과 수집
     - `bid_results` 테이블 upsert
     - `competitors` 테이블 upsert (신규 경쟁사 자동 등록)
   - `run_full_collection(db)` — 전체 수집 진입점 (notices → results 순서)
   - `CollectionLog` 기록 (수집유형, 성공건수, 실패건수, 소요시간, 에러요약)
2. `bid-system/backend/tests/unit/collector/test_service.py` 신규
   - upsert 중복 처리: 같은 announcement_no 2회 수집 → 1건만 저장
   - CollectionLog 정상 기록 검증

## Acceptance Criteria (mvp)
- [ ] 빌드 통과
- [ ] 단위 테스트: upsert 중복 처리 (announcement_no 중복 시 update)
- [ ] 단위 테스트: collect_notices() 완료 후 CollectionLog 1건 생성
- [ ] 단위 테스트: 수집 실패 시 CollectionLog에 error_summary 기록

---
relevant_docs: ["ARCHITECTURE"]
---

# Step 5: 공고 수집 안정성 + 용역·물품 확장

## 목표
수집 누락을 최소화하고, 용역·물품 공고도 수집하며, 수집 이력을 관리자가 모니터링할 수 있도록 한다.

## 작업 내용

### Collector 개선
1. `bid-system/collector/g2b_client.py` 수정
   - 지수 백오프 재시도: 429/5xx 응답 시 `2^n * 5초` 대기 (최대 3회, 최대 60초)
   - 타임아웃 설정: `httpx.AsyncClient(timeout=30.0)` 명시
   - 응답 파싱 오류 시 원본 JSON 로깅 후 skip (프로세스 중단 방지)

2. `bid-system/collector/main.py` 수정
   - 용역 수집 스케줄 추가: `getBidPblancListInfoServc` (09:30, 15:30)
   - 물품 수집 스케줄 추가: `getBidPblancListInfoThng` (10:00, 16:00)
   - 수집 결과(성공건수/실패건수/소요시간)를 `collection_logs` 테이블에 저장

### Backend — 수집 로그
3. `bid-system/backend/app/models.py` — `CollectionLog` 모델 추가
   ```python
   class CollectionLog(Base):
       __tablename__ = "collection_logs"
       id           = Column(BigInteger, primary_key=True)
       collect_type = Column(String(20))  # notice_cnstwk / notice_servc / notice_thng / result
       collected_at = Column(DateTime(timezone=True))
       success_count = Column(Integer, default=0)
       fail_count    = Column(Integer, default=0)
       duration_sec  = Column(Numeric(8, 2))
       error_summary = Column(Text)
       created_at    = Column(DateTime(timezone=True), server_default=func.now())
   ```
4. `bid-system/backend/app/api/v1/admin.py` — `GET /admin/collection-logs?days=7` 엔드포인트 추가
5. `bid-system/backend/app/schemas.py` — `CollectionLogOut` 추가
6. Alembic 마이그레이션 파일 생성 (또는 `models.py` 변경으로 자동 반영)

### Frontend
7. `bid-system/frontend/src/api/index.ts` — `adminApi.collectionLogs(days?)` 추가
8. `bid-system/frontend/src/pages/AdminPage.tsx` 수정
   - "수집 현황" 섹션 추가: 최근 7일 수집 로그 타임라인 테이블
   - 수집 타입별 성공률 배지 (공사/용역/물품/결과)
   - 마지막 수집 시각 표시

## Acceptance Criteria
- [ ] 429 응답 시 지수 백오프 재시도 로직 동작 확인 (로그 출력)
- [ ] collector가 용역(`servc`) 공고도 수집 (main.py 스케줄 확인)
- [ ] `collection_logs` 테이블 생성 및 수집 후 레코드 삽입
- [ ] `GET /admin/collection-logs` 응답에 수집 이력 목록 반환
- [ ] AdminPage 수집 현황 섹션에 타임라인 표시
- [ ] 빌드 오류 없음

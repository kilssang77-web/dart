---
relevant_docs: ["ARCHITECTURE", "CODING_CONVENTION", "SCHEMA", "API_GUIDE"]
relevant_references: ["info21c", "infose_info21c"]
---

# Step 1: 나라장터 Open API 클라이언트

## 목표
공공데이터포털 나라장터 API를 호출하는 Python 클라이언트 구현

## 작업 내용
1. `bid-system/backend/app/collector/__init__.py` 신규 (빈 파일)
2. `bid-system/backend/app/collector/client.py` 신규
   - `NarajangterClient` 클래스
   - 공사입찰공고목록 (`getBidPblancListInfoCnstwkBsbd01`)
   - 용역입찰공고목록 (`getBidPblancListInfoServcBsbd01`)
   - 물품입찰공고목록 (`getBidPblancListInfoThingsBsbd01`)
   - 낙찰결과목록 (`getBidResultListInfoCnstwkBsbd01`)
   - 재시도 로직 (최대 3회), 타임아웃 30초, 페이지네이션
3. `bid-system/backend/app/config.py` — `NARA_API_KEY` 환경변수 추가
4. `bid-system/backend/.env.example` — `NARA_API_KEY=` 항목 추가
5. `bid-system/backend/tests/unit/collector/test_client.py` 신규
   - pytest-mock으로 API 응답 fixture mocking
   - 파싱 정확도, 재시도 로직, 페이지네이션 테스트

## Acceptance Criteria (mvp)
- [ ] 빌드 통과 (`uvicorn app.main:app` 정상 시작)
- [ ] 단위 테스트 통과: API 응답 파싱, 재시도, 페이지네이션
- [ ] `NARA_API_KEY` 없으면 명확한 에러 메시지 (설정 로드 시점)

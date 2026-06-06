# 프로젝트 개발 규칙

> 이 파일은 Claude Code(AI 에이전트)가 따라야 할 프로젝트 전용 규칙입니다.
> **kospi-feature-stock** — Python 3.12 + FastAPI + Kafka + PostgreSQL(TimescaleDB+pgvector) 마이크로서비스 시스템.

---

## CRITICAL — 절대 지켜야 할 규칙

1. **비즈니스 로직은 각 서비스의 전담 모듈에서만 작성한다.** FastAPI 라우터(routers/)에 비즈니스 로직을 작성하지 않는다. DB 쿼리를 라우터에서 직접 호출하지 않는다.

2. **DB 접근은 항상 asyncpg를 통한 파라미터 바인딩을 사용한다.** 문자열 포맷팅으로 SQL을 조합하지 않는다 (SQL 인젝션 방지).

3. **환경변수는 반드시 `.env` 파일과 `os.getenv()`로 관리한다.** API 키·비밀값·DSN을 코드에 하드코딩하지 않는다.

4. **Kafka 메시지 발행/소비는 각 서비스의 `kafka/` 서브모듈을 통해서만 수행한다.** 라우터나 비즈니스 로직 모듈에서 직접 Kafka 클라이언트를 생성하지 않는다.

5. **모든 FastAPI 라우터 함수는 Pydantic 스키마(schemas/)를 통해 요청/응답을 정의한다.** `dict` 또는 `Any` 타입을 응답으로 반환하지 않는다.

---

## 코딩 표준

> 세부 사항은 `.harness/docs/CODING_CONVENTION.md` 참조.

### Backend (Python 3.12 + FastAPI)
- 서비스 구조: `main.py` (진입점) / `kafka/` (스트림) / `db/` (쿼리) / `rules/` 또는 도메인 모듈
- 비동기: 모든 I/O 작업은 `async/await` 사용 (asyncpg, aiokafka, httpx)
- 예외: FastAPI `HTTPException` + 커스텀 `error_handler` 사용
- 타입힌트: 모든 함수 시그니처에 타입힌트 필수
- 로깅: `logging` 모듈 사용, 비밀값 출력 금지

### 마이크로서비스 간 통신
- **동기**: FastAPI REST (서비스간 직접 HTTP 호출 최소화)
- **비동기**: Kafka 토픽 발행/소비
- **캐시/Pub-Sub**: Redis

### DB / 인프라
- PostgreSQL 쿼리: asyncpg 파라미터 바인딩 (`$1`, `$2`)
- 시계열 데이터: TimescaleDB Hypertable 활용
- 벡터 검색: pgvector `<=>` (cosine), `<->` (L2)
- 마이그레이션: `infra/postgres/` SQL 파일 순서대로 관리

---

## 아키텍처 원칙

> 세부 사항은 `.harness/docs/ARCHITECTURE.md` 참조.

- **데이터 흐름**: collector → Kafka → detector/analyzer → Kafka → recommender → Redis/DB → api
- **서비스 독립성**: 각 서비스는 독립 배포 가능. 타 서비스 DB에 직접 접근하지 않는다.
- **설정**: 모든 임계값·파라미터는 환경변수로 노출. 하드코딩 금지.

---

## 테스트 요구사항

> 세부 사항은 `.harness/docs/TESTING.md` 참조.

- **prototype**: Docker Compose 기동 후 `/health` 엔드포인트 통과
- **mvp**: pytest 단위 테스트 통과 (탐지 규칙, 추천 알고리즘 핵심 로직)
- **production**: pytest 커버리지 70%+, 보안 스캔, E2E 시나리오 테스트

---

## 보안 요구사항

> 세부 사항은 `.harness/docs/SECURITY.md` 참조.

- 비밀값 하드코딩 절대 금지 (`.env` + `os.getenv()`)
- 외부 입력은 Pydantic 스키마로 검증
- 로그에 API 키·토큰·개인정보 출력 금지
- SQL은 항상 파라미터 바인딩

---

## 파일 변경 금지 목록

- `.harness/phases/` 내 `completed` 상태 run 폴더
- `.harness/release-notes/` 내 `synced: true` 항목
- `.harness/references/` (읽기 전용 참고 자산)

---

## 커밋 메시지 형식

Conventional Commits 형식을 따른다:

```
<type>(<scope>): <subject>

feat(detector): 모닝스타 패턴 탐지 규칙 연결
fix(recommender): ML 확률 계산 오류 수정
```

type: `feat` | `fix` | `docs` | `refactor` | `test` | `chore` | `perf`

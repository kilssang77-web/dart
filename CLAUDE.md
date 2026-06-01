# 프로젝트 개발 규칙

> 이 파일은 Claude Code(AI 에이전트)가 따라야 할 프로젝트 전용 규칙입니다.
> **FastAPI (Python 3.12) + React 18 (TypeScript)** 기반 웹 개발을 전제합니다.
> 프로젝트: `bid-system` — 나라장터 입찰 AI 추천 시스템

---

## CRITICAL — 절대 지켜야 할 규칙

> 이 섹션은 예외 없이 모든 작업에서 준수한다.

1. **비즈니스 로직은 `services.py`에서만 작성한다.** Router(`api/v1/`)에 비즈니스 로직을 작성하지 않는다. SQLAlchemy Session을 Router에서 직접 사용하지 않는다.

2. **React 컴포넌트에서 `axios`를 직접 호출하지 않는다.** 모든 API 호출은 `frontend/src/api/` 레이어를 통해 수행하며, 서버 상태는 TanStack Query로 관리한다.

3. **ML 모델 추론(`ml/`)은 서비스 레이어에서만 호출한다.** Router에서 `ml/` 모듈을 직접 import하지 않는다.

4. **비밀값을 코드에 하드코딩하지 않는다.** DB 비밀번호·API 키·JWT Secret은 환경변수(`.env`)로만 관리한다.

5. **`any` 타입 사용 금지 (TypeScript).** 모든 API 응답은 `frontend/src/types/index.ts`에 타입을 정의한다.

---

## 코딩 표준

> 세부 사항은 `.harness/docs/CODING_CONVENTION.md` 참조. 여기에는 핵심만 기재한다.

### Backend (FastAPI + Python 3.12)
- 패키지 구조: `api/v1/` (라우터) / `services.py` (비즈니스) / `models.py` (ORM) / `schemas.py` (DTO) / `ml/` (ML 엔진)
- DTO: Pydantic `BaseModel`, Request/Response 분리 (`*Request` / `*Response`)
- 예외: FastAPI `HTTPException` + 공통 에러 핸들러
- 쿼리: SQLAlchemy ORM 또는 파라미터 바인딩 사용 (문자열 직접 조합 금지)
- 린터: Ruff (`ruff check` + `ruff format`)

### Frontend (React 18 + TypeScript)
- 컴포넌트: `pages/` (라우트 페이지), `components/ui/` (shadcn 래퍼), `components/layout/` (레이아웃)
- 상태: 서버 상태 → TanStack Query v5, 전역 클라이언트 상태 → Zustand (`store/`)
- 타입: `any` 사용 금지. `src/types/index.ts`에 API 응답 타입 정의 필수
- 린터: Prettier + ESLint

---

## 아키텍처 원칙

> 세부 사항은 `.harness/docs/ARCHITECTURE.md` 참조.

- 레이어 의존성: `api/v1/` → `services.py` → `models.py` + `ml/` (역방향 금지)
- DB 트랜잭션: `services.py`에서만 `db.commit()` / `db.rollback()` 사용
- ML 추론: `services.py`에서 `ml/` 함수 호출. Router에서 직접 호출 금지

---

## 테스트 요구사항

> 단계(stage)에 따라 강도가 달라진다. 세부 사항은 `.harness/docs/TESTING.md` 참조.

- **prototype**: 빌드 통과만 필수
- **mvp**: 빌드 + 단위 테스트 통과 (pytest)
- **production**: 빌드 + 단위/통합 테스트 + 커버리지 임계 + 보안 스캔

---

## 보안 요구사항

> 세부 사항은 `.harness/docs/SECURITY.md` 참조.

- 비밀값 하드코딩 절대 금지 (환경변수 사용)
- 외부 입력은 Pydantic 모델 또는 TypeScript 타입 가드로 검증
- 로그에 패스워드·토큰·개인정보 출력 금지
- JWT Secret은 `.env`의 `SECRET_KEY`로만 관리

---

## 파일 변경 금지 목록

> 다음 파일·디렉토리는 이 step에서 변경하지 않는다.

- `.harness/phases/` 내 `completed` 상태 run 폴더
- `.harness/release-notes/` 내 `synced: true` 항목
- `.harness/references/` (읽기 전용 참고 자산)
- `bid-system/frontend/node_modules/`
- `bid-system/backend/app/__pycache__/`

---

## 커밋 메시지 형식

Conventional Commits 형식을 따른다:

```
<type>(<scope>): <subject>

feat(recommend): Monte Carlo 시뮬레이션 캐싱 추가
fix(auth): JWT 만료 후 401 응답 누락 수정
```

type: `feat` | `fix` | `docs` | `refactor` | `test` | `chore` | `perf`

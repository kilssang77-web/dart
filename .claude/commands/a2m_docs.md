---
description: 질문에 답하면 단계별 docs(prototype 4종 / mvp 11종 / production 12종)를 자동 생성합니다
---

신규 `/a2m_docs` 명령입니다.
처음 사용하는 사용자가 질문에 답하면 `.harness/docs/*`를 단계에 맞게 생성할 수 있도록 돕습니다.

- **prototype**: PRD, ARCHITECTURE, ADR, UI_GUIDE (4종)
- **mvp**: 위 + CODING_CONVENTION, PROJECT_STRUCTURE, SECURITY, TESTING, API_GUIDE, SCHEMA, SCREEN_MAP (11종)
- **production**: 위 + DEPLOYMENT (12종)

---

## 인터프리터 실행 흐름

질문 진행 전, `.harness/scripts/ask_questions.py`가 존재하면 인터프리터 모드로 동작한다:

```bash
# 다음 미답 필수 질문 출력 (옵션은 profile.json 컨텍스트에 맞게 좁혀짐)
python .harness/scripts/ask_questions.py next

# 답변 기록 + profile.json / answers.json 갱신
python .harness/scripts/ask_questions.py answer <id> <value>

# 모든 필수 질문 완료 여부 (exit 0=완료, 1=미완료)
python .harness/scripts/ask_questions.py done

# 남은 필수 질문 목록
python .harness/scripts/ask_questions.py missing

# 특정 질문 분기 매트릭스 확인 (디버그)
python .harness/scripts/ask_questions.py explain <id>
```

> **폴백**: `ask_questions.py`가 없거나 실행 실패 시 AI가 `.harness/questions.yaml`을 직접 해석하여 진행한다.
> PyYAML도 없으면 아래 각 질문 섹션을 직접 읽어 진행하되, "**조건/분기**" 블록을 반드시 참고하여 관련 없는 옵션은 표시하지 않는다.

아래 순서대로 질문하고, 모두 완료되면 "문서 일괄 생성" 섹션으로 이동한다.

---

## 질문 0a — 프로젝트 단계 (필수)

> 인터프리터 ID: `q0a`

> "먼저 프로젝트 단계를 선택해 주세요.
> 1. prototype — 빠른 검증·데모 목적. 가볍게 시작. (docs 4종)
> 2. mvp — 실사용자 대상 출시 목표. (docs 11종)
> 3. production — 운영 목표. 가용성·보안·관리 필수. (docs 12종)"

**처리 절차:**
선택 후 `.harness/profile.json` 생성/업데이트 (기존 파일이 있으면 아래 키만 갱신, 나머지는 보존):

```json
{
  "stage": "<선택>",
  "project_name": "<이후 1번 질문에서 확정>",
  "tech": {},
  "updated_at": "<ISO8601>"
}
```

> **주의**: `_comment`, `_schema`, `context`, `architecture`, `review`, `guard`, `project_type` 등 기타 기존 키는 **반드시 보존**한다.

이후 모든 질문의 깊이와 docs 분량은 단계에 맞춰 조정한다.

---

## 질문 0b — 참고 프로젝트 (선택)

> 인터프리터 ID: `q0b`

> "이 프로젝트에는 비슷한 역할을 하는 참고할 만한 프로젝트가 있나요?
> git URL 또는 로컬 절대 경로를 알려주세요. 없으면 '없음'으로 답해주세요."

**처리 절차:**
URL/경로가 주어지면:
```
python .harness/scripts/references.py add <url-or-path> --purpose "<용도>"
```
이후 모든 문서 생성 단계에서 해당 자산을 참조하도록 프롬프트에 강제 주입한다.

---

## 질문 0c — 프로젝트 유형 (필수)

> 인터프리터 ID: `q0c`

> "프로젝트 유형을 선택해 주세요. (AI 페르소나 검증 기준과 보안·DB 질문의 깊이에 영향을 줍니다.)
> 1. b2c_consumer — B2C 소비자 서비스
> 2. b2b_internal — B2B 또는 사내 도구
> 3. financial — 금융·결제·핀테크
> 4. healthcare — 의료·헬스케어
> 5. data_heavy — 데이터 파이프라인·분석
> 6. infra_tool — 인프라·DevOps 도구
> 7. mobile_first — 모바일 우선 서비스
> 8. gov — 공공·정부
> 9. open_source — 오픈소스 라이브러리·프레임워크"

**처리 절차:**
- `profile.json.project_type` 에 기록
- `financial`/`healthcare` 선택 시: 보안 페르소나 가중치 자동 상향 (`review_docs.py` `project_type_override` 트리거) 안내
- `data_heavy` 선택 시: 질문 10(DB 스키마)에서 샤딩 질문 강제됨 안내

---

## 질문 1 — 프로젝트 개요 (→ PRD)

> 인터프리터 ID: `q1`

> "프로젝트를 한 줄로 소개해 주세요.
> - 누가 사용하는 서비스인가요?
> - 어떤 문제를 해결하나요?
> - 프로젝트 이름을 알려주세요."

**처리 절차:**
- `profile.json.project_name` 갱신
- PRD.md "프로젝트 개요" 섹션 작성

---

## 질문 2 — 사용자·유스케이스·MVP 범위 (→ PRD)

> 인터프리터 ID: `q2`

> "주요 사용자 그룹(페르소나)과 핵심 기능 3~5가지를 알려주세요.
> 이번 버전에서 제외할 기능이 있다면 함께 알려주세요."

**처리 절차:**
- PRD.md "사용자 페르소나", "핵심 기능", "이번 버전 범위" 섹션 작성

---

## 질문 3 — 기술 스택 (→ ADR + ARCHITECTURE)

> 인터프리터 ID: `q3`

> "기술 선택을 알려주세요. 잘 모르면 추천을 드릴게요.
> - Backend: (Spring Boot 3 권장)
> - Frontend: (React 18 권장) — 없으면 '없음'
> - DB: (PostgreSQL 권장)
> - 언어 버전: (예: Java 21, Python 3.12, Node 22)
> - 배포: (Docker + 클라우드 / 온프레미스?)"

**처리 절차:**
- 선택 이유를 ADR-001에 기록
- `profile.json.tech` 갱신 (backend, frontend, db, runtime, language_version 등)
- `CLAUDE.md` 상단을 확정 선택 기준으로 준비 (CRITICAL 규칙·코딩 규칙 포함)

---

## 질문 3 직후 — 기술 선택·템플릿 규칙 반영 (필수)

확정된 선택이 하네스 기본 템플릿(Spring Boot 3 + React 18 등)과 다르거나 `CLAUDE.md`·`profile.json`의 `tech`가 기본 템플릿 그대로면 **아래를 반드시 같은 세션에서 수행**하고 다음 질문으로 진행한다.

1. 선택 내용 요약을 사용자에게 확인하거나 질문 3 답변대로 확정한다.
2. `profile.json.tech`를 실제 선택에 맞게 갱신한다.
3. `CLAUDE.md` 상단 준비: CRITICAL 규칙·코딩 규칙·금지 사항을 확정 선택 기준으로 새로 작성한다.
4. 이미 생성된 docs 초안이 있으면 같은 세션에서 ADR.md, ARCHITECTURE.md, PROJECT_STRUCTURE.md, CODING_CONVENTION.md의 선택 의존 구간을 수정한다.

---

## 질문 3.5 — 백엔드 아키텍처 스타일 (필수)

> 인터프리터 ID: `q3_5`

> "이 프로젝트의 백엔드 아키텍처 스타일을 선택해 주세요. **선택은 디렉토리·배포·트랜잭션 경계 전체를 좌우합니다.**
> 1. 단일 모놀리스 — 하나의 빌드/배포 단위
> 2. 모듈러 모놀리스 — 하나의 빌드, 도메인 모듈 분리 (예: domain-auth, domain-post)
> 3. MSA — 여러 빌드/배포 단위, 서비스 간 통신 필요
> 4. 백엔드 없음 (BaaS/Edge functions/Serverless)"

**조건/분기:**
- 의존: `q3.backend`
- MSA 선택 시 후속 질문 자동 발생:
  - 서비스 이름 목록 (예: auth-service, post-service, gateway)
  - 서비스 간 통신: REST / gRPC / Kafka / RabbitMQ / 혼합
  - API Gateway: Spring Cloud Gateway / Nginx / Kong / 없음
  - 서비스 디스커버리: Eureka / Consul / k8s service / 없음
  - 분산 트랜잭션: Saga / 최종 일관성 / 트랜잭션 회피 설계
- 모듈러 모놀리스 선택 시 후속 질문:
  - 모듈 경계 목록과 패키지/디렉토리 매핑
  - 모듈 간 의존 방향 규칙

**처리 절차:**
- 결과를 ARCHITECTURE.md·ADR.md·PROJECT_STRUCTURE.md에 반영
- `profile.json.architecture.style` 기록 (예: `monolith`, `modular_monolith`, `msa`, `baas`)
- MSA면 `profile.json.architecture.services` 기록

> 참고: 선택에 따라 **질문 4**의 레포 옵션이 달라집니다.

---

## 질문 3.6 — 패키지/모듈 명명 (필수)

> 인터프리터 ID: `q3_6`

> "최상위 패키지(또는 npm scope)를 알려주세요.
> - Backend 예시: com.acme.board 또는 io.example.api
> - Frontend 예시: @acme/board-web 또는 board-web
> - MSA라면 서비스마다 별도 명명도 함께 알려주세요."

**처리 절차:**
- 결과를 CODING_CONVENTION.md 상단 패키지 명명 규칙 섹션에 기록
- 이 값은 Java 패키지(`com.acme`) 또는 npm scope(`@acme/web`)이며, **물리 디렉터리 이름(`backend/`, `frontend/`)과 동일할 필요 없다.**

---

## 질문 3.7 — 프론트엔드 라우팅·번들·렌더링 (필수)

> 인터프리터 ID: `q3_7`

**조건/분기:**
- 의존: `q3.frontend`
- `q3.frontend`가 없음이면 자동 스킵

> "프론트엔드 구조에 영향을 주는 선택을 알려주세요.
> 1. **라우터**: TanStack Router / React Router / Next.js App Router / Next.js Pages Router / Remix / Vue Router / SvelteKit
> 2. **빌드/번들러**: Vite / Next.js 내장 / Webpack / Turbopack
> 3. **렌더링**: CSR / SSR / SSG / ISR / Hybrid
> 4. **서버 데이터**: TanStack Query / SWR / RTK Query / Apollo(GraphQL) / tRPC
> 5. **폼**: react-hook-form / formik / 직접 / 프레임워크 내장"

**처리 절차:**
- TanStack Router 선택 → `src/routes/` 구조 강제 → PROJECT_STRUCTURE.md 반영
- Next.js App Router 선택 → `app/` 디렉토리·server components 분리 → CODING_CONVENTION.md 반영
- `profile.json.architecture.frontend_router` 기록

---

## 질문 4 — 리포 구성 (→ PROJECT_STRUCTURE + ARCHITECTURE)

> 인터프리터 ID: `q4`

**조건/분기:**
- 의존: `q3_5` (아키텍처 스타일)

| q3_5 값 | 표시할 옵션 | 권장 | 디렉토리 트리 예 |
|---|---|---|---|
| `monolith` | ① 모노레포 / ② 멀티레포 | 모노레포 | `backend/src/main/...`, `frontend/src/...` |
| `modular_monolith` | ① 모노레포 (사실상 필수) | 모노레포 | `backend/modules/{auth,post,...}/`, `frontend/src/features/{auth,post,...}/` |
| `msa` | ① 멀티레포 / ② Nx·Turborepo 모노레포 / ③ Hybrid | Nx 모노레포 | `services/{auth-service,...}/`, `apps/web/`, `libs/shared-types/` |
| `baas` | (자동 결정: frontend 단일 리포) | — | `web/` |

> AI 처리 지침: q3_5 답변을 먼저 확인하고 해당 행의 옵션만 제시한다. `baas`이면 질문 없이 자동 결정한다.

**처리 절차:**
- `profile.json.architecture.repo_layout` 기록 (예: `monorepo`, `multirepo`, `nx_mono`, `hybrid`)
- PROJECT_STRUCTURE.md 디렉토리 트리 초안을 해당 조합으로 생성
- ARCHITECTURE.md 모듈 경계·통신 다이어그램에 반영

---

## 질문 5 — 인증·보안 (→ SECURITY)

> 인터프리터 ID: `q5`

**조건/분기:**
- 의존: `q3_5` (MSA면 JWT 권장으로 정렬)

> "인증 방식을 선택해 주세요.
> 1. 세션 기반 (서버 세션 + 쿠키) — 모놀리스에 자연스러움
> 2. JWT (Access + Refresh) — MSA/SPA에 자연스러움
> 3. 소셜 로그인 (OAuth2 / OIDC) — 외부 IdP 위임
> 4. 두 가지 이상 혼합
> 5. 없음 (별도 요구 없음)"

**mvp/production 추가 질문:**
- 2FA: 없음 / TOTP(Google Authenticator) / SMS / Email / WebAuthn(Passkey)
- Magic link 사용 여부
- 비밀번호 정책: 최소 길이 / 복잡도 / 만료·재사용 금지
- 토큰 정책 (JWT 선택 시): Access TTL / Refresh TTL / 로테이션 / 블랙리스트(Revocation List)
- 민감 데이터 처리: 개인정보·결제 정보 포함 여부

**처리 절차:**
- SECURITY.md "인증", "비밀번호 정책", "토큰 정책" 섹션 작성
- `financial`/`healthcare` 유형이면 비밀번호·감사 로그 정책 강제 기록

---

## 질문 5b — 외부 인증 제공자 (조건부)

> 인터프리터 ID: `q5b`

**조건/분기:**
- **조건부 — 질문 5 답변이 `소셜 로그인` 또는 `혼합`일 때만 묻기.**
- `세션`, `JWT`, `없음`만 선택 시 자동 스킵.

> "외부 OIDC/OAuth2 인증 제공자를 선택해 주세요. **선택 시 백엔드 의존성·테이블·UI 모두에 영향을 줍니다.**
>
> 글로벌: Google / Apple / GitHub / Microsoft
> 한국: Kakao / Naver / Toss / NHN PAYCO
> 기업: SAML / LDAP / Keycloak / Okta / Auth0 / Cognito
> 자체 IdP 운영 여부, PKCE/Refresh Token 정책"

**처리 절차:**
- SECURITY.md + ADR.md + 필요 시 `auth/oidc` 디렉토리 구조까지 반영

---

## 질문 6a — 코딩 스타일 가이드 (→ CODING_CONVENTION)

> 인터프리터 ID: `q6a`
> 옵션·매트릭스 상세: [`.harness/questions.yaml`](.harness/questions.yaml) 참조

**조건/분기:**
- 의존: `q3.backend`, `q3.frontend`

| q3.backend | 표시할 backend 옵션 |
|---|---|
| spring-boot-3 (Java) | Google Java Style / Oracle Code Conventions / 자체 정의 |
| spring-boot-3 (Kotlin) | ktlint 기본 / Detekt + 자체 / 자체 |
| nestjs | Airbnb TS / StandardJS / Prettier + ESLint recommended / Biome / 자체 |
| fastapi / django | PEP 8 + Black / Ruff / 자체 |
| gin / echo / fiber | gofmt + golangci-lint (사실상 표준) |
| aspnet | .editorconfig + Roslyn analyzer / 자체 |
| actix / axum | rustfmt + clippy |
| (백엔드 없음) | (backend 옵션 스킵) |

| q3.frontend | 표시할 frontend 옵션 |
|---|---|
| react-18 / nextjs / remix | Airbnb JS / StandardJS / Prettier + ESLint recommended / Biome / 자체 |
| vue3 / nuxt | Vue 공식 스타일 가이드 + Prettier / Biome / 자체 |
| svelte / sveltekit | Svelte 공식 + Prettier / Biome / 자체 |
| (프론트 없음) | (frontend 옵션 스킵) |

> AI 처리 지침: `q3.backend`가 없으면 backend 표 스킵. `q3.frontend`가 없으면 frontend 표 스킵. Spring Boot이고 Java/Kotlin 미명시면 Java 행 제시.

**처리 절차:**
- 답변을 CODING_CONVENTION.md "스타일 가이드" 섹션에 기록

---

## 질문 6b — 린터·포매터·자동화 (→ CODING_CONVENTION)

> 인터프리터 ID: `q6b`
> 옵션·매트릭스 상세: [`.harness/questions.yaml`](.harness/questions.yaml) 참조

**조건/분기:**
- 의존: `q6a`, `q3.backend`, `q3.frontend`
- 대부분 q6a 답변과 함께 자동 권장됨 — AI가 최적 도구를 먼저 제시하고 사용자가 수정할 수 있도록 한다.

| q3.backend | 권장 backend 도구 |
|---|---|
| spring-boot-3 (Java) | Spotless + Checkstyle |
| spring-boot-3 (Kotlin) | ktlint + Detekt |
| nestjs | ESLint + Prettier |
| fastapi / django | Black + Ruff |
| gin / echo / fiber | golangci-lint |
| aspnet | dotnet format |

| q3.frontend | 권장 frontend 도구 |
|---|---|
| react-18 / nextjs / remix / vue3 / svelte | ESLint + Prettier (권장) / Biome (단일 도구) |

Pre-commit hook: lint-staged + husky / pre-commit(Python) / lefthook / 사용 안 함

> AI 처리 지침: pre-commit hook 선택 시 설치 명령 자동 안내. frontend 없으면 frontend 도구 스킵.

**처리 절차:**
- CODING_CONVENTION.md "자동화" 섹션에 기록
- pre-commit hook 선택 시 설치 명령 안내 (예: `npx husky-init && npm install -D lint-staged`)

---

## 질문 6c — Git·협업 컨벤션 (→ CODING_CONVENTION)

> 인터프리터 ID: `q6c`

> "Git·협업 컨벤션을 알려주세요.
> - 커밋 메시지: Conventional Commits (권장) / Gitmoji / Angular / 자체 / 자유
> - 브랜치 명명: `feat/<task>-<runId>` (하네스 기본·권장) / git-flow / GitHub Flow / 자체
> - 머지 정책: squash merge (권장) / rebase / merge commit
> - PR/MR 리뷰 정책: 최소 1명 / 2명 + CODEOWNERS / 임의"

**처리 절차:**
- CODING_CONVENTION.md "Git·협업 컨벤션" 섹션에 기록
- 하네스 기본 브랜치 명명(`feat/<task>-<runId>`)을 변경할 경우, `execute.py`의 `_branch_name()` 메서드를 함께 수정해야 함을 안내

---

## 질문 7a — 테마 (→ UI_GUIDE)

> 인터프리터 ID: `q7a`

**조건/분기:**
- 의존: `q3.frontend` — frontend가 없으면 자동 스킵

> "테마 정책을 선택해 주세요.
> 1. 라이트 모드만
> 2. 다크 모드만
> 3. 둘 다 지원 — 사용자 수동 토글
> 4. 둘 다 지원 — 시스템 따름(`prefers-color-scheme`) + 사용자 override (가장 권장)"

**처리 절차:**
- UI_GUIDE.md "테마" 섹션 생성
- 4번 선택 시 CSS 변수·`html[data-theme="dark"]` 패턴 권장 안내

---

## 질문 7b — 컴포넌트 시스템·디자인 토큰 (→ UI_GUIDE)

> 인터프리터 ID: `q7b`
> 옵션·매트릭스 상세: [`.harness/questions.yaml`](.harness/questions.yaml) 참조

**조건/분기:**
- 의존: `q3_7` (프론트 라우팅·번들), `q3.frontend`
- frontend가 없으면 자동 스킵

| q3_7.router | 표시할 컴포넌트 옵션 |
|---|---|
| TanStack Router / React Router / Remix | shadcn/ui + Radix + Tailwind (권장) / Mantine / Chakra UI / MUI / Ant Design / Headless UI / 자체 |
| Next.js App Router / Next.js Pages Router | 위 React 옵션 + Next UI / 자체 |
| Vue Router (vue3 / nuxt) | Element Plus / Naive UI / Vuetify / PrimeVue / Headless UI Vue / 자체 |
| SvelteKit | shadcn-svelte / Skeleton / Carbon / 자체 |

추가:
- Tailwind CSS 사용 여부
- 디자인 토큰: Style Dictionary / Tailwind config 기반 / 자체 JSON / 없음
- CSS-in-JS: Emotion / styled-components / 사용 안 함

> AI 처리 지침: q3_7.router 값을 먼저 확인하고 해당 행 옵션만 제시한다.

**처리 절차:**
- UI_GUIDE.md "컴포넌트 시스템", "디자인 토큰" 섹션 생성

---

## 질문 7c — UI 톤 (→ UI_GUIDE)

> 인터프리터 ID: `q7c`

**조건/분기:**
- 의존: `q0c` (project_type)
- `financial` 선택 시 "유머·캐주얼" 톤은 경고 표시
- frontend가 없으면 자동 스킵

> "UI 톤을 알려주세요.
> 1. 산업 분류: 업무/B2B 도구 / 컨슈머/B2C 서비스 / 데이터·관리툴 / 게임·엔터 / 핀테크·보안 / 헬스·의료 / 공공·정부
> 2. 톤 키워드 (복수 선택): 공식적·신뢰감 / 친근·일상 / 미니멀·여백 / 데이터 밀도 / 유머·캐주얼
> 3. 컬러 톤: 중립 회색 강조 / 단일 브랜드 강조색 / 파스텔·소프트 / 비비드·강렬"

**처리 절차:**
- UI_GUIDE.md "디자인 원칙" 섹션 생성

---

## 질문 7d — 폼팩터·반응형 (→ UI_GUIDE)

> 인터프리터 ID: `q7d`

**조건/분기:**
- 의존: `q3_7` (프론트 라우팅), `q3.frontend`
- React Native / Flutter 옵션은 q3_7이 해당 선택인 경우에만 표시
- frontend가 없으면 자동 스킵

> "폼팩터를 선택해 주세요.
> 1. 데스크탑 우선 + 반응형 (대시보드·관리툴)
> 2. 모바일 우선 + 반응형 (소비자 서비스)
> 3. 데스크탑·모바일 분리 UI (별도 라우트)
> 4. 모바일 네이티브/하이브리드 (React Native / Flutter / Capacitor / PWA)
>
> 브레이크포인트 권장: 640 / 768 / 1024 / 1280 px (Tailwind 기본)"

**처리 절차:**
- UI_GUIDE.md "폼팩터" 섹션 생성
- 4번 선택 시 모바일 네이티브 추가 설정 안내

---

## 질문 7e — 접근성·국제화 (→ UI_GUIDE)

> 인터프리터 ID: `q7e`

**조건/분기:**
- 의존: `q0a` (stage), `q3.frontend`
- mvp/production이면 강제 질문, prototype은 선택
- frontend가 없으면 자동 스킵

> "접근성·국제화 정책을 알려주세요.
>
> **접근성:**
> - prototype: 미정의 가능
> - mvp 권장: WCAG AA
> - production 필수: WCAG AA (공공·금융은 AAA 권장)
>
> **국제화:**
> - 한국어 단일 / 영어 단일 / 다국어 (목록 입력)
> - 다국어 시 라이브러리: react-i18next / vue-i18n / next-intl / formatjs
> - RTL(아랍어·히브리어) 지원 여부"

**처리 절차:**
- UI_GUIDE.md "접근성", "국제화" 섹션 생성
- 국제화 라이브러리는 q3_7.router와 정합 확인

---

## 질문 8 — 메뉴/화면 구성 (→ SCREEN_MAP)

> 인터프리터 ID: `q8`

**조건/분기:**
- 의존: `q0a` (stage), `q3_7` (router)
- prototype이면 선택 사항, mvp/production이면 필수

> "주요 메뉴와 각 메뉴 아래 화면을 알려주세요.
> 화면별 핵심 기능 1~3개와 접근 가능한 역할도 함께 말해주세요.
>
> 예시:
> - 메뉴: 게시판
>   - 화면: 게시글 목록 (경로: /posts, 권한: USER·ADMIN, 기능: 목록 조회·검색·글쓰기 버튼)
>   - 화면: 게시글 상세 (경로: /posts/:id, 권한: 전체, 기능: 내용 보기·댓글·수정·삭제)"

**라우팅 규칙 후속 질문 (q3_7 답변 기반으로 관련 항목만):**

| q3_7.router | 안내할 라우팅 패턴 |
|---|---|
| TanStack Router | 파일 기반 라우팅 (`src/routes/`) — 경로 파라미터 패턴 확인 |
| Next.js App Router | `app/` 디렉토리 — 중첩 레이아웃 규칙 확인 |
| React Router / Vue Router / SvelteKit | 경로 파라미터 패턴: `/posts/:id` 또는 `/posts/[id]` |

공통 추가 질문:
- Query string 정책: 검색·필터·페이지네이션 위치 (path vs query)
- Modal/Drawer 라우트: URL 반영 (`/posts/123/comments`) 또는 상태만

**처리 절차:**
- SCREEN_MAP.md에 사이트맵(mermaid), 화면 목록 표, 화면별 상세 섹션, 주요 사용자 플로우 생성
- 각 화면의 API_GUIDE.md 엔드포인트·SCHEMA.md 엔티티와 역참조 링크 포함
- 라우트 규칙은 PROJECT_STRUCTURE.md의 `src/routes/` 트리에도 반영
- **`SCREEN_MAP.md` 상단 `<!-- AUTO-GENERATED SKELETON -->` 주석을 반드시 제거한다** (잔존 시 validate_docs가 오류로 감지)

---

## 질문 9 — 테스트 전략 (→ TESTING)

> 인터프리터 ID: `q9`
> 옵션·매트릭스 상세: [`.harness/questions.yaml`](.harness/questions.yaml) 참조

**조건/분기:**
- 의존: `q3.backend`, `q3.frontend`, `q3_5`
- MSA(`q3_5=msa`)이면 Contract test 강제 권장

> "테스트 전략을 알려주세요.
> - Backend: 단위 테스트 / 통합 테스트?
> - Frontend: Vitest + RTL? Playwright E2E?
> - 커버리지 목표: 없음 / 60% / 80%"

**단계별 추가 질문:**

mvp/production 추가:
- 테스트 피라미드 비율: Unit 70 / Integration 20 / E2E 10 (기본) — 또는 자체

| q3.backend | 모킹 도구 옵션 |
|---|---|
| spring-boot-3 | Mockito / MockK / TestContainers / WireMock |
| nestjs | Jest mock / Vitest / MSW / Supertest |
| fastapi / django | pytest-mock / responses / VCR.py |
| gin / echo | testify / gomock / httptest |

| q3.frontend | 모킹 도구 옵션 |
|---|---|
| react-18 / nextjs | MSW (Mock Service Worker) / Vitest / Playwright |
| vue3 | Vitest + Vue Test Utils / Playwright |
| svelte | Vitest / Playwright |

공통:
- 테스트 데이터: Faker / 고정 Fixture / snapshot / 빌더 패턴
- Contract test: Pact (MSA 시 강력 권장)

> AI 처리 지침: q3_5가 `msa`이면 Contract test 필수 권장 후 ADR에 기록. 백엔드/프론트 없으면 해당 모킹 도구 표 스킵.

**처리 절차:**
- TESTING.md 섹션 자동 생성
- 커버리지 목표: prototype 없음 / mvp 60 / production 80 (기본 — 사용자 변경 가능)

---

## 질문 10 — DB 스키마 (→ SCHEMA)

> 인터프리터 ID: `q10`

**조건/분기:**
- 의존: `q3.db`, `q0c` (project_type)
- prototype이면 선택 사항, mvp/production이면 필수
- `data_heavy` project_type이면 샤딩 질문 강제

> "데이터베이스 구조를 알려주세요.
> - 어떤 DBMS를 사용하나요? (PostgreSQL / MySQL / MariaDB / Oracle / MongoDB / 기타)
> - 마이그레이션 도구: Flyway / Liquibase / 없음
> - 주요 테이블이나 엔티티를 열거해 주세요. (예: 사용자, 게시글, 댓글)
> - 데이터 간 주요 관계를 설명해 주세요."

**추가 구성 질문:**
- DB 역할 분리: 단일 DB / 운영+분석(Read Replica) / 운영+캐시(Redis) / 운영+검색(Elastic·OpenSearch)
- 읽기 복제(Replica Read) 사용 여부 + 일관성 정책 (read-after-write 보장 필요?)
- 샤딩: 없음 / Horizontal (data_heavy이면 강제 질문, 샤드 키 입력)
- 공통 컬럼 정책:
  - audit timestamps: `created_at`, `updated_at` 자동 채우기
  - 작성자 기록: `created_by`, `updated_by`
  - soft delete: `deleted_at` 사용 여부
  - 낙관적 락: `version` 컬럼 사용 여부

**처리 절차:**
- DBMS, 마이그레이션 도구, 파일 위치 설정
- 주요 테이블과 컬럼을 테이블 형식으로 초안 생성
- JPA 단방향/양방향 매핑 방식 제안 (단방향/양방향, LAZY/EAGER)
- 명명 규칙(`V{버전}__{설명}.sql`) 기록
- ER 다이어그램을 Mermaid `erDiagram` 형식으로 초안 생성
- SCHEMA.md에 "DB 구성", "공통 컬럼 정책" 섹션 자동 생성

---

## 질문 11 — 로컬 실행 환경 (Docker Compose)

> 인터프리터 ID: `q11`

**조건/분기:**
- 의존: `q10` (DB 선택), `q3.backend`

> "로컬 개발에서 별도 실행이 필요한 인프라가 있나요? 있으면 `docker-compose.yml`을 자동 생성합니다.
> - DBMS: PostgreSQL / MySQL / MongoDB / ...
> - 캐시: Redis / Memcached
> - 메시지 브로커: Kafka(+KRaft) / RabbitMQ / NATS
> - 검색: OpenSearch / ElasticSearch / Meilisearch
> - 객체 스토리지(개발용): MinIO / LocalStack S3
> - 메일 캡처: MailHog / MailPit
> - 관측: Prometheus + Grafana / Jaeger / Tempo
>
> 선택한 항목을 묶어 `docker-compose.yml`과 `.env.example`을 생성할까요?"

> AI 처리 지침: q10에서 선택한 DBMS는 이미 포함으로 표시. 선택 안 된 항목만 추가 선택.

**처리 절차 (YES 시):**
- 루트의 `docker-compose.yml` (또는 `docker/compose.local.yml`)
- `.env.example` (호스트/포트/계정 기본값)
- PROJECT_STRUCTURE.md + DEPLOYMENT.md에 기동 방법 문단 자동 추가

---

## 질문 12 — 배포 형태 (→ DEPLOYMENT)

> 인터프리터 ID: `q12`

**조건/분기:**
- 의존: `q3.backend`, `q0a` (stage)
- prototype: 선택 사항. mvp: 권장. **production: 필수.**

> "프로덕션 배포 방식을 알려주세요.
> 1. Docker 이미지 (registry push 후 k8s/ECS/Cloud Run 등에서 실행)
> 2. Jar/War 직접 배포 (서버에 SCP/Ansible 등)
> 3. Serverless (AWS Lambda, Cloud Functions)
> 4. PaaS (Fly.io, Railway, Heroku)
> 5. 정적 호스팅 + 분리 API (Vercel/Netlify + 별도 API 서버)
> 6. 사내 온프레미스 + 자체 스크립트"

**Docker 이미지 선택 시 후속 질문:**
- 베이스 이미지 선호: distroless / alpine / debian-slim / ubuntu
- 멀티스테이지 빌드 사용 여부
- 이미지 레지스트리: DockerHub / GHCR / GitLab / ECR / ACR / private
- 이미지 태깅 정책: semver / git-sha / branch / latest
- 빌드 도구: `Dockerfile` / Jib / Buildpacks / ko

**처리 절차:**
- Docker 선택 시: `Dockerfile`(들), `.dockerignore`, 필요 시 `compose.prod.yml` 또는 k8s 매니페스트 스켈레톤 생성
- DEPLOYMENT.md 생성 (배포 절차·이미지 태깅·롤백)
- **`DEPLOYMENT.md` 상단 `<!-- AUTO-GENERATED SKELETON -->` 주석을 반드시 제거한다** (잔존 시 validate_docs가 오류로 감지)

---

## 질문 13 — MCP 추가 안내

> 인터프리터 ID: `q13`

> "개발에 추가로 필요한 도구가 있나요?
> - GitLab/GitHub API 연동 (MR/PR 자동화)
> - DB 스키마 조회 (postgres MCP)
> - E2E 테스트 자동화 (playwright MCP)
>
> 세부 MCP 설정은 /a2m_mcp 명령을 사용하세요."

---

## 문서 일괄 생성

모든 질문이 완료되면 (`ask_questions.py done` exit 0):

0. **질문 3 직후 반영**이 완료되었는지 확인한다. 미완료면 `CLAUDE.md`·`profile.json`·선택 의존 docs를 먼저 맞춘다.
1. 모든 답변을 기반으로 `.harness/docs/*` 를 생성하라:
   - prototype: PRD, ARCHITECTURE, ADR, UI_GUIDE (4종)
   - mvp: 위 + CODING_CONVENTION, PROJECT_STRUCTURE, SECURITY, TESTING, API_GUIDE, SCHEMA, SCREEN_MAP (11종)
   - production: 위 + DEPLOYMENT (12종)
   - 질문 11에서 Docker Compose 생성 선택 시: 루트의 `docker-compose.yml` + `.env.example`
   - 질문 12에서 Docker 이미지 선택 시: `Dockerfile` + `.dockerignore`
2. 참고 프로젝트가 있으면 각 문서 하단에 "## 참고 자료" 섹션 추가.
3. 단계(stage)에 맞는 섹션을 채우고, 미해당 섹션은 "이 단계에서는 생략 — 다음 단계 진입 시 작성" 메모를 남긴다.
4. 생성된 `.harness/docs/*` 미리보기를 사용자에게 보여주고 확인 받기.
5. 확인된 파일을 저장.

---

완료 후:

6. **1차 syntactic 검증** 자동 실행:
   ```
   python .harness/scripts/validate_docs.py --stage <stage>
   ```
   오류가 있으면 즉시 수정한다.

7. **2차 AI 페르소나 검증** 자동 실행:
   ```
   python .harness/scripts/review_docs.py --stage <stage>
   ```
   - 임계점수 미달 시 auto_fillable 갭은 자동 보완(diff 확인), needs_decision 갭은 Q&A
   - 최대 3회 반복 후 종료
   - 통과 시: `페르소나 리뷰 통과 (평균 {score}점)`
   - 미통과 시: 남은 갭 목록과 함께 종료 — 사람의 결단이 필요한 영역 인계

> "docs 생성 및 충실도 검증이 완료되었습니다. 이제 /a2m_start로 개발을 시작하세요."

---

## 부록 A — profile.json 확장 설정

`profile.json`에 `context` 블록을 추가하면 각 step에서 AI가 읽어들이는 문서 범위를 제어할 수 있습니다.

```json
{
  "context": {
    "always_inject_docs": ["PRD", "CODING_CONVENTION"],
    "max_doc_kb_per_step": 64
  }
}
```

- `always_inject_docs`: 매 step마다 전문이 항상 주입되는 문서 목록 (기본: `["PRD", "CODING_CONVENTION"]`)
- `max_doc_kb_per_step`: 문서 1개당 최대 주입 크기(KB). 문서가 클 경우 초과분은 잘림 (기본: `64`)

> 나머지 docs는 이름과 1줄 요약만 주입됩니다. 특정 step에서 추가 문서가 필요하면 step frontmatter에 `relevant_docs` 를 명시하세요.

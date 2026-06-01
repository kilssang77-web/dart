> 이 문서는 스켈레톤입니다. 본 프로젝트에 맞게 재작성하세요.
> 각 섹션의 `{...}` 플레이스홀더와 `<!-- 예시 -->` 마커가 달린 항목을 교체하세요.

# 프로젝트 구조

---

## 레포 전략

> 이 섹션의 목적: 모노레포 vs 멀티레포 선택과 그 이유를 기록한다.

- 전략: {모노레포 / 멀티레포}
- 이유: {선택 근거}
- 구성: {구성 설명}

---

## 전체 디렉토리 트리

> 이 섹션의 목적: 실제 파일 시스템 구조를 문서화한다. 주요 폴더의 역할을 주석으로 달아 신규 팀원이 즉시 파악할 수 있도록 한다.

**예시 — Spring Boot + React 모노레포** <!-- 예시 -->
```
project-root/
├── backend/
│   ├── src/
│   │   ├── main/
│   │   │   ├── java/com/example/
│   │   │   │   ├── BoardApplication.java     # Spring Boot 진입점
│   │   │   │   ├── config/                   # Spring 설정(Security, CORS, JPA 등)
│   │   │   │   ├── domain/
│   │   │   │   │   ├── post/                 # 게시글 도메인
│   │   │   │   │   │   ├── Post.java         # 엔티티
│   │   │   │   │   │   ├── PostRepository.java
│   │   │   │   │   │   ├── PostService.java
│   │   │   │   │   │   └── PostController.java
│   │   │   │   │   └── user/                 # 사용자 도메인
│   │   │   │   └── common/                   # 공통(예외, 페이지네이션 등)
│   │   │   └── resources/
│   │   │       ├── db/migration/             # Flyway SQL
│   │   │       └── application.yml
│   │   └── test/                             # 단위·통합 테스트
│   └── build.gradle
├── frontend/
│   ├── src/
│   │   ├── api/                              # axios 인스턴스 + 도메인별 API 함수
│   │   ├── components/                       # 공통 재사용 컴포넌트
│   │   ├── features/
│   │   │   ├── post/                         # 게시글 기능 모듈
│   │   │   └── auth/                         # 인증 기능 모듈
│   │   ├── pages/                            # 라우트 페이지
│   │   ├── store/                            # Zustand 스토어
│   │   ├── types/                            # 전역 타입 정의
│   │   └── main.tsx                          # React 진입점
│   ├── package.json
│   └── vite.config.ts
├── docs/                                     # 프로젝트 문서
├── .harness/                                 # 하네스 런타임 메타 (git 추적 제외)
└── phases/                                   # 하네스 실행 이력
```

{실제 프로젝트 디렉토리 트리}

---

## 빌드 · 실행 명령

> 이 섹션의 목적: 프로젝트를 처음 받은 팀원이 명령 몇 줄로 개발 환경을 구동할 수 있도록 한다.

### 사전 요구사항

- {예: Java 21+, Node.js 20+, Docker (DB용)}

### Backend

```bash
# 의존성 설치 및 빌드
./gradlew build

# 개발 서버 실행
./gradlew bootRun

# 테스트
./gradlew test

# 테스트 (통합 포함)
./gradlew integrationTest
```

### Frontend

```bash
# 의존성 설치
npm install

# 개발 서버 실행
npm run dev

# 프로덕션 빌드
npm run build

# 린트
npm run lint

# 테스트
npm test
```

### Docker (로컬 인프라)

```bash
# DB 등 로컬 인프라 실행
docker compose up -d

# 중지
docker compose down
```

---

## 환경변수

> 이 섹션의 목적: 필요한 환경변수를 열거하여 설정 누락으로 인한 실행 오류를 방지한다. 실제 값은 `.env` 파일에 두고 `.env.example`만 커밋한다.

### Backend (`backend/.env` 또는 `application-local.yml`)

| 변수 | 설명 | 예시값 |
|------|------|--------|
| `SPRING_DATASOURCE_URL` | DB 연결 URL | `jdbc:postgresql://localhost:5432/board` |
| `SPRING_DATASOURCE_USERNAME` | DB 사용자 | `board_user` |
| `SPRING_DATASOURCE_PASSWORD` | DB 패스워드 | `(secret)` |
| `JWT_SECRET` | JWT 서명 키 (256bit+) | `(secret)` |
| `JWT_EXPIRATION_MS` | 토큰 만료 시간(ms) | `3600000` |
| {추가 변수} | {설명} | {예시} |

### Frontend (`frontend/.env.local`)

| 변수 | 설명 | 예시값 |
|------|------|--------|
| `VITE_API_BASE_URL` | 백엔드 API URL | `http://localhost:8080` |
| {추가 변수} | {설명} | {예시} |

---

## 브랜치 전략

> 이 섹션의 목적: 브랜치 이름과 merge 정책을 통일하여 충돌·혼란을 줄인다.

| 브랜치 | 용도 | merge 대상 |
|--------|------|-----------|
| `main` | 프로덕션 배포 기준 | — |
| `develop` | 통합 개발 브랜치 | `main` (release 시) |
| `feat/<name>` | 기능 개발 | `develop` |
| `fix/<name>` | 버그 수정 | `develop` (긴급: `main`) |
| `feat-<task>` | 하네스 자동 생성 브랜치 | `develop` |

PR 규칙:
- {예: 최소 1인 승인 필요}
- {예: CI 통과 필수}
- {예: squash merge 사용}

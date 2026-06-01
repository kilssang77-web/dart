> 이 문서는 스켈레톤입니다. 본 프로젝트에 맞게 재작성하세요.
> 각 섹션의 `{...}` 플레이스홀더와 `<!-- 예시 -->` 마커가 달린 항목을 교체하세요.

# 코딩 컨벤션

---

## 공통

> 이 섹션의 목적: 언어·프레임워크를 불문하고 적용되는 전팀 규칙을 명시한다.

- 언어: {사용 언어 목록}
- 인코딩: UTF-8
- 줄 끝: LF
- 들여쓰기: {스페이스 N칸 / 탭}
- 파일 끝 빈줄: 1개
- 주석 언어: {한국어 / 영어}
- TODO 형식: `// TODO(작성자): 내용 — 완료 조건`

---

## Backend — Java / Spring

> 이 섹션의 목적: Java·Spring 코드 작성 시 팀이 합의한 규칙을 기록한다.

### 네이밍

| 구분 | 규칙 | 예시 |
|------|------|------|
| 클래스 | PascalCase | `PostService`, `UserRepository` |
| 메서드 / 변수 | camelCase | `findByUserId`, `pageSize` |
| 상수 | UPPER_SNAKE_CASE | `MAX_PAGE_SIZE` |
| 패키지 | lowercase | `com.example.domain.post` |

### Service 메서드 네이밍 규칙 <!-- 예시 -->

```java
// 조회: find + 대상 + By + 조건
public PostDto findPostById(Long postId) { ... }

// 생성: create + 대상
public PostDto createPost(CreatePostRequest request, Long userId) { ... }

// 수정: update + 대상
public PostDto updatePost(Long postId, UpdatePostRequest request, Long userId) { ... }

// 삭제: delete + 대상
public void deletePost(Long postId, Long userId) { ... }
```

### 레이어 규칙

- Controller: DTO만 입력받고 반환. `@Valid` 필수. 비즈니스 로직 금지
- Service: 트랜잭션 관리, 비즈니스 규칙. Repository 직접 접근만(다른 Service 호출 신중)
- Repository: JPA/쿼리 메서드. N+1 주의 — 필요 시 `@EntityGraph` 또는 fetch join
- DTO: Request/Response 분리. `@Builder` + `@Getter` 적용

### 예외 처리

```
{예외 처리 전략 — 예: @ControllerAdvice + 커스텀 ErrorResponse 포맷 사용}
```

---

## Frontend — TypeScript / React

> 이 섹션의 목적: React 컴포넌트와 TypeScript 코드 작성 규칙을 명시한다.

### 네이밍

| 구분 | 규칙 | 예시 |
|------|------|------|
| 컴포넌트 파일 | PascalCase | `PostCard.tsx`, `CommentList.tsx` |
| 훅 파일 | camelCase + use 접두 | `usePostList.ts`, `useAuth.ts` |
| 유틸/헬퍼 | camelCase | `formatDate.ts`, `validators.ts` |
| 타입/인터페이스 | PascalCase | `PostDto`, `PageResponse<T>` |

### React 훅 사용 규칙 <!-- 예시 -->

```typescript
// 서버 상태: TanStack Query 사용 (useState로 직접 관리 금지)
const { data: posts, isLoading } = useQuery({
  queryKey: ['posts', page],
  queryFn: () => postApi.getList({ page }),
});

// 전역 클라이언트 상태: Zustand 스토어 사용
const user = useAuthStore((state) => state.user);

// 로컬 UI 상태만 useState 사용
const [isOpen, setIsOpen] = useState(false);
```

### 컴포넌트 작성 규칙

- 컴포넌트는 `features/` 도메인 폴더 또는 `components/` 공통 폴더에 위치
- Props 타입은 컴포넌트 파일 내 `interface Props` 로 정의 (별도 파일 불필요)
- 직접 외부 API 호출 금지 — `api/` 레이어 경유 필수
- {추가 규칙}

---

## 파일·디렉토리 네이밍

> 이 섹션의 목적: 파일 이름 규칙을 통일하여 탐색 비용을 줄인다.

| 파일 종류 | 규칙 |
|----------|------|
| React 컴포넌트 | PascalCase + .tsx |
| 훅 | camelCase + .ts |
| 유틸/서비스 | camelCase + .ts |
| 테스트 | 원본파일명 + .test.ts(x) |
| Java 클래스 | PascalCase + .java |
| SQL 마이그레이션 | V{순번}__{설명}.sql (Flyway) |

---

## 포매터 · 린터

> 이 섹션의 목적: 코드 스타일을 자동화하여 PR에서 스타일 논쟁을 없앤다.

| 도구 | 대상 | 설정 파일 | 실행 명령 |
|------|------|----------|----------|
| {Prettier} | FE | {.prettierrc} | {npm run format} |
| {ESLint} | FE | {eslint.config.js} | {npm run lint} |
| {Checkstyle / Google Java Format} | BE | {checkstyle.xml} | {./gradlew checkstyleMain} |

---

## 커밋 메시지

> 이 섹션의 목적: 커밋 이력을 읽기 좋게 유지하고 자동 changelog 생성을 가능하게 한다.

Conventional Commits 형식을 따른다: `<type>(<scope>): <subject>`

| type | 의미 |
|------|------|
| `feat` | 새 기능 |
| `fix` | 버그 수정 |
| `docs` | 문서만 변경 |
| `refactor` | 기능 변경 없는 코드 개선 |
| `test` | 테스트 추가/수정 |
| `chore` | 빌드 설정, 의존성 등 기타 |
| `perf` | 성능 개선 |

예시:
```
feat(post): 게시글 페이지네이션 API 추가
fix(auth): 토큰 만료 후 재발급 로직 오류 수정
docs(adr): ADR-003 PostgreSQL 선택 기록 추가
```

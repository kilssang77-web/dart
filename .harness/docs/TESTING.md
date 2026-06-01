> 이 문서는 스켈레톤입니다. 본 프로젝트에 맞게 재작성하세요.
> 각 섹션의 `{...}` 플레이스홀더와 `<!-- 예시 -->` 마커가 달린 항목을 교체하세요.

# 테스트 전략

---

## 테스트 피라미드

> 이 섹션의 목적: 테스트 유형별 비율과 각 레이어에서 무엇을 검증하는지 정의한다.

```
         /\
        /E2E\         소수 (핵심 사용자 시나리오만)
       /──────\
      /통합 테스트\    API 단위, DB 통합
     /────────────\
    /  단위 테스트  \  가장 많이, 가장 빠르게
   /────────────────\
```

| 레이어 | 목표 비율 | 속도 | 도구 |
|--------|---------|------|------|
| 단위 테스트 | {예: 70%} | 빠름 (밀리초) | {JUnit 5 / Vitest} |
| 통합 테스트 | {예: 25%} | 보통 (초) | {Spring Boot Test / @DataJpaTest} |
| E2E 테스트 | {예: 5%} | 느림 (분) | {Playwright} |

---

## Backend — 단위 테스트

> 이 섹션의 목적: Service 레이어 단위 테스트 작성 방법과 규칙을 명시한다.

**도구**: JUnit 5 + Mockito + AssertJ

**대상**: Service 클래스의 비즈니스 로직 (Controller, Repository는 단위 테스트 대상 아님)

```java
// 예시 — PostService 단위 테스트 패턴 <!-- 예시 -->
@ExtendWith(MockitoExtension.class)
class PostServiceTest {

    @Mock PostRepository postRepository;
    @InjectMocks PostService postService;

    @Test
    @DisplayName("게시글 조회 시 존재하지 않는 ID면 PostNotFoundException 발생")
    void findPost_notFound_throwsException() {
        // given
        given(postRepository.findById(999L)).willReturn(Optional.empty());

        // when & then
        assertThatThrownBy(() -> postService.findPostById(999L))
            .isInstanceOf(PostNotFoundException.class);
    }
}
```

---

## Backend — 통합 테스트

> 이 섹션의 목적: API 엔드포인트와 DB 통합을 검증하는 테스트 전략을 명시한다.

**도구**: `@SpringBootTest` + `MockMvc` + Testcontainers (또는 H2)

```java
// 예시 패턴 outline
@SpringBootTest
@AutoConfigureMockMvc
class PostControllerIntegrationTest {
    @Autowired MockMvc mockMvc;

    @Test
    void getPost_existingId_returns200() throws Exception { ... }
}
```

**DB 전략**: {예: Testcontainers PostgreSQL (운영과 동일 DB) / H2 인메모리}

---

## Frontend — 컴포넌트 테스트

> 이 섹션의 목적: React 컴포넌트 테스트 작성 방법을 정의한다.

**도구**: Vitest + React Testing Library

**원칙**: 구현 세부사항이 아닌 사용자 행동을 테스트한다.

```typescript
// 예시 패턴 outline
test('게시글 목록이 렌더링되면 제목이 표시된다', async () => {
  renderWithProviders(<PostList />);
  expect(await screen.findByText('테스트 게시글')).toBeInTheDocument();
});
```

---

## Frontend — E2E 테스트

> 이 섹션의 목적: 핵심 사용자 시나리오를 브라우저 수준에서 검증하는 전략을 명시한다.

**도구**: {예: Playwright}

**대상 시나리오** (우선순위 상위 N개만):
1. {예: 로그인 → 게시글 작성 → 목록 확인}
2. {예: 댓글 작성 → 삭제}
3. {추가 시나리오}

---

## 픽스처 · 시드 데이터

> 이 섹션의 목적: 테스트 데이터를 일관되게 관리하는 방법을 명시한다.

- Backend: {예: `@BeforeEach`에서 직접 삽입 / Flyway test fixture SQL}
- Frontend: {예: MSW(Mock Service Worker)로 API mocking}
- E2E: {예: 테스트 전 API 호출로 데이터 시드, 후 정리}

---

## 커버리지 목표

> 이 섹션의 목적: 최소 커버리지 임계값을 설정하여 테스트 공백을 방지한다. 단계에 따라 값이 달라진다.

| 단계 | 목표 | 측정 범위 |
|------|------|----------|
| prototype | 필수 없음 | — |
| mvp | {예: 라인 커버리지 60% 이상} | {예: service 패키지} |
| production | {예: 라인 커버리지 80% 이상} | {예: domain + service 패키지} |

```bash
# Backend 커버리지 리포트
./gradlew test jacocoTestReport

# Frontend 커버리지 리포트
npm run coverage
```

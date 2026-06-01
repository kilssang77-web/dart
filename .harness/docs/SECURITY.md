> 이 문서는 스켈레톤입니다. 본 프로젝트에 맞게 재작성하세요.
> 각 섹션의 `{...}` 플레이스홀더와 `<!-- 예시 -->` 마커가 달린 항목을 교체하세요.

# 보안 가이드

---

## 인증 · 인가

> 이 섹션의 목적: 누가 어떤 방법으로 접근 권한을 얻는지, 권한 계층은 어떻게 구성하는지 기록한다.

### 인증 방식

- 방식: {예: JWT (access token + refresh token)}
- Access Token 만료: {예: 1시간}
- Refresh Token 만료: {예: 7일, Redis 저장}
- 발급 엔드포인트: {예: `POST /api/auth/login`}

### 권한 계층

| 역할 | 설명 | 접근 범위 |
|------|------|----------|
| `ROLE_GUEST` | 미인증 사용자 | {예: 게시글 읽기만} |
| `ROLE_USER` | 인증된 일반 사용자 | {예: 게시글 CRUD (본인 것)} |
| `ROLE_ADMIN` | 관리자 | {예: 모든 리소스 관리} |

### Spring Security 설정 요약

```java
// 예시 — 실제 설정으로 교체하세요
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/posts/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
);
```

---

## 비밀값 관리

> 이 섹션의 목적: 비밀값이 코드나 로그에 노출되지 않도록 하는 정책을 명시한다.

**절대 금지 사항:**
- 소스 코드에 비밀값 하드코딩
- `git add`로 `.env` 파일 커밋
- 로그에 패스워드·토큰 출력

**허용 관리 방식:**
- 개발: `.env` 파일 (`.gitignore`에 추가됨)
- 운영: {예: AWS Secrets Manager / HashiCorp Vault / K8s Secret}
- CI/CD: {예: GitLab CI Variables / GitHub Actions Secrets}

---

## 입력 검증

> 이 섹션의 목적: 외부 입력을 처리하는 지점에서 어떻게 검증하는지 기술한다.

### Backend

- 모든 API 요청에 `@Valid` 어노테이션 적용 (`javax.validation`)
- Bean Validation 어노테이션 사용: `@NotBlank`, `@Size`, `@Email`, `@Pattern`
- SQL Injection: JPA 파라미터 바인딩 사용 (쿼리 문자열 직접 조합 금지)
- XSS: 응답 Content-Type을 `application/json`으로 고정 (HTML 직접 반환 금지)

### Frontend

- `dangerouslySetInnerHTML` 사용 금지 (불가피 시 DOMPurify 사용)
- 사용자 입력 기반 URL 조작 금지
- {추가 규칙}

---

## OWASP Top 10 체크리스트

> 이 섹션의 목적: 주요 웹 취약점에 대한 팀의 대응 현황을 추적한다. 단계에 따라 작성 깊이를 조정한다.

| OWASP 항목 | 상태 | 대응 방법 |
|-----------|------|----------|
| A01 - 접근 제어 실패 | {✅/⚠️/❌} | {방법} |
| A02 - 암호화 실패 | {✅/⚠️/❌} | {방법} |
| A03 - 인젝션 | {✅/⚠️/❌} | {방법} |
| A04 - 안전하지 않은 설계 | {✅/⚠️/❌} | {방법} |
| A05 - 보안 구성 오류 | {✅/⚠️/❌} | {방법} |
| A06 - 취약하고 오래된 구성요소 | {✅/⚠️/❌} | {방법} |
| A07 - 식별 및 인증 실패 | {✅/⚠️/❌} | {방법} |
| A08 - 소프트웨어/데이터 무결성 실패 | {✅/⚠️/❌} | {방법} |
| A09 - 보안 로깅/모니터링 실패 | {✅/⚠️/❌} | {방법} |
| A10 - SSRF | {✅/⚠️/❌} | {방법} |

---

## 로깅에서 PII 마스킹

> 이 섹션의 목적: 개인정보(이메일, 전화번호, 이름 등)가 로그에 그대로 남지 않도록 하는 정책을 명시한다.

- 이메일: `j***@example.com` 형식으로 마스킹
- 패스워드: **절대 로그 출력 금지**
- 주민등록번호·카드번호: 법적 요구사항에 따라 마스킹
- 구현 방법: {예: Logback PatternLayout 커스터마이징 / MDC 활용}

---

## 의존성 보안 스캔

> 이 섹션의 목적: 알려진 취약점이 있는 의존성을 정기적으로 검출하는 프로세스를 정의한다.

```bash
# Frontend — npm audit
npm audit --audit-level=high

# Backend — OWASP Dependency Check (Gradle)
./gradlew dependencyCheckAnalyze
```

- 실행 주기: {예: CI/CD 파이프라인에서 PR마다 + 주 1회 scheduled}
- 임계값: {예: high 이상 발견 시 빌드 실패}

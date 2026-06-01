> 이 문서는 스켈레톤입니다. 본 프로젝트에 맞게 재작성하세요.
> 각 섹션의 `{...}` 플레이스홀더와 `<!-- 예시 -->` 마커가 달린 항목을 교체하세요.

# API 가이드

---

## REST 규약

> 이 섹션의 목적: API 설계 시 일관성을 보장하기 위한 기본 규칙을 명시한다.

### URL 설계

- 리소스 이름은 복수형 명사: `/api/posts`, `/api/users`
- 계층 구조 표현: `/api/posts/{postId}/comments`
- 동사 사용 금지 (동사 역할은 HTTP 메서드가 담당)
- 케이싱: kebab-case (`/api/user-profiles`)

### HTTP 메서드

| 메서드 | 용도 | 멱등성 |
|--------|------|--------|
| GET | 조회 | ✅ |
| POST | 생성 | ❌ |
| PUT | 전체 수정 | ✅ |
| PATCH | 부분 수정 | ❌ (구현 따라 다름) |
| DELETE | 삭제 | ✅ |

### API 기본 경로

- Base URL: `{예: /api/v1}`
- Content-Type: `application/json` (요청·응답 모두)

---

## 에러 응답 포맷

> 이 섹션의 목적: 모든 에러 응답이 동일한 구조를 갖도록 하여 클라이언트 에러 처리를 단순화한다.

**표준 에러 응답 구조:**

```json
{
  "status": 400,
  "code": "VALIDATION_ERROR",
  "message": "요청 데이터가 유효하지 않습니다.",
  "errors": [
    { "field": "title", "message": "제목은 1자 이상 200자 이하여야 합니다." }
  ],
  "timestamp": "2026-05-13T10:30:00+09:00"
}
```

**에러 코드 카탈로그:**

| HTTP 상태 | code | 의미 |
|-----------|------|------|
| 400 | `VALIDATION_ERROR` | 입력값 검증 실패 |
| 401 | `UNAUTHORIZED` | 인증 필요 |
| 403 | `FORBIDDEN` | 권한 없음 |
| 404 | `RESOURCE_NOT_FOUND` | 리소스 없음 |
| 409 | `DUPLICATE_RESOURCE` | 중복 리소스 |
| 500 | `INTERNAL_ERROR` | 서버 오류 |
| {추가} | `{코드}` | {의미} |

---

## 페이지네이션

> 이 섹션의 목적: 목록 API의 페이지네이션 방식을 통일한다.

**방식**: {예: offset 기반 (page, size) / cursor 기반}

**요청 파라미터:**

| 파라미터 | 기본값 | 설명 |
|---------|--------|------|
| `page` | `0` | 페이지 번호 (0-indexed) |
| `size` | `20` | 페이지 크기 (최대: `100`) |
| `sort` | `createdAt,desc` | 정렬 기준 |

**응답 포맷 (예시):** <!-- 예시 -->

```json
{
  "content": [ {...}, {...} ],
  "page": {
    "number": 0,
    "size": 20,
    "totalElements": 150,
    "totalPages": 8
  }
}
```

---

## 버저닝

> 이 섹션의 목적: API 버전 관리 전략을 명시하여 하위 호환성 파괴를 방지한다.

- 전략: {예: URL 경로 버저닝 `/api/v1`, `/api/v2` / 헤더 버저닝 `Accept: application/vnd.api+json;version=2`}
- 버전 올림 기준: {예: Breaking change 발생 시에만 (필드 제거, 타입 변경 등)}
- 구 버전 유지 기간: {예: 신 버전 출시 후 6개월}

---

## 인증 헤더

> 이 섹션의 목적: API 요청 시 인증을 어떻게 전달하는지 명시한다.

```
Authorization: Bearer {access_token}
```

- 토큰 발급: `POST /api/auth/login`
- 토큰 재발급: `POST /api/auth/refresh`
- 토큰 만료 시: `401 UNAUTHORIZED` 응답 → 클라이언트가 refresh 토큰으로 재발급

---

## 응답 캐시

> 이 섹션의 목적: 캐시 가능한 엔드포인트와 캐시 정책을 명시한다.

| 엔드포인트 | 캐시 전략 | TTL |
|-----------|---------|-----|
| `GET /api/posts` | {예: Cache-Control: public, max-age=60} | {예: 60초} |
| `GET /api/posts/{id}` | {예: ETag 기반} | — |
| `POST /api/posts` | 캐시 없음 | — |

---

## 주요 API 목록

> 이 섹션의 목적: 이 프로젝트의 핵심 API 엔드포인트를 한눈에 파악할 수 있도록 한다.

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| POST | `/api/auth/login` | 로그인, access/refresh 토큰 발급 | 불필요 |
| POST | `/api/auth/refresh` | access 토큰 재발급 | refresh token |
| GET | `/api/posts` | 게시글 목록 조회 | 불필요 |
| POST | `/api/posts` | 게시글 생성 | 필요 |
| GET | `/api/posts/{id}` | 게시글 상세 조회 | 불필요 |
| PATCH | `/api/posts/{id}` | 게시글 수정 | 필요 (작성자) |
| DELETE | `/api/posts/{id}` | 게시글 삭제 | 필요 (작성자/관리자) |
| {메서드} | `{경로}` | {설명} | {인증} |

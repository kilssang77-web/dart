# API 가이드

---

## REST 규약

### URL 설계

- 리소스 이름은 복수형 명사: `/api/v1/bids`, `/api/v1/competitors`
- 계층 구조 표현: `/api/v1/agencies/{id}/analysis`
- 동사 사용 금지 (HTTP 메서드가 역할 담당)
- 케이싱: kebab-case (`/api/v1/my-bids`, `/api/v1/srate-distribution`)

### HTTP 메서드

| 메서드 | 용도 | 멱등성 |
|--------|------|--------|
| GET | 조회 | ✅ |
| POST | 생성 / 추천 요청 | ❌ |
| PUT | 전체 수정 | ✅ |
| PATCH | 부분 수정 | ❌ |
| DELETE | 삭제 | ✅ |

### API 기본 경로

- Base URL: `/api/v1`
- Content-Type: `application/json` (요청·응답 모두)

---

## 에러 응답 포맷

**표준 에러 응답 구조 (FastAPI HTTPException):**

```json
{
  "detail": "공고를 찾을 수 없습니다."
}
```

**주요 에러 코드:**

| HTTP 상태 | 의미 |
|-----------|------|
| 400 | 입력값 검증 실패 (Pydantic ValidationError) |
| 401 | 인증 필요 (JWT 없음 또는 만료) |
| 403 | 권한 없음 (role 불충분) |
| 404 | 리소스 없음 |
| 409 | 중복 리소스 (e.g., 이미 북마크됨) |
| 422 | 요청 파라미터 타입 오류 |
| 500 | 서버 내부 오류 |

---

## 페이지네이션

**방식**: offset 기반 (page, size)

**요청 파라미터:**

| 파라미터 | 기본값 | 설명 |
|---------|--------|------|
| `page` | `1` | 페이지 번호 (1-indexed) |
| `size` | `20` | 페이지 크기 (최대: `100`) |

**응답 포맷:**

```json
{
  "items": [ {...}, {...} ],
  "total": 150,
  "page": 1,
  "size": 20
}
```

---

## 버저닝

- 전략: URL 경로 버저닝 `/api/v1`
- 버전 올림 기준: Breaking change 발생 시에만 (필드 제거, 타입 변경 등)

---

## 인증 헤더

```
Authorization: Bearer {access_token}
```

- 토큰 발급: `POST /api/v1/auth/login`
- 토큰 만료: 24시간 (기본값, `SECRET_KEY` 환경변수로 서명)
- 토큰 만료 시: `401` 응답 → 재로그인 필요 (refresh token 미지원, MVP 이후 도입 예정)

---

## 주요 API 목록

### 인증

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| POST | `/api/v1/auth/login` | 로그인, JWT 발급 | 불필요 |

### 공고 (Bids)

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| GET | `/api/v1/bids` | 공고 목록 (필터·페이지네이션) | 필요 |
| GET | `/api/v1/bids/{id}` | 공고 상세 + 낙찰 결과 | 필요 |
| POST | `/api/v1/bids` | 공고 수동 등록 | ADMIN |
| POST | `/api/v1/bids/{id}/bookmark` | 북마크 추가 | 필요 |
| DELETE | `/api/v1/bids/{id}/bookmark` | 북마크 삭제 | 필요 |

### AI 추천 (Recommend)

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| POST | `/api/v1/recommend` | 투찰률 추천 v1 | 필요 |
| POST | `/api/v1/recommend/v2` | 투찰률 추천 v2 (하이브리드 앙상블) | 필요 |
| GET | `/api/v1/recommend/yega-frequency` | 예가 빈도 분석 (Prism형) | 필요 |

### 통계 (Statistics)

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| GET | `/api/v1/stats/overview` | 대시보드 KPI 통계 | 필요 |
| GET | `/api/v1/stats/agencies` | 발주처별 통계 | 필요 |
| GET | `/api/v1/stats/industries` | 공종별 통계 | 필요 |
| GET | `/api/v1/stats/heatmap` | 발주처×공종 히트맵 | 필요 |
| GET | `/api/v1/stats/srate-distribution` | 사정율 분포 히스토그램 | 필요 |

### 발주처 (Agencies)

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| GET | `/api/v1/agencies` | 발주처 목록 | 필요 |
| GET | `/api/v1/agencies/{id}/analysis` | 발주처 심층 분석 | 필요 |

### 경쟁사 (Competitors)

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| GET | `/api/v1/competitors` | 경쟁사 목록 | 필요 |
| GET | `/api/v1/competitors/{id}` | 경쟁사 상세 | 필요 |
| GET | `/api/v1/competitors/{id}/pattern` | 경쟁사 투찰성향 (레이더 차트) | 필요 |
| GET | `/api/v1/competitors/compare` | 2개사 성향 비교 | 필요 |

### 내 입찰 (My Bids)

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| GET | `/api/v1/my-bids` | 내 투찰 이력 목록 | 필요 |
| POST | `/api/v1/my-bids` | 투찰 이력 등록 | 필요 |
| PATCH | `/api/v1/my-bids/{id}` | 투찰 결과 업데이트 | 필요 |
| DELETE | `/api/v1/my-bids/{id}` | 투찰 이력 삭제 | 필요 |
| GET | `/api/v1/my-bids/analysis` | 추천 정확도 분석 | 필요 |

### 관리자 (Admin)

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| GET | `/api/v1/admin/users` | 사용자 목록 | ADMIN |
| POST | `/api/v1/admin/users` | 사용자 생성 | ADMIN |
| GET | `/api/v1/admin/collection-logs` | 수집 로그 조회 | ADMIN |

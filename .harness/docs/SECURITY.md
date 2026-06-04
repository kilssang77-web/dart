# 보안 가이드

---

## 인증 · 인가

### 인증 방식

- 방식: JWT (access token 단일 — refresh token MVP 이후 도입 예정)
- Access Token 만료: `ACCESS_TOKEN_EXPIRE_MINUTES` 환경변수 (기본 1440분 = 24시간)
- 알고리즘: HS256
- 발급 엔드포인트: `POST /api/v1/auth/login`
- 서명 키: `.env`의 `SECRET_KEY` (256bit 이상 랜덤 문자열)

### 권한 계층

| 역할 | 설명 | 접근 범위 |
|------|------|----------|
| `viewer` | 일반 사용자 | 조회·추천·내 입찰 관리 |
| `admin` | 관리자 | 모든 리소스 + 사용자 관리 + 수집 로그 |

### FastAPI 인증 설정 요약

```python
# common/security.py — 의존성 주입 방식
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    ...

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    return current_user
```

---

## 비밀값 관리

**절대 금지 사항:**
- 소스 코드에 비밀값 하드코딩
- `git add`로 `.env` 파일 커밋 (`.gitignore`에 포함됨)
- 로그에 패스워드·토큰·개인정보 출력

**허용 관리 방식:**
- 개발: `bid-system/backend/.env` (`.env.example`만 커밋)
- 운영: 서버 환경변수 또는 Docker secret
- CI/CD: GitHub Actions Secrets

**핵심 비밀값:**

| 변수 | 설명 |
|------|------|
| `DATABASE_URL` | PostgreSQL 연결 문자열 |
| `SECRET_KEY` | JWT 서명 키 (256bit+) |

---

## 입력 검증

### Backend

- 모든 API 요청에 Pydantic `BaseModel` 적용 (FastAPI 자동 `422` 응답)
- SQL Injection: SQLAlchemy ORM 파라미터 바인딩 사용 (문자열 직접 조합 금지)
- 숫자 범위 검증: `base_amount > 0`, `bid_rate ∈ [0.5, 1.2]` 등 Service 레이어 검증
- XSS: 응답 Content-Type `application/json` 고정 (HTML 직접 반환 금지)

### Frontend

- `dangerouslySetInnerHTML` 사용 금지
- 사용자 입력 기반 URL 조작 금지
- `any` 타입 사용 금지 — Pydantic 응답 타입을 `src/types/index.ts`에 동기화

---

## OWASP Top 10 체크리스트

| OWASP 항목 | 상태 | 대응 방법 |
|-----------|------|----------|
| A01 - 접근 제어 실패 | ✅ | JWT Depends + role 체크, admin 전용 엔드포인트 분리 |
| A02 - 암호화 실패 | ✅ | bcrypt 패스워드 해싱, JWT HS256 서명 |
| A03 - 인젝션 | ✅ | SQLAlchemy ORM 파라미터 바인딩 일관 적용 |
| A04 - 안전하지 않은 설계 | ⚠️ | Service/Router 레이어 분리, ML 직접 호출 금지 (MVP 보완 필요) |
| A05 - 보안 구성 오류 | ⚠️ | CORS origins 제한 (개발: 모든 origin — 운영 전 수정 필요) |
| A06 - 취약하고 오래된 구성요소 | ⚠️ | pip-audit / npm audit 정기 실행 예정 |
| A07 - 식별 및 인증 실패 | ✅ | JWT 만료 처리, is_active 체크 |
| A08 - 소프트웨어/데이터 무결성 실패 | ⚠️ | 의존성 해시 고정 예정 |
| A09 - 보안 로깅/모니터링 실패 | ⚠️ | audit_logs 테이블 존재 — 모든 액션 기록 미완 |
| A10 - SSRF | ✅ | 외부 URL 요청 없음 (나라장터 API는 서버 → 외부, SSRF 아님) |

---

## 로깅에서 PII 마스킹

- 패스워드: 로그 출력 절대 금지 (`hashed_password`도 debug 로그 제외)
- JWT 토큰: Authorization 헤더 전체 로그 금지
- 이메일: 필요 시 `j***@a2m.co.kr` 형식으로 마스킹
- 구현: Python logging — 민감 필드 직접 출력 금지 원칙

---

## 의존성 보안 스캔

```bash
# Backend
pip-audit

# Frontend
npm audit --audit-level=high
```

- 실행 주기: MVP — PR 머지 전 수동 실행
- 임계값: high 이상 발견 시 즉시 패치

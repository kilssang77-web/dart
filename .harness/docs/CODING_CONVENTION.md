# 코딩 컨벤션

---

## 공통

- 언어: Python 3.12 (Backend), TypeScript 5 (Frontend)
- 인코딩: UTF-8
- 줄 끝: LF
- 들여쓰기: 스페이스 4칸 (Python), 스페이스 2칸 (TypeScript)
- 파일 끝 빈줄: 1개
- 주석 언어: 한국어
- TODO 형식: `# TODO(작성자): 내용 — 완료 조건`

---

## Backend — Python / FastAPI

### 네이밍

| 구분 | 규칙 | 예시 |
|------|------|------|
| 클래스 | PascalCase | `BidService`, `RecommendEngine` |
| 함수 / 변수 | snake_case | `get_bid_list`, `base_amount` |
| 상수 | UPPER_SNAKE_CASE | `MAX_PAGE_SIZE`, `MODEL_VERSION` |
| 파일 | snake_case | `services.py`, `assessment.py` |
| Pydantic 모델 | PascalCase + Request/Response | `RecommendV2Request`, `BidDetail` |

### 레이어 규칙

- Router (`api/v1/`): 입력 파싱·응답 반환만. 비즈니스 로직 금지. DB 세션 직접 사용 금지.
- Service (`services.py`): 모든 비즈니스 로직. `db.commit()` / `db.rollback()` 사용 위치.
- ML (`ml/`): 추론 로직. Service에서만 호출. Router 직접 import 금지.
- ORM (`models.py`): SQLAlchemy 모델 정의. 관계(relationship) 설정.
- Schema (`schemas.py`): Pydantic Request/Response 분리. `*Request` / `*Response` suffix.

### Service 함수 네이밍 규칙

```python
# 조회: get_ + 대상 + _by_ + 조건
def get_bid_by_id(db: Session, bid_id: int) -> BidDetail: ...

# 목록: get_ + 대상 + _list
def get_bid_list(db: Session, params: BidListParams) -> list[BidSummary]: ...

# 생성: create_ + 대상
def create_bid(db: Session, data: BidCreate) -> Bid: ...

# 수정: update_ + 대상
def update_my_bid_result(db: Session, record_id: int, data: MyBidRecordUpdate): ...
```

### 예외 처리

- FastAPI `HTTPException` 사용. `status_code` + `detail` 포함.
- 공통 에러는 `main.py`의 exception handler로 처리.
- 404: `raise HTTPException(status_code=404, detail="공고를 찾을 수 없습니다")`
- 403: `raise HTTPException(status_code=403, detail="권한이 없습니다")`

### 린터

- `ruff check .` — 린트
- `ruff format .` — 포맷

---

## Frontend — TypeScript / React

### 네이밍

| 구분 | 규칙 | 예시 |
|------|------|------|
| 컴포넌트 파일 | PascalCase + .tsx | `RecommendPage.tsx`, `WinProbGauge.tsx` |
| 훅 파일 | camelCase + use 접두 | `useAuthStore.ts` |
| API 함수 | camelCase | `getBidList`, `postRecommendV2` |
| 타입/인터페이스 | PascalCase | `BidSummary`, `RecommendV2Response` |

### 상태 관리 규칙

```typescript
// 서버 상태: TanStack Query v5 사용 (useState 직접 관리 금지)
const { data, isLoading } = useQuery({
  queryKey: ['bids', page, filters],
  queryFn: () => getBidList({ page, ...filters }),
});

// 전역 클라이언트 상태: Zustand (store/auth.ts)
const { user, token } = useAuthStore();

// 로컬 UI 상태만 useState 사용
const [isOpen, setIsOpen] = useState(false);
```

### 컴포넌트 작성 규칙

- `pages/` — 라우트 페이지 컴포넌트 (URL 1:1 대응)
- `components/ui/` — shadcn 래퍼 및 커스텀 시각화 컴포넌트
- `components/layout/` — AppLayout, 사이드바 등 레이아웃
- Props 타입은 파일 내 `interface Props`로 정의
- `axios` 직접 호출 금지 — `src/api/index.ts` 경유 필수
- `any` 타입 사용 금지 — `src/types/index.ts`에 타입 정의 필수

---

## 파일·디렉토리 네이밍

| 파일 종류 | 규칙 |
|----------|------|
| React 컴포넌트 | PascalCase + .tsx |
| 훅 | camelCase + .ts |
| API 함수 | camelCase + .ts |
| 테스트 (pytest) | `test_` + 원본파일명.py |
| DB 마이그레이션 | `V{순번}__{설명}.sql` |

---

## 포매터 · 린터

| 도구 | 대상 | 설정 파일 | 실행 명령 |
|------|------|----------|----------|
| Ruff | Backend (Python) | `pyproject.toml` | `ruff check . && ruff format .` |
| Prettier | Frontend | `.prettierrc` | `npm run format` |
| ESLint | Frontend | `eslint.config.js` | `npm run lint` |

---

## 커밋 메시지

Conventional Commits 형식: `<type>(<scope>): <subject>`

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
feat(recommend): Monte Carlo 시뮬레이션 캐싱 추가
fix(ml): 낙찰확률 0% 버그 수정 — 경쟁사 무효입찰 필터
fix(auth): JWT 만료 후 401 응답 누락 수정
```

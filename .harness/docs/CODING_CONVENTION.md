# 코딩 컨벤션

---

## 공통

- 언어: Python 3.12
- 인코딩: UTF-8
- 줄 끝: LF
- 들여쓰기: 스페이스 4칸
- 파일 끝 빈줄: 1개
- 주석 언어: 한국어 (한 줄 WHY 주석만 허용, 무엇을 하는지 설명하는 주석 금지)

---

## Backend — Python / FastAPI

### 네이밍

| 구분 | 규칙 | 예시 |
|------|------|------|
| 모듈/파일 | snake_case | `ml_client.py`, `rest_client.py` |
| 클래스 | PascalCase | `EntryRecommender`, `LGBMPredictor` |
| 함수/변수 | snake_case | `get_ml_result`, `feature_event_id` |
| 상수 | UPPER_SNAKE_CASE | `FEATURE_COLUMNS`, `ML_SERVICE_URL` |
| 비공개 함수 | `_` 접두어 | `_recover_missed_events`, `_run_retrain` |

### FastAPI 라우터 규칙

- 비즈니스 로직은 라우터에 작성하지 않는다 — 전담 모듈에서 처리
- 요청/응답은 반드시 Pydantic 스키마로 정의 (`dict` / `Any` 반환 금지)
- 모든 라우터 함수는 `async def`

```python
# 올바른 패턴
@router.get("/recommendations", response_model=list[RecommendationOut])
async def list_recommendations(min_prob: float = 0.35, db=Depends(get_db)):
    return await recommendation_service.list(min_prob=min_prob, db=db)

# 금지 — 라우터에 직접 DB 쿼리
@router.get("/recommendations")
async def list_recommendations(db=Depends(get_db)):
    rows = await db.fetch("SELECT * FROM recommendations")  # 금지
    return rows
```

### 비동기 I/O

모든 I/O 작업은 `async/await` 사용:

```python
# DB: asyncpg 파라미터 바인딩
rows = await conn.fetch(
    "SELECT * FROM recommendations WHERE success_prob >= $1",
    min_prob
)

# HTTP: httpx.AsyncClient
async with httpx.AsyncClient() as client:
    resp = await client.post(url, json=payload, timeout=5.0)

# Kafka: aiokafka
await producer.send_and_wait(topic, value=msg_bytes)
```

### SQL 작성 규칙

- 파라미터 바인딩 필수 (`$1`, `$2`, …) — 문자열 포맷팅으로 SQL 조합 절대 금지
- SELECT 대상 컬럼 명시 (SELECT * 금지, 인덱스 스캔만 예외)

```python
# 올바른 패턴
await conn.fetch(
    "SELECT id, code, action, success_prob FROM recommendations "
    "WHERE success_prob >= $1 ORDER BY created_at DESC LIMIT $2",
    min_prob, limit
)

# 금지 — SQL 인젝션 위험
query = f"SELECT * FROM recommendations WHERE code = '{code}'"
```

### 예외 처리

- FastAPI 라우터: `HTTPException` 사용
- 서비스 레이어: 예외 전파 또는 `logging.exception()` 후 None/기본값 반환
- 외부 API 오류: `try/except` + fallback 로직

```python
async def get_ml_result(features: dict) -> float:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(ML_SERVICE_URL + "/predict", json=features, timeout=3.0)
            resp.raise_for_status()
            return resp.json()["success_prob"]
    except Exception:
        logger.warning("ML HTTP 실패 — local fallback")
        return _local_predict(features)
```

### 환경변수 관리

```python
import os

ML_SERVICE_URL = os.getenv("ML_SERVICE_URL", "")
REC_MIN_PROB = float(os.getenv("REC_MIN_PROB", "0.35"))
```

하드코딩 금지. `.env.example`에 변수 정의 필수.

### 타입힌트

모든 함수 시그니처에 타입힌트 필수. `Any` 사용 금지.

```python
async def emit(rec: dict[str, float], event_id: int | None = None) -> None: ...
def _f(val: object, default: float = 0.0) -> float: ...
```

### 로깅

```python
import logging
logger = logging.getLogger(__name__)

logger.info("Recovery: completed %d/%d events", ok, total)
logger.warning("pattern_vector 생성 실패: %s", err)
# 금지: API 키·토큰·패스워드 로그 출력
```

---

## 파일·디렉토리 네이밍

| 파일 종류 | 규칙 |
|----------|------|
| Python 모듈 | snake_case + .py |
| 테스트 | `test_` + 모듈명 + .py |
| SQL 마이그레이션 | `V{순번}__{설명}.sql` (TimescaleDB hypertable 순서 보장) |
| 환경변수 파일 | `.env` (git 제외), `.env.example` (git 추적) |

---

## 포매터 · 린터

| 도구 | 대상 | 설정 | 실행 |
|------|------|------|------|
| black | 전체 Python | `pyproject.toml` | `black .` |
| isort | import 정렬 | `pyproject.toml` | `isort .` |
| mypy | 타입 검사 (production) | `mypy.ini` | `mypy services/` |

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
feat(detector): 모닝스타 3봉 패턴 Kafka 파이프라인 연결
fix(recommender): Recovery 중복 처리 버그 수정 (feature_event_id 기반)
perf(ml): bars pre-indexing으로 백테스트 O(n²) → O(n) 최적화
```

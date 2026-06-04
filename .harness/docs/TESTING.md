# 테스트 전략

---

## 테스트 피라미드

```
         /\
        /E2E\         MVP 이후 도입 예정
       /──────\
      /통합 테스트\    API 엔드포인트 + DB
     /────────────\
    /  단위 테스트  \  Service·ML 함수
   /────────────────\
```

| 레이어 | 목표 비율 | 속도 | 도구 |
|--------|---------|------|------|
| 단위 테스트 | 70% | 빠름 (밀리초) | pytest + pytest-mock |
| 통합 테스트 | 25% | 보통 (초) | pytest + httpx + TestClient |
| E2E 테스트 | 5% | 느림 (분) | Playwright (MVP 이후) |

---

## Backend — 단위 테스트

**도구**: pytest + pytest-mock + pytest-cov

**대상**: `services.py`의 비즈니스 로직, `ml/` 추론 함수 (Router는 단위 테스트 대상 아님)

```python
# 예시 패턴 — services.py 단위 테스트
import pytest
from unittest.mock import MagicMock
from app.services import get_bid_by_id
from app.schemas import BidDetail

def test_get_bid_by_id_not_found(db_session):
    db_session.query.return_value.filter.return_value.first.return_value = None
    with pytest.raises(HTTPException) as exc_info:
        get_bid_by_id(db_session, bid_id=999)
    assert exc_info.value.status_code == 404
```

**실행:**
```bash
# bid-system/backend/
pytest tests/unit/

# 커버리지 포함
pytest --cov=app/services --cov=app/ml --cov-report=term-missing
```

---

## Backend — 통합 테스트

**도구**: pytest + FastAPI `TestClient` + 테스트 DB

**대상**: API 엔드포인트의 요청→응답 전체 플로우

```python
# 예시 패턴 — API 통합 테스트
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_login_success():
    response = client.post("/api/v1/auth/login", json={
        "email": "test@a2m.co.kr",
        "password": "testpass"
    })
    assert response.status_code == 200
    assert "access_token" in response.json()

def test_get_bids_unauthorized():
    response = client.get("/api/v1/bids")
    assert response.status_code == 401
```

**DB 전략**: 테스트용 SQLite 인메모리 (또는 별도 PostgreSQL 테스트 DB)

---

## Frontend — 컴포넌트 테스트

**도구**: Vitest + React Testing Library

**원칙**: 구현 세부사항이 아닌 사용자 행동을 테스트한다.

```typescript
// 예시 패턴 — WinProbGauge 컴포넌트 테스트
import { render, screen } from '@testing-library/react';
import { WinProbGauge } from '@/components/ui/WinProbGauge';

test('낙찰확률 75%가 표시된다', () => {
  render(<WinProbGauge probability={0.75} />);
  expect(screen.getByText('75%')).toBeInTheDocument();
});
```

**실행:**
```bash
# bid-system/frontend/
npm test

# 커버리지 포함
npm run coverage
```

---

## Frontend — E2E 테스트

**도구**: Playwright (MVP 이후 도입)

**대상 시나리오** (우선순위 상위 3개):
1. 로그인 → 대시보드 KPI 확인
2. AI 추천 조건 입력 → 4전략 결과 표시
3. 내 입찰 등록 → 결과 업데이트

---

## 픽스처 · 시드 데이터

- Backend: `conftest.py`의 `@pytest.fixture`로 테스트 DB 세션 및 샘플 데이터 관리
- Frontend: MSW(Mock Service Worker)로 API mocking (MVP 도입 예정)
- E2E: Playwright `beforeEach`에서 API 직접 호출로 데이터 시드

---

## 커버리지 목표

| 단계 | 목표 | 측정 범위 |
|------|------|----------|
| prototype | 필수 없음 | — |
| mvp | 라인 커버리지 60% 이상 | `app/services.py`, `app/ml/` |
| production | 라인 커버리지 80% 이상 | `app/services.py`, `app/ml/`, `app/api/` |

```bash
# Backend 커버리지 리포트
pytest --cov=app --cov-report=html
# → htmlcov/index.html 확인

# Frontend 커버리지 리포트
npm run coverage
```

---

## ML 엔진 테스트 특이사항

- `ml/assessment.py`: 사정율 예측 결과가 `[0.85, 1.05]` 범위 내인지 검증
- `ml/simulation.py`: 시뮬레이션 n_sim=1000 수렴 여부 단위 테스트
- `ml/yega.py`: 15개 후보 조합 합계가 1.0이 되는지 검증 (확률 합산)
- ML 테스트는 DB 불필요 — 순수 함수 단위 테스트 가능

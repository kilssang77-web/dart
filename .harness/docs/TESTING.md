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

## Collector 단위 테스트

| 파일 | 테스트 수 | 커버 대상 |
|------|---------|---------|
| `tests/unit/collector/test_client.py` | 12 | NarajangterClient 페이지네이션·재시도·파싱 |
| `tests/unit/collector/test_service.py` | 10 | collect_notices/results upsert 중복방지 |
| `tests/unit/collector/test_scheduler.py` | 9 | APScheduler 잡 등록·실행·에러 처리 |

**패턴**: collector 테스트는 `requests` 및 `SessionLocal`을 mock으로 교체. 실제 API 호출 없이 단위 검증.

```python
# 예시 — NarajangterClient 재시도 테스트
from unittest.mock import patch, MagicMock
from app.collector.client import NarajangterClient

def test_retry_on_timeout():
    client = NarajangterClient(api_key="test")
    with patch("requests.get", side_effect=[Timeout(), MagicMock(status_code=200, json=lambda: {})]):
        result = client.get_notices("notice_cnstwk", page=1)
    assert result is not None
```

---

## ML 엔진 테스트 특이사항

- `ml/assessment.py`: 사정율 예측 결과가 `[0.85, 1.05]` 범위 내인지 검증
- `ml/simulation.py`: 시뮬레이션 n_sim=1000 수렴 여부 단위 테스트
- `ml/a_value.py`: calc_bid_range P10~P90 범위·FLOOR_RATE_TABLE 업종별 매핑 정확도 검증
- `ml/prism.py`: scan_prism_zones 71구간 생성·floor 필터·TOP10 순서 검증
- `ml/yega.py`: 15개 후보 조합 합계가 1.0이 되는지 검증, get_agency_yega_pattern 발주처 없을 때 폴백 검증
- `ml/rank_model.py`: DB fallback (버킷→전체) 경로 및 50건 미만 시 None 반환 검증
- `ml/personal.py`: 이력 없음 empty_result, 지수감쇠 가중치, MAX_CORRECTION(0.008) 클리핑 검증
- ML 테스트는 DB 불필요 — 순수 함수 단위 테스트 가능 (rank_model 제외: DB 조회 포함)

---

## mvp-enhance2 단위 테스트 (2026-06-05)

| 파일 | 테스트 수 | 커버 대상 |
|------|---------|---------|
| `tests/unit/test_a_value.py` | 18 | calc_bid_range P10~P90, FLOOR_RATE_TABLE 업종별 매핑 |
| `tests/unit/test_srate_trend.py` | 7 | SrateTrendService 폴백·3개월 필터·트렌드 방향(↑↓→) |
| `tests/unit/test_prism.py` | 10 | scan_prism_zones 71구간·floor 필터·TOP10 정렬 |
| `tests/unit/test_competitor_zones.py` | 5 | CompetitorZoneService 0.005 버킷·peak_zone 산출 |
| `tests/unit/test_top_recommended.py` | 4 | OpportunityScoreService 7일 이내·활성공종 필터·점수 정렬 |
| `tests/unit/test_gap_distribution.py` | 6 | DefeatAnalysisService 빈 이력·5건 이상·편향 방향 분류 |
| `tests/unit/test_yega_pattern.py` | 6 | get_agency_yega_pattern C(15,4) 역산·발주처 없을 때 폴백 |
| `tests/unit/test_joint_qual_service.py` | 5 | JointQualService 매칭 없음·1개 이상·적격 기준 계산 |
---

## DB 연동 테스트 주의사항

### PostgreSQL TIMESTAMPTZ vs Python datetime

PostgreSQL `TIMESTAMPTZ` 컬럼은 timezone-aware datetime을 반환한다.
Python `datetime.now()`는 naive datetime이므로 SQLAlchemy 비교 시 오류 발생:

```
TypeError: can't compare offset-naive and offset-aware datetimes
```

**규칙**: `TIMESTAMPTZ` 컬럼(예: `bid_open_date`, `created_at`, `notice_date`)과 비교할 때는 반드시 `datetime.now(timezone.utc)` 사용.

```python
# 잘못된 코드 — runtime TypeError 발생
from datetime import datetime, timedelta
cutoff = datetime.now() - timedelta(days=7)
db.query(Bid).filter(Bid.bid_open_date >= cutoff)  # TypeError!

# 올바른 코드
from datetime import datetime, timedelta, timezone
cutoff = datetime.now(timezone.utc) - timedelta(days=7)
db.query(Bid).filter(Bid.bid_open_date >= cutoff)   # OK
```

> 영향 범위: `services.py`에서 DB 컬럼과 datetime을 비교하는 모든 쿼리.
> 단위 테스트에서 DB 없이 mock 사용 시에도 datetime 인자는 timezone-aware로 전달할 것.

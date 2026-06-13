"""
Unit / integration tests for the API service.
Run:   pytest services/api/tests/ -v
"""
import pytest
from unittest.mock import AsyncMock, patch


# ── Health endpoint ──────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_health_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"


# ── /stocks/search ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_search_returns_list(client, mock_pool):
    mock_pool.fetch = AsyncMock(return_value=[
        {"code": "005930", "name": "삼성전자", "market": "KOSPI"},
    ])
    resp = await client.get("/stocks/search?q=삼성")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["code"] == "005930"


@pytest.mark.asyncio
async def test_search_empty_query_returns_empty(client, mock_pool):
    mock_pool.fetch = AsyncMock(return_value=[])
    resp = await client.get("/stocks/search?q=")
    assert resp.status_code == 200
    assert resp.json() == []


# ── /features ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_features_list(client, mock_pool):
    mock_pool.fetch = AsyncMock(return_value=[])
    resp = await client.get("/features?limit=10")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── /recommendations ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_recommendations_list(client, mock_pool):
    mock_pool.fetch = AsyncMock(return_value=[])
    resp = await client.get("/recommendations?limit=10")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── /metrics (Prometheus) ────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_metrics_endpoint_exists(client):
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "fstock_" in resp.text or "http_requests" in resp.text


# ── /recommendations hours 파라미터 (서비스 레이어 직접 테스트) ────────────────
@pytest.mark.asyncio
async def test_recommendations_where_default_hours():
    """hours=72 기본값 시 WHERE 절 첫 파라미터가 72인지 확인."""
    from unittest.mock import MagicMock
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from services.recommendation_service import RecommendationService

    svc = RecommendationService(db=MagicMock(), redis=MagicMock())
    _, params = svc._build_where(action=None, market=None, code=None, min_prob=0.20, hours=72)
    assert params[0] == 72


@pytest.mark.asyncio
async def test_recommendations_where_hours_48():
    """hours=48 전달 시 WHERE 절 첫 파라미터가 48인지 확인."""
    from unittest.mock import MagicMock
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from services.recommendation_service import RecommendationService

    svc = RecommendationService(db=MagicMock(), redis=MagicMock())
    _, params = svc._build_where(action=None, market=None, code=None, min_prob=0.20, hours=48)
    assert params[0] == 48


# ── RecommendationService._build_where 단위 테스트 ──────────────────────────
@pytest.mark.asyncio
async def test_build_where_uses_hours():
    """_build_where가 hours 파라미터를 첫 번째 바인딩 변수로 사용해야 함."""
    from unittest.mock import MagicMock
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from services.recommendation_service import RecommendationService

    svc = RecommendationService(db=MagicMock(), redis=MagicMock())
    where, params = svc._build_where(
        action=None, market=None, code=None, min_prob=0.3, hours=48
    )
    # 첫 번째 파라미터가 hours=48
    assert params[0] == 48, f"hours should be first param, got {params}"
    # 두 번째 파라미터가 min_prob=0.3
    assert params[1] == 0.3, f"min_prob should be second param, got {params}"
    # WHERE 절에 시간 필터가 포함되어야 함
    assert any("hour" in w.lower() for w in where)


@pytest.mark.asyncio
async def test_build_where_with_action():
    """action 파라미터가 WHERE 절에 올바르게 추가되는지 확인."""
    from unittest.mock import MagicMock
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from services.recommendation_service import RecommendationService

    svc = RecommendationService(db=MagicMock(), redis=MagicMock())
    where, params = svc._build_where(
        action="BUY", market=None, code=None, min_prob=0.5, hours=72
    )
    assert "BUY" in params
    assert any("action" in w for w in where)


# ── code_signals SignalItem 타입 확인 (서비스 레이어 직접 테스트) ────────────────
@pytest.mark.asyncio
async def test_code_signals_returns_code_signals_response():
    """code_signals 서비스가 CodeSignalsResponse를 반환해야 함 (SignalItem 타입 사용)."""
    from unittest.mock import MagicMock, AsyncMock, patch
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from services.recommendation_service import RecommendationService
    from schemas.responses import CodeSignalsResponse

    mock_pool = MagicMock()
    mock_pool.fetch = AsyncMock(return_value=[])
    mock_redis = AsyncMock()
    mock_redis.pipeline = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=AsyncMock(execute=AsyncMock(return_value=[]))),
        __aexit__=AsyncMock(),
    ))

    svc = RecommendationService(db=mock_pool, redis=mock_redis)

    with patch("services.recommendation_service.enrich_live_prices", AsyncMock()):
        result = await svc.code_signals("005930", hours=48)

    assert isinstance(result, CodeSignalsResponse)
    assert result.total_count == 0
    assert result.signals == []


# ── /features hours 기본값 72 (라우터 기본값 직접 확인) ────────────────────────
@pytest.mark.asyncio
async def test_features_router_default_hours():
    """features 라우터의 hours 기본값이 72인지 확인 (라우터 소스 파싱)."""
    import ast, os
    router_path = os.path.join(os.path.dirname(__file__), "..", "routers", "features.py")
    with open(router_path) as f:
        source = f.read()
    # default=72 가 소스에 있어야 함
    assert "default=72" in source, "features router hours default should be 72"


# ── Integration: DB round-trip ───────────────────────────────────────────────
@pytest.mark.integration
@pytest.mark.asyncio
async def test_daily_bars_db(real_pool):
    rows = await real_pool.fetch(
        "SELECT code, date, close FROM daily_bars ORDER BY date DESC LIMIT 5"
    )
    assert len(rows) > 0, "daily_bars table should have data"

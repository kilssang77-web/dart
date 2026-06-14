"""
Integration test fixtures.
Requires a live PostgreSQL + Redis (set POSTGRES_DSN and REDIS_URL env vars,
or spin up docker-compose infra first).
"""
import os
import pytest
import asyncpg
import redis.asyncio as redis_lib
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock

# ── Optional: skip all integration tests when infra not available ────────────
POSTGRES_DSN = os.getenv("POSTGRES_DSN", "")
REDIS_URL    = os.getenv("REDIS_URL", "redis://localhost:6379/0")
SKIP_INFRA   = not POSTGRES_DSN


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: requires live DB/Redis")


# ── App fixture with mocked dependencies ────────────────────────────────────
@pytest.fixture
def mock_pool():
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()))
    pool.fetch = AsyncMock(return_value=[])
    pool.fetchval = AsyncMock(return_value=None)
    pool.execute = AsyncMock()
    return pool


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock()
    r.delete = AsyncMock()
    return r


@pytest.fixture
async def client(mock_pool, mock_redis):
    """HTTP test client with mocked DB/Redis — no infra needed."""
    import main as app_module

    app_module._db_pool = mock_pool
    app_module._redis   = mock_redis

    async with AsyncClient(
        transport=ASGITransport(app=app_module.app),
        base_url="http://test",
    ) as ac:
        yield ac


# ── Integration fixtures (skipped when POSTGRES_DSN not set) ────────────────
@pytest.fixture(scope="session")
async def real_pool():
    if SKIP_INFRA:
        pytest.skip("POSTGRES_DSN not configured")
    pool = await asyncpg.create_pool(
        dsn=POSTGRES_DSN.replace("+asyncpg", ""),
        min_size=1, max_size=3,
    )
    yield pool
    await pool.close()


@pytest.fixture(scope="session")
async def real_redis():
    if SKIP_INFRA:
        pytest.skip("POSTGRES_DSN not configured")
    r = redis_lib.from_url(REDIS_URL)
    yield r
    await r.aclose()

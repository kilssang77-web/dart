import asyncio
import logging
import os
import httpx
import redis.asyncio as redis_lib
from dataclasses import dataclass, field
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

_KIS_BASE_URL = os.getenv("KIS_BASE_URL", "https://openapi.koreainvestment.com:9443")
_KIS_WS_URL   = os.getenv("KIS_WS_URL",   "ws://ops.koreainvestment.com:21000")


@dataclass
class KISConfig:
    app_key: str
    app_secret: str
    account_no: str
    account_type: str = "01"
    base_url: str = field(default_factory=lambda: _KIS_BASE_URL)
    ws_url: str   = field(default_factory=lambda: _KIS_WS_URL)


class KISAuthManager:
    TOKEN_KEY    = "kis:access_token"
    APPROVAL_KEY = "kis:ws_approval_key"

    def __init__(self, config: KISConfig, redis_client: redis_lib.Redis):
        self.config = config
        self.redis = redis_client
        self._client = httpx.AsyncClient(timeout=30)
        self._lock = asyncio.Lock()

    async def get_access_token(self) -> str:
        cached = await self.redis.get(self.TOKEN_KEY)
        if cached:
            return cached.decode()
        async with self._lock:
            cached = await self.redis.get(self.TOKEN_KEY)
            if cached:
                return cached.decode()
            data = await self._issue_token()
            ttl = data.get("expires_in", 86400) - 1800
            await self.redis.setex(self.TOKEN_KEY, max(ttl, 300), data["access_token"])
            return data["access_token"]

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    )
    async def _issue_token(self) -> dict:
        resp = await self._client.post(
            f"{self.config.base_url}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": self.config.app_key,
                "appsecret": self.config.app_secret,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def get_ws_approval_key(self) -> str:
        cached = await self.redis.get(self.APPROVAL_KEY)
        if cached:
            return cached.decode()
        resp = await self._client.post(
            f"{self.config.base_url}/oauth2/Approval",
            json={
                "grant_type": "client_credentials",
                "appkey": self.config.app_key,
                "secretkey": self.config.app_secret,
            },
        )
        resp.raise_for_status()
        key = resp.json()["approval_key"]
        await self.redis.setex(self.APPROVAL_KEY, 86400, key)
        return key

    def get_headers(self, token: str, tr_id: str) -> dict:
        return {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self.config.app_key,
            "appsecret": self.config.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }

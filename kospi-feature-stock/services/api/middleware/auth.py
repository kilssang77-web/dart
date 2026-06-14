"""
X-API-Key 헤더 기반 API 인증 미들웨어.

API_KEY 환경변수가 설정되지 않으면 인증을 건너뛴다(개발 모드).
설정된 경우 /api/v1/** 경로에만 적용하고 /health, /metrics, /docs, /openapi.json은 제외한다.
"""

import os
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

_API_KEY = os.environ.get("API_KEY", "")

_SKIP_PREFIXES = ("/health", "/metrics", "/docs", "/openapi.json", "/redoc")


class APIKeyMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):
        if not _API_KEY:
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(p) for p in _SKIP_PREFIXES):
            return await call_next(request)

        if not path.startswith("/api/"):
            return await call_next(request)

        key = (
            request.headers.get("X-API-Key")
            or request.headers.get("x-api-key")
            or request.query_params.get("api_key")
        )
        if key != _API_KEY:
            logger.warning(f"Unauthorized request: {request.method} {path} from {request.client}")
            return JSONResponse(
                {"detail": "Invalid or missing API key"},
                status_code=401,
                headers={"WWW-Authenticate": 'ApiKey realm="Quant Eye API"'},
            )

        return await call_next(request)

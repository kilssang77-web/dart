"""
인증 미들웨어 — JWT Bearer 토큰 + X-API-Key 지원.

우선순위:
  1. Authorization: Bearer <JWT>
  2. X-API-Key 헤더 또는 ?api_key= (환경변수 API_KEY 설정 시)
  3. JWT_SECRET_KEY, API_KEY 모두 미설정 → 개발 모드(인증 없음)
"""

import os
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

_API_KEY    = os.environ.get("API_KEY", "")
_JWT_ACTIVE = bool(os.environ.get("JWT_SECRET_KEY", ""))

_SKIP_PREFIXES  = ("/health", "/metrics", "/docs", "/openapi.json", "/redoc", "/ws/")
_PUBLIC_PATHS   = ("/api/v1/auth/login",)


class APIKeyMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 항상 통과: 헬스, 메트릭, 문서, WebSocket
        if any(path.startswith(p) for p in _SKIP_PREFIXES):
            return await call_next(request)

        # API 경로가 아니면 통과 (정적 파일, SPA fallback 등)
        if not path.startswith("/api/"):
            return await call_next(request)

        # 공개 API (로그인 엔드포인트)
        if any(path.startswith(p) for p in _PUBLIC_PATHS):
            return await call_next(request)

        # 인증이 모두 비설정이면 개발 모드 — 전통과
        if not _JWT_ACTIVE and not _API_KEY:
            return await call_next(request)

        # ── JWT Bearer 확인 ──────────────────────────────────
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            from auth_utils import decode_token
            payload = decode_token(auth_header[7:])
            if payload:
                return await call_next(request)
            logger.warning(f"만료/무효 토큰: {request.method} {path}")
            return JSONResponse(
                {"detail": "토큰이 만료되었거나 유효하지 않습니다. 다시 로그인해주세요."},
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer realm="Quant Eye"'},
            )

        # ── X-API-Key 호환 ────────────────────────────────────
        if _API_KEY:
            key = (
                request.headers.get("X-API-Key")
                or request.headers.get("x-api-key")
                or request.query_params.get("api_key")
            )
            if key == _API_KEY:
                return await call_next(request)

        # ── 인증 실패 ─────────────────────────────────────────
        logger.warning(f"인증 실패: {request.method} {path} from {request.client}")
        return JSONResponse(
            {"detail": "로그인이 필요합니다"},
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer realm="Quant Eye"'},
        )

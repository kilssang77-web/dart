"""JWT + 비밀번호 해시 유틸리티."""
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

SECRET_KEY   = os.environ.get("JWT_SECRET_KEY", "dev-insecure-secret-change-me")
ALGORITHM    = "HS256"
EXPIRE_HOURS = int(os.environ.get("JWT_EXPIRE_HOURS", "8"))

# ── JWT ──────────────────────────────────────────────────────────
try:
    from jose import jwt, JWTError
    _JOSE_OK = True
except ImportError:
    _JOSE_OK = False
    logger.warning("python-jose 미설치 — JWT 인증 불가")

# ── 비밀번호 해시: bcrypt 직접 사용 (passlib 호환성 문제 우회) ────
try:
    import bcrypt as _bcrypt
    _BCRYPT_OK = True
except ImportError:
    _BCRYPT_OK = False
    logger.warning("bcrypt 미설치 — SHA-256 폴백 사용")


def hash_password(plain: str) -> str:
    if _BCRYPT_OK:
        salt = _bcrypt.gensalt()
        return _bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")
    import hashlib
    return hashlib.sha256(plain.encode()).hexdigest()


def verify_password(plain: str, hashed: str) -> bool:
    if _BCRYPT_OK:
        try:
            return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
        except Exception:
            return False
    import hashlib
    return hashlib.sha256(plain.encode()).hexdigest() == hashed


def create_access_token(data: dict) -> str:
    if not _JOSE_OK:
        raise RuntimeError("python-jose 미설치")
    payload = {
        **data,
        "exp": datetime.now(timezone.utc) + timedelta(hours=EXPIRE_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    if not _JOSE_OK:
        return None
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None

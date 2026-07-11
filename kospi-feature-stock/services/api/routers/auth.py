"""인증 라우터 — 로그인 / 내 정보 / 로그아웃."""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from deps import get_db
from auth_utils import verify_password, create_access_token, decode_token

logger = logging.getLogger(__name__)
router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str

    @field_validator("username", "password")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("빈 값은 허용되지 않습니다")
        return v.strip()


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    display_name: str


class UserInfo(BaseModel):
    username: str
    display_name: str


def _extract_token(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


@router.post("/auth/login", response_model=LoginResponse, summary="로그인")
async def login(body: LoginRequest, db=Depends(get_db)):
    row = await db.fetchrow(
        "SELECT * FROM users WHERE username=$1 AND is_active=TRUE",
        body.username,
    )
    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다")

    display = row["display_name"] or row["username"]
    token   = create_access_token({"sub": row["username"], "display_name": display})

    try:
        await db.execute(
            "UPDATE users SET last_login=NOW() WHERE username=$1", row["username"]
        )
    except Exception:
        pass

    logger.info(f"로그인 성공: {body.username}")
    return LoginResponse(access_token=token, display_name=display)


@router.get("/auth/me", response_model=UserInfo, summary="내 정보")
async def me(request: Request):
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="인증 토큰이 없습니다")
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다")
    return UserInfo(username=payload["sub"], display_name=payload.get("display_name", payload["sub"]))


@router.post("/auth/logout", summary="로그아웃")
async def logout():
    # 클라이언트가 토큰을 삭제하므로 서버 측 처리 불필요 (stateless JWT)
    return {"message": "로그아웃 되었습니다"}

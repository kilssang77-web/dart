"""인증 라우터 — 로그인 / 내 정보 / 로그아웃 / 사용자 관리."""
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from deps import get_db
from auth_utils import verify_password, hash_password, create_access_token, decode_token

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


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────
def _require_auth(request: Request) -> dict:
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="인증 토큰이 없습니다")
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다")
    return payload


def _row_to_user(row) -> dict:
    return {
        "username":     row["username"],
        "display_name": row["display_name"],
        "is_active":    row["is_active"],
        "created_at":   row["created_at"].isoformat() if row["created_at"] else "",
        "last_login":   row["last_login"].isoformat() if row["last_login"] else None,
    }


# ── 스키마 ────────────────────────────────────────────────────────────────────
class UserOut(BaseModel):
    username:     str
    display_name: Optional[str]
    is_active:    bool
    created_at:   str
    last_login:   Optional[str]


class UserCreateBody(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("아이디는 필수입니다")
        if len(v) < 3:
            raise ValueError("아이디는 3자 이상이어야 합니다")
        return v

    @field_validator("password")
    @classmethod
    def password_valid(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("비밀번호는 8자 이상이어야 합니다")
        return v


class UserUpdateBody(BaseModel):
    display_name: Optional[str] = None
    is_active:    Optional[bool] = None
    new_password: Optional[str] = None


# ── 사용자 목록 ───────────────────────────────────────────────────────────────
@router.get("/auth/users", response_model=List[UserOut], summary="사용자 목록")
async def list_users(request: Request, db=Depends(get_db)):
    _require_auth(request)
    rows = await db.fetch("SELECT * FROM users ORDER BY created_at ASC")
    return [_row_to_user(r) for r in rows]


# ── 사용자 추가 ───────────────────────────────────────────────────────────────
@router.post("/auth/users", response_model=UserOut, status_code=201, summary="사용자 추가")
async def create_user(body: UserCreateBody, request: Request, db=Depends(get_db)):
    _require_auth(request)
    existing = await db.fetchrow("SELECT 1 FROM users WHERE username=$1", body.username)
    if existing:
        raise HTTPException(status_code=400, detail="이미 존재하는 아이디입니다")
    pw_hash = hash_password(body.password)
    row = await db.fetchrow(
        "INSERT INTO users (username, password_hash, display_name) VALUES ($1, $2, $3) RETURNING *",
        body.username, pw_hash, body.display_name or body.username,
    )
    logger.info(f"사용자 추가: {body.username}")
    return _row_to_user(row)


# ── 사용자 수정 ───────────────────────────────────────────────────────────────
@router.put("/auth/users/{username}", response_model=UserOut, summary="사용자 수정")
async def update_user(username: str, body: UserUpdateBody, request: Request, db=Depends(get_db)):
    _require_auth(request)
    row = await db.fetchrow("SELECT * FROM users WHERE username=$1", username)
    if not row:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    sets, params = [], []
    idx = 1
    if body.display_name is not None:
        sets.append(f"display_name=${idx}"); params.append(body.display_name); idx += 1
    if body.is_active is not None:
        sets.append(f"is_active=${idx}"); params.append(body.is_active); idx += 1
    if body.new_password is not None:
        if len(body.new_password) < 8:
            raise HTTPException(status_code=400, detail="비밀번호는 8자 이상이어야 합니다")
        sets.append(f"password_hash=${idx}"); params.append(hash_password(body.new_password)); idx += 1

    if not sets:
        return _row_to_user(row)

    params.append(username)
    row = await db.fetchrow(
        f"UPDATE users SET {', '.join(sets)} WHERE username=${idx} RETURNING *",
        *params,
    )
    logger.info(f"사용자 수정: {username}")
    return _row_to_user(row)


# ── 사용자 삭제 ───────────────────────────────────────────────────────────────
@router.delete("/auth/users/{username}", status_code=204, summary="사용자 삭제")
async def delete_user(username: str, request: Request, db=Depends(get_db)):
    payload = _require_auth(request)
    if payload["sub"] == username:
        raise HTTPException(status_code=400, detail="자신의 계정은 삭제할 수 없습니다")
    result = await db.execute("DELETE FROM users WHERE username=$1", username)
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    logger.info(f"사용자 삭제: {username}")


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_length(cls, v: str) -> str:
        if len(v.strip()) < 8:
            raise ValueError("비밀번호는 8자 이상이어야 합니다")
        return v


@router.post("/auth/change-password", summary="비밀번호 변경")
async def change_password(body: ChangePasswordRequest, request: Request, db=Depends(get_db)):
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="인증 토큰이 없습니다")
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다")

    username = payload["sub"]
    row = await db.fetchrow("SELECT * FROM users WHERE username=$1 AND is_active=TRUE", username)
    if not row:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    if not verify_password(body.current_password, row["password_hash"]):
        raise HTTPException(status_code=400, detail="현재 비밀번호가 올바르지 않습니다")

    new_hash = hash_password(body.new_password)
    await db.execute("UPDATE users SET password_hash=$1 WHERE username=$2", new_hash, username)
    logger.info(f"비밀번호 변경: {username}")
    return {"message": "비밀번호가 변경되었습니다"}

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime

from ...database import get_db
from ...models import User
from ...schemas import LoginRequest, TokenResponse, UserCreate, UserOut
from ...common.security import (
    verify_password, hash_password, create_token,
    get_current_user, require_role
)

router = APIRouter(prefix="/auth", tags=["인증"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email, User.is_active == True).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="이메일 또는 비밀번호가 올바르지 않습니다.")
    user.last_login = datetime.utcnow()
    db.commit()
    token = create_token(user.id, user.role)
    return TokenResponse(access_token=token, user_name=user.name or user.email, role=user.role)


@router.get("/me", response_model=UserOut)
def me(current: User = Depends(get_current_user)):
    return current


@router.post("/refresh", response_model=TokenResponse)
def refresh(current: User = Depends(get_current_user)):
    """유효한 토큰으로 새 토큰 발급 — 만료 전 자동 갱신용."""
    token = create_token(current.id, current.role)
    return TokenResponse(access_token=token, user_name=current.name or current.email, role=current.role)


@router.post("/users", response_model=UserOut)
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail="이미 사용 중인 이메일입니다.")
    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        name=body.name,
        role=body.role,
        department=body.department,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/users", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    return db.query(User).all()

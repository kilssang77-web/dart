from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ...database import get_db
from ...models import WatchKeyword
from ...schemas import WatchKeywordCreate, WatchKeywordUpdate, WatchKeywordOut
from ...common.security import get_current_user
from ...models import User

router = APIRouter(prefix="/keywords", tags=["keywords"])


@router.get("", response_model=List[WatchKeywordOut])
def list_keywords(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(WatchKeyword).order_by(WatchKeyword.created_at.desc()).all()


@router.post("", response_model=WatchKeywordOut)
def create_keyword(body: WatchKeywordCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    kw = WatchKeyword(**body.model_dump(), user_id=user.id)
    db.add(kw)
    db.commit()
    db.refresh(kw)
    return kw


@router.put("/{kw_id}", response_model=WatchKeywordOut)
def update_keyword(kw_id: int, body: WatchKeywordUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    kw = db.query(WatchKeyword).filter(WatchKeyword.id == kw_id).first()
    if not kw:
        raise HTTPException(status_code=404, detail="키워드를 찾을 수 없습니다.")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(kw, k, v)
    db.commit()
    db.refresh(kw)
    return kw


@router.delete("/{kw_id}")
def delete_keyword(kw_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    kw = db.query(WatchKeyword).filter(WatchKeyword.id == kw_id).first()
    if not kw:
        raise HTTPException(status_code=404, detail="키워드를 찾을 수 없습니다.")
    db.delete(kw)
    db.commit()
    return {"success": True}
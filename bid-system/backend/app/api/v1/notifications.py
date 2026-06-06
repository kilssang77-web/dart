from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import User
from ...schemas import NotificationListResponse, NotificationOut
from ...services import NotificationService
from ...common.security import get_current_user

router = APIRouter(prefix="/notifications", tags=["알림"])


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    svc = NotificationService(db)
    return NotificationListResponse(
        items=svc.list_for_user(current.id, unread_only=unread_only, limit=limit),
        unread_count=svc.unread_count(current.id),
    )


@router.get("/unread-count")
def unread_count(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return {"count": NotificationService(db).unread_count(current.id)}


@router.post("/{notification_id}/read", status_code=204)
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    NotificationService(db).mark_read(notification_id, current.id)


@router.post("/read-all", status_code=204)
def mark_all_read(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    NotificationService(db).mark_all_read(current.id)

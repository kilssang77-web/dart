"""
북마크 서비스 (BookmarkService)
"""
import logging
from sqlalchemy.orm import Session

from ..models import BidBookmark

logger = logging.getLogger(__name__)


class BookmarkService:
    def __init__(self, db: Session):
        self.db = db

    def add(self, bid_id: int, user_id: int, note: str = None) -> BidBookmark:
        existing = self.db.query(BidBookmark).filter(
            BidBookmark.user_id == user_id, BidBookmark.bid_id == bid_id
        ).first()
        if existing:
            return existing
        bookmark = BidBookmark(bid_id=bid_id, user_id=user_id, note=note)
        self.db.add(bookmark)
        self.db.commit()
        self.db.refresh(bookmark)
        return bookmark

    def remove(self, bid_id: int, user_id: int):
        bookmark = self.db.query(BidBookmark).filter(
            BidBookmark.user_id == user_id, BidBookmark.bid_id == bid_id
        ).first()
        if bookmark:
            self.db.delete(bookmark)
            self.db.commit()

    def list_bookmarks(self, user_id: int, page: int = 1, size: int = 20) -> dict:
        query = self.db.query(BidBookmark).filter(BidBookmark.user_id == user_id)
        total = query.count()
        items = query.order_by(BidBookmark.created_at.desc()).offset((page - 1) * size).limit(size).all()
        return {"items": items, "total": total}

    def get_bookmarked_ids(self, user_id: int, bid_ids: list) -> set:
        rows = self.db.query(BidBookmark.bid_id).filter(
            BidBookmark.user_id == user_id,
            BidBookmark.bid_id.in_(bid_ids)
        ).all()
        return {r.bid_id for r in rows}

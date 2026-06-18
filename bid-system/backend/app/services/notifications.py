"""
알림 서비스 (NotificationService)
"""
import logging
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_

from ..models import Notification, User

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, db: Session):
        self.db = db

    # ── 내부: dedup_key 기반 중복 체크 후 INSERT ────────────────────────
    def _create_deduped(
        self,
        user_id: Optional[int],
        ntype: str,
        title: str,
        body: Optional[str] = None,
        link: Optional[str] = None,
        dedup_key: Optional[str] = None,
    ) -> tuple:
        """(notification, is_new) 반환. dedup_key가 오늘 이미 존재하면 기존 반환."""
        if dedup_key:
            q = self.db.query(Notification).filter(
                Notification.dedup_key == dedup_key,
            )
            if user_id is not None:
                q = q.filter(Notification.user_id == user_id)
            else:
                q = q.filter(Notification.user_id.is_(None))
            existing = q.first()
            if existing:
                return existing, False

        n = Notification(
            user_id=user_id, ntype=ntype, title=title,
            body=body, link=link, dedup_key=dedup_key,
        )
        self.db.add(n)
        self.db.flush()   # id 채번 (commit은 호출자가)
        return n, True

    def create(
        self,
        user_id: Optional[int],
        ntype: str,
        title: str,
        body: Optional[str] = None,
        link: Optional[str] = None,
        dedup_key: Optional[str] = None,
    ) -> "Notification":
        n, _ = self._create_deduped(user_id, ntype, title, body, link, dedup_key)
        self.db.commit()
        self.db.refresh(n)
        return n

    def list_for_user(
        self, user_id: int, unread_only: bool = False, limit: int = 20
    ) -> list:
        q = self.db.query(Notification).filter(
            or_(Notification.user_id == user_id, Notification.user_id.is_(None))
        )
        if unread_only:
            q = q.filter(Notification.is_read == False)
        return q.order_by(Notification.created_at.desc()).limit(limit).all()

    def mark_read(self, notification_id: int, user_id: int) -> None:
        n = self.db.query(Notification).filter(
            Notification.id == notification_id,
            or_(Notification.user_id == user_id, Notification.user_id.is_(None)),
        ).first()
        if n:
            n.is_read = True
            self.db.commit()

    def mark_all_read(self, user_id: int) -> None:
        self.db.query(Notification).filter(
            or_(Notification.user_id == user_id, Notification.user_id.is_(None)),
            Notification.is_read == False,
        ).update({"is_read": True}, synchronize_session=False)
        self.db.commit()

    def unread_count(self, user_id: int) -> int:
        return self.db.query(Notification).filter(
            or_(Notification.user_id == user_id, Notification.user_id.is_(None)),
            Notification.is_read == False,
        ).count()

    # ── 키워드 매칭: bid_id당 사용자당 1건 ─────────────────────────────
    def create_keyword_match(self, bid, matched_keywords: list) -> list:
        kw_str = ", ".join(matched_keywords)
        title = f"[키워드 매칭] {bid.title[:60]}"
        body = f"키워드 '{kw_str}' 에 매칭된 공고입니다."
        link = f"/bids/{bid.id}"
        users = self.db.query(User).filter(User.is_active == True).all()
        results = []
        for u in users:
            dedup_key = f"keyword_match:{bid.id}"
            n, is_new = self._create_deduped(
                u.id, "keyword_match", title, body, link, dedup_key=dedup_key
            )
            if is_new:
                results.append(n)
        self.db.commit()
        for n in results:
            self.db.refresh(n)
        return results

    # ── 사정율 급변: 기관명+날짜 기준 하루 1건 ─────────────────────────
    def create_srate_spike(
        self,
        agency_name: str,
        industry_name: str,
        direction: str,
        delta_pct: float,
    ) -> list:
        from datetime import date
        arrow = "▲" if direction == "up" else "▼"
        title = f"[사정율 급변] {agency_name} {arrow}{abs(delta_pct):.1f}%"
        body = f"{industry_name} 공종 사정율이 {arrow}{abs(delta_pct):.1f}% 변동했습니다."
        today_str = date.today().strftime("%Y%m%d")
        safe_agency = agency_name.replace(":", "_")[:80]
        dedup_key = f"srate_spike:{safe_agency}:{today_str}"
        n, is_new = self._create_deduped(
            None, "srate_spike", title, body, dedup_key=dedup_key
        )
        self.db.commit()
        if is_new:
            self.db.refresh(n)
        return [n]

    # ── 투찰 마감 알림: execution_id + days_left + 날짜 기준 1건 ────────
    def create_execution_deadline(
        self, user_id: int, exec_title: str, days_left: int,
        execution_id: Optional[int] = None,
    ) -> "Notification":
        from datetime import date
        if days_left == 0:
            title = f"[오늘 개찰] {exec_title[:45]}"
            body = "오늘 개찰 마감입니다. 투찰 완료 여부를 확인하세요."
        else:
            title = f"[D-{days_left}] 내일 개찰: {exec_title[:40]}"
            body = f"{days_left}일 후 개찰 마감입니다. 투찰률을 최종 확인하세요."
        today_str = date.today().strftime("%Y%m%d")
        dedup_key = f"exec_deadline:{execution_id}:D{days_left}:{today_str}" if execution_id else None
        n, is_new = self._create_deduped(
            user_id, "execution_deadline", title, body,
            link="/executions", dedup_key=dedup_key,
        )
        self.db.commit()
        if is_new:
            self.db.refresh(n)
        return n

    # ── 결과 입력 리마인더: execution_id + 날짜 기준 하루 1건 ────────────
    def create_result_reminder(
        self, user_id: int, exec_title: str,
        execution_id: Optional[int] = None,
    ) -> "Notification":
        from datetime import date
        title = f"[결과 입력 요청] {exec_title[:45]}"
        body = "개찰이 완료된 것으로 보입니다. 낙찰/패찰 결과를 입력해주세요."
        today_str = date.today().strftime("%Y%m%d")
        dedup_key = f"result_reminder:{execution_id}:{today_str}" if execution_id else None
        n, is_new = self._create_deduped(
            user_id, "execution_result", title, body,
            link="/executions", dedup_key=dedup_key,
        )
        self.db.commit()
        if is_new:
            self.db.refresh(n)
        return n

    def create_pre_open_alert(
        self, user_id: int, exec_title: str,
        execution_id: Optional[int] = None,
    ) -> "Notification":
        """개찰 약 3시간 전 알림 — 시간 단위 dedup."""
        from datetime import datetime
        hour_str = datetime.now().strftime("%Y%m%d%H")
        title = f"[3시간 전] {exec_title[:43]}"
        body = "약 3시간 후 개찰 예정입니다. 투찰률 최종 확인 후 투찰을 완료하세요."
        dedup_key = f"pre_open:{execution_id}:{hour_str}" if execution_id else None
        n, is_new = self._create_deduped(
            user_id, "pre_open_alert", title, body,
            link="/executions", dedup_key=dedup_key,
        )
        self.db.commit()
        if is_new:
            self.db.refresh(n)
        return n

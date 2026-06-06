"""怨듦퀬쨌?숈같寃곌낵 ?섏쭛 ?쒕퉬????DB upsert 諛?CollectionLog 湲곕줉"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from loguru import logger
from sqlalchemy.orm import Session

from app.collector.client import BidNotice
from app.collector.client import BidResult as BidResultData
from app.collector.client import NarajangterClient
from app.models import Agency, Bid, BidResult, Competitor, CollectionLog, WatchKeyword
from app.services import NotificationService

CollectType = Literal["notice_cnstwk", "notice_servc", "notice_thng"]


# ------------------------------------------------------------------ #
# ?대? upsert ?ы띁                                                     #
# ------------------------------------------------------------------ #


def _upsert_agency(db: Session, name: str) -> Agency:
    """諛쒖＜泥?upsert ??name 湲곗?. ?좉퇋 諛쒖＜泥섎㈃ flush."""
    agency = db.query(Agency).filter(Agency.name == name).first()
    if not agency:
        agency = Agency(name=name)
        db.add(agency)
        db.flush()
    return agency


def _upsert_bid(db: Session, notice: BidNotice, agency_id: int) -> tuple[Bid, bool]:
    """怨듦퀬 upsert ??announcement_no 湲곗?. ??踰덉㎏ 諛섑솚媛?True = ?좉퇋."""
    bid = db.query(Bid).filter(Bid.announcement_no == notice.announcement_no).first()
    if bid:
        bid.title = notice.title
        bid.base_amount = notice.base_amount or 0
        if notice.bid_open_date:
            bid.bid_open_date = _parse_datetime(notice.bid_open_date)
        return bid, False
    bid = Bid(
        announcement_no=notice.announcement_no,
        title=notice.title,
        agency_id=agency_id,
        base_amount=notice.base_amount or 0,
        notice_date=_parse_date(notice.notice_date),
        bid_open_date=_parse_datetime(notice.bid_open_date),
        status="open",
        source="api",
    )
    db.add(bid)
    db.flush()
    return bid, True


def _upsert_competitor(db: Session, name: str, biz_reg_no: str | None) -> Competitor:
    """寃쎌웳??upsert ??biz_reg_no ?곗꽑, ?놁쑝硫?name 湲곗?."""
    if biz_reg_no:
        competitor = db.query(Competitor).filter(Competitor.biz_reg_no == biz_reg_no).first()
    else:
        competitor = db.query(Competitor).filter(Competitor.name == name).first()
    if not competitor:
        competitor = Competitor(name=name, biz_reg_no=biz_reg_no)
        db.add(competitor)
        db.flush()
    return competitor


def _upsert_bid_result(
    db: Session,
    bid_id: int,
    competitor_id: int,
    data: BidResultData,
) -> bool:
    """?숈같寃곌낵 upsert ??(bid_id, competitor_id) 湲곗?. True = ?좉퇋."""
    result = (
        db.query(BidResult)
        .filter(BidResult.bid_id == bid_id, BidResult.competitor_id == competitor_id)
        .first()
    )
    if result:
        result.bid_amount = data.bid_amount or 0
        result.bid_rate = data.bid_rate or 0
        result.rank = data.rank or 0
        result.is_winner = data.is_winner
        return False
    db.add(
        BidResult(
            bid_id=bid_id,
            competitor_id=competitor_id,
            bid_amount=data.bid_amount or 0,
            bid_rate=data.bid_rate or 0,
            rank=data.rank or 0,
            is_winner=data.is_winner,
        )
    )
    return True


# ------------------------------------------------------------------ #
# ?좎쭨 ?뚯떛 ?ы띁                                                       #
# ------------------------------------------------------------------ #


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    for fmt in ("%Y%m%d%H%M", "%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(s[: len(fmt)], fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _parse_datetime(s: str | None) -> datetime | None:
    if not s:
        return None
    for fmt in ("%Y%m%d%H%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[: len(fmt)], fmt).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
    return None


def _date_range(days_back: int) -> tuple[str, str]:
    """YYYYMMDDHHMM ?뺤떇???쒖옉쨌???좎쭨 臾몄옄??諛섑솚"""
    end = datetime.now()
    start = end - timedelta(days=days_back)
    return start.strftime("%Y%m%d0000"), end.strftime("%Y%m%d2359")


# ------------------------------------------------------------------ #
# CollectionLog 湲곕줉                                                   #
# ------------------------------------------------------------------ #


def _record_log(
    db: Session,
    collect_type: str,
    success: int,
    fail: int,
    duration: float,
    error_summary: str | None = None,
) -> CollectionLog:
    log = CollectionLog(
        collect_type=collect_type,
        collected_at=datetime.now(tz=timezone.utc),
        success_count=success,
        fail_count=fail,
        duration_sec=round(duration, 2),
        error_summary=error_summary,
    )
    db.add(log)
    db.commit()
    return log


def _check_keyword_match(db: Session, bid: Bid) -> None:
    keywords = db.query(WatchKeyword).filter(WatchKeyword.is_active == True).all()
    if not keywords:
        return
    title_lower = bid.title.lower()
    matched = [kw.keyword for kw in keywords if kw.keyword.lower() in title_lower]
    if matched:
        try:
            NotificationService(db).create_keyword_match(bid, matched)
        except Exception as exc:
            logger.warning("keyword notify failed bid={}: {}", bid.id, exc)


# ------------------------------------------------------------------ #
# 怨듦컻 ?쒕퉬???⑥닔                                                     #
# ------------------------------------------------------------------ #


def collect_notices(
    db: Session,
    client: NarajangterClient,
    collect_type: CollectType,
    days_back: int = 7,
) -> CollectionLog:
    """怨듭궗/?⑹뿭/臾쇳뭹 怨듦퀬 ?섏쭛 ??bids + agencies upsert + CollectionLog 湲곕줉"""
    paginate_fn = {
        "notice_cnstwk": client.paginate_construction_bids,
        "notice_servc": client.paginate_service_bids,
        "notice_thng": client.paginate_goods_bids,
    }[collect_type]

    bgn_dt, end_dt = _date_range(days_back)
    success = fail = 0
    errors: list[str] = []
    t0 = time.monotonic()

    try:
        for page in paginate_fn(bgn_dt, end_dt):
            for notice in page:
                try:
                    agency = _upsert_agency(db, notice.agency_name)
                    bid, is_new = _upsert_bid(db, notice, agency.id)
                    db.commit()
                    if is_new:
                        _check_keyword_match(db, bid)
                    success += 1
                except Exception as exc:
                    db.rollback()
                    fail += 1
                    errors.append(str(exc)[:200])
                    logger.warning("bid upsert failed {}: {}", notice.announcement_no, exc)
    except Exception as exc:
        errors.append(f"?섏씠吏?ㅼ씠???ㅻ쪟: {str(exc)[:200]}")
        logger.error("怨듦퀬 ?섏쭛 以묐떒: {}", exc)

    return _record_log(
        db,
        collect_type,
        success,
        fail,
        time.monotonic() - t0,
        "; ".join(errors) if errors else None,
    )


def collect_results(
    db: Session,
    client: NarajangterClient,
    days_back: int = 30,
) -> CollectionLog:
    """?숈같寃곌낵 ?섏쭛 ??bid_results + competitors upsert + CollectionLog 湲곕줉"""
    bgn_dt, end_dt = _date_range(days_back)
    success = fail = 0
    errors: list[str] = []
    t0 = time.monotonic()

    try:
        for page in client.paginate_bid_results(bgn_dt, end_dt):
            for result_data in page:
                try:
                    bid = (
                        db.query(Bid)
                        .filter(Bid.announcement_no == result_data.announcement_no)
                        .first()
                    )
                    if not bid:
                        logger.debug("怨듦퀬 ?놁쓬, 嫄대꼫?: {}", result_data.announcement_no)
                        continue
                    competitor = _upsert_competitor(
                        db, result_data.competitor_name, result_data.biz_reg_no
                    )
                    _upsert_bid_result(db, bid.id, competitor.id, result_data)
                    db.commit()
                    success += 1
                except Exception as exc:
                    db.rollback()
                    fail += 1
                    errors.append(str(exc)[:200])
                    logger.warning(
                        "?숈같寃곌낵 ????ㅽ뙣 {}: {}", result_data.announcement_no, exc
                    )
    except Exception as exc:
        errors.append(f"?섏씠吏?ㅼ씠???ㅻ쪟: {str(exc)[:200]}")
        logger.error("?숈같寃곌낵 ?섏쭛 以묐떒: {}", exc)

    return _record_log(
        db,
        "result",
        success,
        fail,
        time.monotonic() - t0,
        "; ".join(errors) if errors else None,
    )


def run_full_collection(db: Session) -> list[CollectionLog]:
    """?꾩껜 ?섏쭛 吏꾩엯????notices(3醫? ??results ?쒖꽌濡??ㅽ뻾"""
    from app.config import get_settings

    settings = get_settings()
    client = NarajangterClient(api_key=settings.g2b_api_key)

    logs: list[CollectionLog] = []
    for ctype in ("notice_cnstwk", "notice_servc", "notice_thng"):
        log = collect_notices(db, client, ctype)
        logs.append(log)
        logger.info(
            "?섏쭛 ?꾨즺 [{}]: ?깃났={}, ?ㅽ뙣={}", ctype, log.success_count, log.fail_count
        )

    log = collect_results(db, client)
    logs.append(log)
    logger.info(
        "?숈같寃곌낵 ?섏쭛 ?꾨즺: ?깃났={}, ?ㅽ뙣={}", log.success_count, log.fail_count
    )

    return logs

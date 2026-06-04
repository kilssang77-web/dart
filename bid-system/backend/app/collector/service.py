"""공고·낙찰결과 수집 서비스 — DB upsert 및 CollectionLog 기록"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from loguru import logger
from sqlalchemy.orm import Session

from app.collector.client import BidNotice
from app.collector.client import BidResult as BidResultData
from app.collector.client import NarajangterClient
from app.models import Agency, Bid, BidResult, Competitor, CollectionLog

CollectType = Literal["notice_cnstwk", "notice_servc", "notice_thng"]


# ------------------------------------------------------------------ #
# 내부 upsert 헬퍼                                                     #
# ------------------------------------------------------------------ #


def _upsert_agency(db: Session, name: str) -> Agency:
    """발주처 upsert — name 기준. 신규 발주처면 flush."""
    agency = db.query(Agency).filter(Agency.name == name).first()
    if not agency:
        agency = Agency(name=name)
        db.add(agency)
        db.flush()
    return agency


def _upsert_bid(db: Session, notice: BidNotice, agency_id: int) -> tuple[Bid, bool]:
    """공고 upsert — announcement_no 기준. 두 번째 반환값 True = 신규."""
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
    """경쟁사 upsert — biz_reg_no 우선, 없으면 name 기준."""
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
    """낙찰결과 upsert — (bid_id, competitor_id) 기준. True = 신규."""
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
# 날짜 파싱 헬퍼                                                       #
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
    """YYYYMMDDHHMM 형식의 시작·끝 날짜 문자열 반환"""
    end = datetime.now()
    start = end - timedelta(days=days_back)
    return start.strftime("%Y%m%d0000"), end.strftime("%Y%m%d2359")


# ------------------------------------------------------------------ #
# CollectionLog 기록                                                   #
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


# ------------------------------------------------------------------ #
# 공개 서비스 함수                                                     #
# ------------------------------------------------------------------ #


def collect_notices(
    db: Session,
    client: NarajangterClient,
    collect_type: CollectType,
    days_back: int = 7,
) -> CollectionLog:
    """공사/용역/물품 공고 수집 → bids + agencies upsert + CollectionLog 기록"""
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
                    _upsert_bid(db, notice, agency.id)
                    db.commit()
                    success += 1
                except Exception as exc:
                    db.rollback()
                    fail += 1
                    errors.append(str(exc)[:200])
                    logger.warning("공고 저장 실패 {}: {}", notice.announcement_no, exc)
    except Exception as exc:
        errors.append(f"페이지네이션 오류: {str(exc)[:200]}")
        logger.error("공고 수집 중단: {}", exc)

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
    """낙찰결과 수집 → bid_results + competitors upsert + CollectionLog 기록"""
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
                        logger.debug("공고 없음, 건너뜀: {}", result_data.announcement_no)
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
                        "낙찰결과 저장 실패 {}: {}", result_data.announcement_no, exc
                    )
    except Exception as exc:
        errors.append(f"페이지네이션 오류: {str(exc)[:200]}")
        logger.error("낙찰결과 수집 중단: {}", exc)

    return _record_log(
        db,
        "result",
        success,
        fail,
        time.monotonic() - t0,
        "; ".join(errors) if errors else None,
    )


def run_full_collection(db: Session) -> list[CollectionLog]:
    """전체 수집 진입점 — notices(3종) → results 순서로 실행"""
    from app.config import get_settings

    settings = get_settings()
    client = NarajangterClient(api_key=settings.nara_api_key)

    logs: list[CollectionLog] = []
    for ctype in ("notice_cnstwk", "notice_servc", "notice_thng"):
        log = collect_notices(db, client, ctype)
        logs.append(log)
        logger.info(
            "수집 완료 [{}]: 성공={}, 실패={}", ctype, log.success_count, log.fail_count
        )

    log = collect_results(db, client)
    logs.append(log)
    logger.info(
        "낙찰결과 수집 완료: 성공={}, 실패={}", log.success_count, log.fail_count
    )

    return logs

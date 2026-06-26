"""怨듦퀬쨌?숈같寃곌낵 ?섏쭛 ?쒕퉬????DB upsert 諛?CollectionLog 湲곕줉"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.collector.client import BidNotice
from app.collector.client import BidResult as BidResultData
from app.collector.client import NarajangterClient
from app.models import Agency, Bid, BidResult, Competitor, CollectionLog, Industry, Region, WatchKeyword
from app.services import NotificationService

CollectType = Literal["notice_cnstwk", "notice_servc", "notice_thng"]

_industry_cache: dict[str, int | None] = {}
_region_cache:   dict[str, int | None] = {}

# 제목 키워드 → 업종명 매핑 (G2B API indutyNm null인 수의계약·소액공고 대상)
# 우선순위 순 배치: 앞 패턴이 뒤보다 우선 적용
_TITLE_INDUSTRY_KEYWORDS: list[tuple[list[str], str]] = [
    (["방수공사", "방수처리", "방수 공사", "방수도장"],           "도장ㆍ습식ㆍ방수ㆍ석공사업"),
    (["도장공사", "도장 공사", "페인트", "도색공사"],             "도장ㆍ습식ㆍ방수ㆍ석공사업"),
    (["미장공사", "타일공사", "석공사", "습식공사"],               "도장ㆍ습식ㆍ방수ㆍ석공사업"),
    (["실내건축공사", "인테리어공사", "내장공사", "칸막이공사", "목공사", "도배공사"],
                                                                   "실내건축공사업"),
    (["창호공사", "창문공사", "유리공사", "지붕공사", "금속공사"], "금속창호ㆍ지붕건축물조립공사업"),
    (["전기공사", "조명공사", "전기설비", "수변전", "배전공사"],   "전기공사업"),
    (["기계설비공사", "냉난방공사", "공조공사", "환기공사", "배관공사", "냉난방기"],
                                                                   "기계설비ㆍ가스공사업"),
    (["소방공사", "소화설비", "스프링클러"],                        "일반소방시설공사업(기계)"),
    (["철근콘크리트", "콘크리트공사", "내진보강", "구조보강"],     "철근ㆍ콘크리트공사업"),
    (["조경공사", "식재공사", "조경시설"],                          "조경공사업"),
    (["상하수도공사", "상수도공사", "하수도공사", "하수처리", "정수장", "배수공사"],
                                                                   "상ㆍ하수도설비공사업"),
    (["포장공사", "아스팔트", "보도공사", "포장보수", "도로포장"], "지반조성ㆍ포장공사업"),
    (["철거공사", "해체공사", "비계공사"],                          "구조물해체ㆍ비계공사업"),
    (["숲가꾸기", "풀베기", "덩굴류제거", "병해충방제"],           "산림사업법인(숲가꾸기 및 병해충방제)"),
    (["숲길", "등산로 정비"],                                       "산림사업법인(숲길 조성,관리)"),
    (["토목공사", "토공사"],                                        "토목공사업"),
    (["건축공사", "보수공사", "개선공사", "개보수", "리모델링", "증축", "신축"],
                                                                   "건축공사업"),
]

_title_industry_id_cache: dict[str, int | None] = {}


def _infer_industry_from_title(db: Session, title: str | None) -> int | None:
    """공고 제목 키워드로 업종 추론 — G2B indutyNm null인 수의계약/소액공고 대상."""
    if not title:
        return None
    if title in _title_industry_id_cache:
        return _title_industry_id_cache[title]

    title_lower = title.lower()
    for keywords, industry_name in _TITLE_INDUSTRY_KEYWORDS:
        if any(kw.lower() in title_lower for kw in keywords):
            iid = _resolve_industry_id(db, industry_name)
            _title_industry_id_cache[title] = iid
            return iid

    _title_industry_id_cache[title] = None
    return None


def _resolve_industry_id(db: Session, name: str | None) -> int | None:
    if not name:
        return None
    if name not in _industry_cache:
        # 1차: 정확 매칭
        row = db.query(Industry.id).filter(Industry.name == name).first()
        if not row and len(name) >= 4:
            # 2차: 부분 포함 매칭 (G2B API 문자열 변형 대응)
            row = db.query(Industry.id).filter(Industry.name.ilike(f"%{name}%")).first()
        _industry_cache[name] = row[0] if row else None
    return _industry_cache[name]


def _resolve_region_id(db: Session, name: str | None) -> int | None:
    if not name:
        return None
    if name not in _region_cache:
        row = db.query(Region.id).filter(Region.name == name).first()
        _region_cache[name] = row[0] if row else None
    return _region_cache[name]


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
    """공고 upsert — announcement_no 기준. 신규이면 True 반환."""
    industry_id = _resolve_industry_id(db, notice.industry_code)
    # G2B indutyNm null인 수의계약/소액공고 → 제목 키워드로 업종 추론
    if industry_id is None:
        industry_id = _infer_industry_from_title(db, notice.title)
    region_id   = _resolve_region_id(db, notice.region_code)

    bid = db.query(Bid).filter(Bid.announcement_no == notice.announcement_no).first()
    if bid:
        bid.title = notice.title
        # API에서 값이 있을 때만 업데이트 (기존 값 zero-out 방지)
        if notice.base_amount:
            bid.base_amount = notice.base_amount
        if notice.bid_open_date:
            bid.bid_open_date = _parse_datetime(notice.bid_open_date)
        if notice.bid_close_date and bid.bid_close_date is None:
            bid.bid_close_date = _parse_datetime(notice.bid_close_date)
        if notice.estimated_price and bid.estimated_price is None:
            bid.estimated_price = notice.estimated_price
        if notice.min_bid_rate and bid.min_bid_rate is None:
            bid.min_bid_rate = notice.min_bid_rate
        if notice.contract_method and bid.contract_method is None:
            bid.contract_method = notice.contract_method
        if notice.bid_method and bid.bid_method is None:
            bid.bid_method = notice.bid_method
        if notice.construction_work_div and bid.construction_work_div is None:
            bid.construction_work_div = notice.construction_work_div
        if notice.joint_supply_bid and bid.joint_supply_bid is None:
            bid.joint_supply_bid = notice.joint_supply_bid
        if notice.participant_limit and bid.participant_limit is None:
            bid.participant_limit = notice.participant_limit
        if bid.industry_id is None and industry_id:
            bid.industry_id = industry_id
        if bid.region_id is None and region_id:
            bid.region_id = region_id
        return bid, False
    bid = Bid(
        announcement_no=notice.announcement_no,
        title=notice.title,
        agency_id=agency_id,
        industry_id=industry_id,
        region_id=region_id,
        base_amount=notice.base_amount or 0,
        estimated_price=notice.estimated_price,
        min_bid_rate=notice.min_bid_rate,
        notice_date=_parse_date(notice.notice_date),
        bid_open_date=_parse_datetime(notice.bid_open_date),
        bid_close_date=_parse_datetime(notice.bid_close_date),
        contract_method=notice.contract_method,
        bid_method=notice.bid_method,
        construction_work_div=notice.construction_work_div,
        joint_supply_bid=notice.joint_supply_bid,
        participant_limit=notice.participant_limit,
        status="open",
        source="api",
    )
    db.add(bid)
    db.flush()
    return bid, True


def _upsert_competitor(db: Session, name: str, biz_reg_no: str | None) -> Competitor:
    """경쟁사 upsert — biz_reg_no 우선, 없으면 name 기준. SAVEPOINT로 race condition 방지."""
    if biz_reg_no:
        competitor = db.query(Competitor).filter(Competitor.biz_reg_no == biz_reg_no).first()
    else:
        competitor = db.query(Competitor).filter(Competitor.name == name).first()
    if competitor:
        return competitor
    try:
        with db.begin_nested():
            competitor = Competitor(name=name, biz_reg_no=biz_reg_no)
            db.add(competitor)
        return competitor
    except IntegrityError:
        if biz_reg_no:
            return db.query(Competitor).filter(Competitor.biz_reg_no == biz_reg_no).first()
        return db.query(Competitor).filter(Competitor.name == name).first()


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
    # (format_string, expected_string_length) — len(fmt) ≠ len(output)
    _DT_FMTS = [
        ("%Y%m%d%H%M",        12),
        ("%Y-%m-%d %H:%M:%S", 19),
        ("%Y-%m-%dT%H:%M:%S", 19),
        ("%Y-%m-%d",          10),
        ("%Y%m%d",             8),
    ]
    for fmt, strlen in _DT_FMTS:
        try:
            return datetime.strptime(s[:strlen], fmt).replace(tzinfo=timezone.utc)
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
    detail: dict[str, Any] | None = None,
) -> CollectionLog:
    log = CollectionLog(
        collect_type=collect_type,
        collected_at=datetime.now(tz=timezone.utc),
        success_count=success,
        fail_count=fail,
        duration_sec=round(duration, 2),
        error_summary=error_summary,
        detail_json=json.dumps(detail, ensure_ascii=False) if detail else None,
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
_NOTICE_META = {
    'notice_cnstwk': {
        'label': '공사 입찰공고',
        'source': '나라장터 G2B API',
        'endpoint': 'getBidPblancListInfoCnstwk',
        'api_base': 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService',
    },
    'notice_servc': {
        'label': '용역 입찰공고',
        'source': '나라장터 G2B API',
        'endpoint': 'getBidPblancListInfoServc',
        'api_base': 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService',
    },
    'notice_thng': {
        'label': '물품 입찰공고',
        'source': '나라장터 G2B API',
        'endpoint': 'getBidPblancListInfoThng',
        'api_base': 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService',
    },
}


def collect_notices(
    db: Session,
    client: NarajangterClient,
    collect_type: CollectType,
    days_back: int = 7,
) -> CollectionLog:
    """공사/용역/물품 공고 수집 — bids + agencies upsert + CollectionLog 기록"""
    paginate_fn = {
        "notice_cnstwk": client.paginate_construction_bids,
        "notice_servc": client.paginate_service_bids,
        "notice_thng": client.paginate_goods_bids,
    }[collect_type]

    bgn_dt, end_dt = _date_range(days_back)
    success = fail = 0
    errors: list[str] = []
    error_details: list[str] = []
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
                    msg = str(exc)
                    errors.append(msg[:200])
                    error_details.append(f"[{notice.announcement_no}] {msg[:150]}")
                    logger.warning("bid upsert failed {}: {}", notice.announcement_no, exc)
    except Exception as exc:
        msg = str(exc)
        errors.append(f"페이지네이션 오류: {msg[:200]}")
        error_details.append(f"API 호출 실패: {msg[:200]}")
        logger.error("공고 수집 실패: {}", exc)

    meta = _NOTICE_META.get(collect_type, {})
    detail = {
        **meta,
        "date_from": bgn_dt,
        "date_to": end_dt,
        "days_back": days_back,
        "total_processed": success + fail,
    }
    if error_details:
        detail["error_details"] = error_details[:20]

    return _record_log(
        db,
        collect_type,
        success,
        fail,
        time.monotonic() - t0,
        "; ".join(errors) if errors else None,
        detail=detail,
    )


def collect_results(
    db: Session,
    client: NarajangterClient,
    days_back: int = 30,
) -> CollectionLog:
    """낙찰결과 수집 — bid_results + competitors upsert + CollectionLog 기록"""
    bgn_dt, end_dt = _date_range(days_back)
    success = fail = 0
    errors: list[str] = []
    error_details: list[str] = []
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
                    msg = str(exc)
                    errors.append(msg[:200])
                    error_details.append(f"[{result_data.announcement_no}] {msg[:150]}")
                    logger.warning("낙찰결과 저장 실패 {}: {}", result_data.announcement_no, exc)
    except Exception as exc:
        msg = str(exc)
        errors.append(f"페이지네이션 오류: {msg[:200]}")
        error_details.append(f"API 호출 실패: {msg[:200]}")
        logger.error("낙찰결과 수집 실패: {}", exc)

    detail = {
        "label": "낙찰결과",
        "source": "나라장터 G2B API",
        "endpoint": "getScsbidListSttusCnstwk",
        "api_base": "https://apis.data.go.kr/1230000/as/ScsbidInfoService",
        "date_from": bgn_dt,
        "date_to": end_dt,
        "days_back": days_back,
        "total_processed": success + fail,
    }
    if error_details:
        detail["error_details"] = error_details[:20]

    return _record_log(
        db,
        "result",
        success,
        fail,
        time.monotonic() - t0,
        "; ".join(errors) if errors else None,
        detail=detail,
    )


def run_full_collection(db: Session) -> list[CollectionLog]:
    """?꾩껜 ?섏쭛 吏꾩엯????notices(3醫? ??results ?쒖꽌濡??ㅽ뻾"""
    from app.config import get_settings

    settings = get_settings()
    client = NarajangterClient(api_key=settings.g2b_api_key)

    logs: list[CollectionLog] = []
    log = collect_notices(db, client, "notice_cnstwk")
    logs.append(log)
    logger.info(
        "공사공고 수집 완료: 성공={}, 실패={}", log.success_count, log.fail_count
    )

    log = collect_results(db, client)
    logs.append(log)
    logger.info(
        "?숈같寃곌낵 ?섏쭛 ?꾨즺: ?깃났={}, ?ㅽ뙣={}", log.success_count, log.fail_count
    )

    return logs

def sync_inpo21c_to_bids(db: Session) -> dict:
    """
    inpo21c_bids 데이터를 bids 테이블로 역방향 동기화.

    G2B API 한계 보완:
      - base_amount: asignBdgtAmt null → inpo21c_bids.base_amount 사용
      - estimated_price: presmptPrce null → inpo21c_bids.estimated_amount 사용
      - bid_open_date: opengDt null → inpo21c_bids.open_datetime 사용
      - participant_count: inpo21c_participants COUNT 집계
      - INSERT: G2B 미수집 공고를 inpo21c_bids 기반으로 신규 등록 (title 있는 경우만)
    """
    from sqlalchemy import text
    updated_base = updated_open = updated_participants = 0
    updated_a_value = updated_estimated = inserted_new = 0

    try:
        # 1. base_amount 동기화 (bids=0이고 inpo21c에 값 있는 경우)
        r = db.execute(text("""
            UPDATE bids b
            SET base_amount = ib.base_amount
            FROM inpo21c_bids ib
            WHERE b.announcement_no = ib.announcement_no
              AND b.base_amount = 0
              AND ib.base_amount > 0
        """))
        updated_base = r.rowcount

        # 2. estimated_price 동기화 (G2B API 누락 보완)
        r = db.execute(text("""
            UPDATE bids b
            SET estimated_price = ib.estimated_amount
            FROM inpo21c_bids ib
            WHERE b.announcement_no = ib.announcement_no
              AND ib.estimated_amount IS NOT NULL AND ib.estimated_amount > 0
              AND b.estimated_price IS NULL
        """))
        updated_estimated = r.rowcount

        # 3. bid_open_date 동기화 (bids=null이고 inpo21c에 값 있는 경우)
        r = db.execute(text("""
            UPDATE bids b
            SET bid_open_date = ib.open_datetime
            FROM inpo21c_bids ib
            WHERE b.announcement_no = ib.announcement_no
              AND b.bid_open_date IS NULL
              AND ib.open_datetime IS NOT NULL
        """))
        updated_open = r.rowcount

        # 4. a_value 동기화 (낙찰 완료 결과에서)
        r = db.execute(text("""
            UPDATE bids b
            SET a_value = ib.a_value
            FROM inpo21c_bids ib
            WHERE b.announcement_no = ib.announcement_no
              AND ib.a_value IS NOT NULL AND ib.a_value > 0
              AND b.a_value IS NULL
        """))
        updated_a_value = r.rowcount

        # 5. participant_count 동기화 (inpo21c 실증 참여자 수)
        r = db.execute(text("""
            UPDATE bids b
            SET participant_count = cnt.n
            FROM (
                SELECT ib.announcement_no, COUNT(ip.inpo21c_bid_id) AS n
                FROM inpo21c_bids ib
                JOIN inpo21c_participants ip ON ip.inpo21c_bid_id = ib.inpo21c_bid_id
                GROUP BY ib.announcement_no
            ) cnt
            WHERE b.announcement_no = cnt.announcement_no
              AND (b.participant_count IS NULL OR b.participant_count < cnt.n)
        """))
        updated_participants = r.rowcount

        # 6. G2B 미수집 공고 신규 INSERT (title이 있는 inpo21c_bids 기반)
        # 6a) 발주기관이 agencies 테이블에 없으면 먼저 등록
        db.execute(text("""
            INSERT INTO agencies (name)
            SELECT DISTINCT ib.agency_name
            FROM inpo21c_bids ib
            WHERE ib.announcement_no IS NOT NULL
              AND ib.agency_name IS NOT NULL AND ib.agency_name != ''
              AND ib.title IS NOT NULL AND ib.title != ''
              AND NOT EXISTS (SELECT 1 FROM bids b WHERE b.announcement_no = ib.announcement_no)
              AND NOT EXISTS (SELECT 1 FROM agencies a WHERE a.name = ib.agency_name)
        """))

        # 6b) bids에 없는 inpo21c 공고 INSERT
        r = db.execute(text("""
            INSERT INTO bids
                (announcement_no, title, agency_id, base_amount, estimated_price,
                 bid_open_date, status, source, a_value)
            SELECT
                ib.announcement_no,
                ib.title,
                a.id,
                COALESCE(ib.base_amount, 0),
                ib.estimated_amount,
                ib.open_datetime,
                'closed',
                'inpo21c',
                ib.a_value
            FROM inpo21c_bids ib
            JOIN agencies a ON a.name = ib.agency_name
            WHERE ib.announcement_no IS NOT NULL
              AND ib.title IS NOT NULL AND ib.title != ''
              AND NOT EXISTS (SELECT 1 FROM bids b WHERE b.announcement_no = ib.announcement_no)
            ON CONFLICT (announcement_no) DO NOTHING
        """))
        inserted_new = r.rowcount

        db.commit()
        logger.info(
            "inpo21c→bids 동기화 완료: base={}, estimated={}, open_date={}, a_value={}, participants={}, inserted_new={}",
            updated_base, updated_estimated, updated_open, updated_a_value,
            updated_participants, inserted_new,
        )
    except Exception as exc:
        db.rollback()
        logger.error("inpo21c→bids 동기화 실패: {}", exc)

    return {
        "updated_base_amount": updated_base,
        "updated_estimated_price": updated_estimated,
        "updated_open_date": updated_open,
        "updated_a_value": updated_a_value,
        "updated_participants": updated_participants,
        "inserted_new_from_inpo21c": inserted_new,
    }


def sync_inpo21c_notices_to_bids(db: Session) -> dict:
    """
    inpo21c_bid_notices → bids 동기화.

    G2B API에서 미수집되는 필드를 인포21 크롤링 결과로 보완:
      - bid_close_date   : 투찰마감일시 (inpo21c_bid_notices.bid_deadline)
      - estimated_price  : 추정가격      (inpo21c_bid_notices.estimated_amount)
      - min_bid_rate     : 낙찰하한율    (inpo21c_bid_notices.min_bid_rate / 100)
      - yega_method      : 예가방법      (inpo21c_bid_notices.yega_method)
      - registration_deadline : 참가등록마감 (inpo21c_bid_notices.reg_deadline)

    announcement_no 매칭: inpo21c는 'R26BK01563893-000' 형식이므로
    SPLIT_PART로 '-' 앞 부분만 사용.
    """
    from sqlalchemy import text
    stats = {}

    try:
        # base_amount 보완 (0인 경우)
        r = db.execute(text("""
            UPDATE bids b
            SET base_amount = n.base_amount
            FROM inpo21c_bid_notices n
            WHERE SPLIT_PART(n.announcement_no, '-', 1) = b.announcement_no
              AND n.base_amount IS NOT NULL AND n.base_amount > 0
              AND (b.base_amount IS NULL OR b.base_amount = 0)
        """))
        stats["base_amount"] = r.rowcount

        # bid_open_date 보완
        r = db.execute(text("""
            UPDATE bids b
            SET bid_open_date = n.open_datetime
            FROM inpo21c_bid_notices n
            WHERE SPLIT_PART(n.announcement_no, '-', 1) = b.announcement_no
              AND n.open_datetime IS NOT NULL
              AND b.bid_open_date IS NULL
        """))
        stats["bid_open_date"] = r.rowcount

        r = db.execute(text("""
            UPDATE bids b
            SET bid_close_date = n.bid_deadline
            FROM inpo21c_bid_notices n
            WHERE SPLIT_PART(n.announcement_no, '-', 1) = b.announcement_no
              AND n.bid_deadline IS NOT NULL
              AND b.bid_close_date IS NULL
        """))
        stats["bid_close_date"] = r.rowcount

        r = db.execute(text("""
            UPDATE bids b
            SET estimated_price = n.estimated_amount
            FROM inpo21c_bid_notices n
            WHERE SPLIT_PART(n.announcement_no, '-', 1) = b.announcement_no
              AND n.estimated_amount IS NOT NULL AND n.estimated_amount > 0
              AND b.estimated_price IS NULL
        """))
        stats["estimated_price"] = r.rowcount

        r = db.execute(text("""
            UPDATE bids b
            SET min_bid_rate = n.min_bid_rate / 100.0
            FROM inpo21c_bid_notices n
            WHERE SPLIT_PART(n.announcement_no, '-', 1) = b.announcement_no
              AND n.min_bid_rate IS NOT NULL
              AND b.min_bid_rate IS NULL
        """))
        stats["min_bid_rate"] = r.rowcount

        r = db.execute(text("""
            UPDATE bids b
            SET yega_method = n.yega_method
            FROM inpo21c_bid_notices n
            WHERE SPLIT_PART(n.announcement_no, '-', 1) = b.announcement_no
              AND n.yega_method IS NOT NULL AND n.yega_method != ''
              AND b.yega_method IS NULL
        """))
        stats["yega_method"] = r.rowcount

        r = db.execute(text("""
            UPDATE bids b
            SET registration_deadline = n.reg_deadline
            FROM inpo21c_bid_notices n
            WHERE SPLIT_PART(n.announcement_no, '-', 1) = b.announcement_no
              AND n.reg_deadline IS NOT NULL
              AND b.registration_deadline IS NULL
        """))
        stats["registration_deadline"] = r.rowcount

        # a_value 동기화 (inpo21c_bid_notices에서)
        r = db.execute(text("""
            UPDATE bids b
            SET a_value = n.a_value
            FROM inpo21c_bid_notices n
            WHERE SPLIT_PART(n.announcement_no, '-', 1) = b.announcement_no
              AND n.a_value IS NOT NULL AND n.a_value > 0
              AND b.a_value IS NULL
        """))
        stats["a_value_from_notices"] = r.rowcount

        db.commit()
        logger.info("inpo21c_notices→bids 동기화 완료: {}", stats)
    except Exception as exc:
        db.rollback()
        logger.error("inpo21c_notices→bids 동기화 실패: {}", exc)
        raise

    return stats


def collect_scsbid_results(db: Session, days_back: int = 30) -> CollectionLog:
    """ScsbidInfoService 낙찰결과 보강 수집 — 스케줄러 직접 호출용 (클라이언트 내부 생성)."""
    from app.config import get_settings
    settings = get_settings()
    client = NarajangterClient(api_key=settings.g2b_api_key)
    return collect_results(db, client, days_back=days_back)


def collect_all_participants_g2b(db: Session, days_back: int = 7) -> dict:
    """
    getOpengResultListInfoOpengCompt — 개찰완료 전참여자 수집 (소스 최적화).

    [Phase 1 개선] inpo21c 우선 전략:
    - inpo21c_participants에 ≥3명 데이터가 있는 공고 → draw_no/bid_dt 보완만 수행 (API insert 스킵)
    - inpo21c 데이터 없는 공고 → G2B full insert (fallback)
    """
    from app.config import get_settings
    from app.collector.client import BidParticipant

    settings = get_settings()
    client = NarajangterClient(api_key=settings.g2b_api_key)

    bgn_dt, end_dt = _date_range(days_back)
    inpo_covered = draw_updated = g2b_filled = skipped = fail = 0
    t0 = time.monotonic()

    from sqlalchemy import text as _t
    rows = db.execute(
        _t("SELECT id, announcement_no FROM bids "
           "WHERE bid_open_date >= NOW() - (:days * INTERVAL '1 day') "
           "  AND status IN ('closed', 'awarded') AND source = 'api'"),
        {"days": days_back},
    ).fetchall()

    for bid_id, announcement_no in rows:
        try:
            # inpo21c_participants 데이터 유무 체크 (공고번호 exact / SPLIT_PART 매칭)
            inpo_cnt = db.execute(_t("""
                SELECT COUNT(*) FROM inpo21c_participants ip
                JOIN inpo21c_bids ib ON ib.inpo21c_bid_id = ip.inpo21c_bid_id
                WHERE ib.announcement_no = :ano
                   OR SPLIT_PART(ib.announcement_no, '-', 1) = :ano
            """), {"ano": announcement_no}).scalar() or 0

            participants: list[BidParticipant] = client.get_participants_for_bid(announcement_no)
            if not participants:
                skipped += 1
                continue

            if inpo_cnt >= 3:
                # inpo21c 데이터 충분 — draw_no / bid_dt만 보완
                for p in participants:
                    if not p.biz_reg_no:
                        continue
                    if p.draw_no1 is not None or p.draw_no2 is not None:
                        db.execute(_t("""
                            UPDATE bid_results br
                            SET draw_no1 = COALESCE(br.draw_no1, :dn1),
                                draw_no2 = COALESCE(br.draw_no2, :dn2),
                                bid_dt   = COALESCE(br.bid_dt,   :bdt)
                            FROM competitors c
                            WHERE br.bid_id = :bid_id
                              AND br.competitor_id = c.id
                              AND c.biz_reg_no = :bno
                        """), {
                            "bid_id": bid_id,
                            "dn1": p.draw_no1,
                            "dn2": p.draw_no2,
                            "bdt": _parse_datetime(p.bid_dt),
                            "bno": p.biz_reg_no,
                        })
                db.commit()
                draw_updated += 1
                inpo_covered += 1
            else:
                # inpo21c 미수집 — G2B full insert
                seen_competitor_ids: set[int] = set()
                for p in participants:
                    if not p.competitor_name:
                        continue
                    competitor = _upsert_competitor(db, p.competitor_name, p.biz_reg_no)
                    if competitor.id in seen_competitor_ids:
                        continue
                    seen_competitor_ids.add(competitor.id)
                    existing = (
                        db.query(BidResult)
                        .filter(BidResult.bid_id == bid_id, BidResult.competitor_id == competitor.id)
                        .first()
                    )
                    if existing:
                        if p.draw_no1 is not None:
                            existing.draw_no1 = p.draw_no1
                        if p.draw_no2 is not None:
                            existing.draw_no2 = p.draw_no2
                        if p.bid_dt:
                            existing.bid_dt = _parse_datetime(p.bid_dt)
                        if p.bid_amount:
                            existing.bid_amount = p.bid_amount
                        if p.bid_rate:
                            existing.bid_rate = p.bid_rate
                    else:
                        db.add(BidResult(
                            bid_id=bid_id,
                            competitor_id=competitor.id,
                            bid_amount=p.bid_amount or 0,
                            bid_rate=p.bid_rate or 0,
                            rank=p.rank or 0,
                            is_winner=p.is_winner,
                            draw_no1=p.draw_no1,
                            draw_no2=p.draw_no2,
                            bid_dt=_parse_datetime(p.bid_dt),
                        ))

                bid_obj = db.query(Bid).filter(Bid.id == bid_id).first()
                if bid_obj:
                    bid_obj.participant_count = len(participants)

                db.commit()
                g2b_filled += 1

        except Exception as exc:
            db.rollback()
            fail += 1
            logger.warning("전참여자 수집 실패 {}: {}", announcement_no, exc)

    elapsed = time.monotonic() - t0
    logger.info(
        "G2B 전참여자 수집: inpo_covered={} draw_updated={} g2b_filled={} skipped={} fail={} ({:.1f}s)",
        inpo_covered, draw_updated, g2b_filled, skipped, fail, elapsed,
    )
    return {
        "inpo_covered": inpo_covered,
        "draw_updated": draw_updated,
        "g2b_filled": g2b_filled,
        "skipped": skipped,
        "fail": fail,
        "elapsed_s": round(elapsed, 1),
    }


def sync_assessment_rate_from_inpo21c(db: Session) -> dict:
    """
    [Phase 1 신규] inpo21c_participants.assessment_rate → bid_results.assessment_rate 역동기화.

    inpo21c에서 수집한 실증 사정율을 bid_results에 채워서 ML 학습 피처로 활용.
    assessment_rate가 이미 있는 행은 덮어쓰지 않는다.
    """
    from sqlalchemy import text as _t

    try:
        # CTE로 매칭 후 UPDATE — PostgreSQL UPDATE alias 제한 우회
        result = db.execute(_t("""
            WITH matched AS (
                SELECT br.id AS br_id, ip.assessment_rate
                FROM bid_results br
                JOIN bids b ON b.id = br.bid_id
                JOIN inpo21c_bids ib ON (
                    b.announcement_no = ib.announcement_no
                    OR b.announcement_no = SPLIT_PART(ib.announcement_no, '-', 1)
                )
                JOIN inpo21c_participants ip ON ip.inpo21c_bid_id = ib.inpo21c_bid_id
                JOIN competitors c ON c.id = br.competitor_id
                WHERE ip.assessment_rate IS NOT NULL
                  AND br.assessment_rate IS NULL
                  AND (c.biz_reg_no = ip.biz_reg_no OR c.name = ip.company_name)
            )
            UPDATE bid_results br
            SET assessment_rate = matched.assessment_rate
            FROM matched
            WHERE br.id = matched.br_id
        """))
        updated = result.rowcount
        db.commit()
        logger.info("assessment_rate 역동기화 완료: {}건 bid_results 갱신", updated)
        return {"updated": updated}
    except Exception as exc:
        db.rollback()
        logger.error("assessment_rate 역동기화 실패: {}", exc)
        return {"updated": 0, "error": str(exc)}


def collect_g2b_yega_detail(db: Session, days_back: int = 7) -> dict:
    """
    getOpengResultListInfoCnstwkPreparPcDetail — 복수예가 상세 수집 (일괄 페이지네이션).

    [Phase 1 개선] inpo21c_yega 우선 전략:
    - inpo21c_yega에 이미 데이터가 있는 공고는 G2B API 스킵 (inpo21c가 더 풍부)
    - inpo21c 미수집 공고만 G2B에서 수집
    """
    from app.config import get_settings
    from sqlalchemy import text as _t

    settings = get_settings()
    client = NarajangterClient(api_key=settings.g2b_api_key)

    bgn_dt, end_dt = _date_range(days_back)
    inserted = updated = fail = pages = skipped_by_inpo = 0
    t0 = time.monotonic()

    # 우리 DB 공고번호 SET (매칭 필터용)
    known_rows = db.execute(
        _t("SELECT announcement_no FROM bids "
           "WHERE bid_open_date >= NOW() - (:days * INTERVAL '1 day') "
           "  AND status IN ('closed', 'awarded') AND source = 'api'"),
        {"days": days_back},
    ).fetchall()
    known_nos: set[str] = {r[0] for r in known_rows}
    if not known_nos:
        return {"inserted": 0, "updated": 0, "fail": 0, "skipped_by_inpo": 0, "elapsed_s": 0.0}

    # inpo21c_yega에 이미 데이터가 있는 공고번호 — 스킵 대상
    inpo_covered_rows = db.execute(_t("""
        SELECT DISTINCT ib.announcement_no
        FROM inpo21c_yega iy
        JOIN inpo21c_bids ib ON ib.inpo21c_bid_id = iy.inpo21c_bid_id
        WHERE ib.announcement_no = ANY(:anos)
           OR SPLIT_PART(ib.announcement_no, '-', 1) = ANY(:anos)
    """), {"anos": list(known_nos)}).fetchall()
    inpo_yega_nos: set[str] = set()
    for r in inpo_covered_rows:
        ano = r[0]
        inpo_yega_nos.add(ano)
        # SPLIT_PART 형식이면 dash 전 부분도 등록
        inpo_yega_nos.add(ano.split("-")[0])

    # inpo21c에 없는 공고만 G2B에서 수집
    target_nos = known_nos - inpo_yega_nos
    skipped_by_inpo = len(known_nos) - len(target_nos)
    if not target_nos:
        logger.info("G2B 예가상세: inpo21c 완전 커버 — G2B 수집 스킵 ({}건)", skipped_by_inpo)
        return {"inserted": 0, "updated": 0, "fail": 0, "skipped_by_inpo": skipped_by_inpo, "elapsed_s": 0.0}

    # 페이지네이션
    num_of_rows = 999
    page_no = 1
    while True:
        try:
            raw = client._get_results(
                "getOpengResultListInfoCnstwkPreparPcDetail",
                {
                    "inqryDiv": 1,
                    "inqryBgnDt": bgn_dt,
                    "inqryEndDt": end_dt,
                    "pageNo": page_no,
                    "numOfRows": num_of_rows,
                },
            )
        except Exception as exc:
            fail += 1
            logger.warning("G2B 예가상세 페이지 {} 호출 실패: {}", page_no, exc)
            break

        items_raw = client._extract_items(raw)
        if not items_raw:
            break
        pages += 1

        batch_inserted = batch_updated = 0
        for item in items_raw:
            ano = item.get("bidNtceNo", "")
            if ano not in target_nos:
                continue
            sno_raw = item.get("compnoRsrvtnPrceSno")
            if not sno_raw:
                continue
            try:
                yega_no = int(str(sno_raw).strip())
            except (ValueError, TypeError):
                continue

            try:
                def _si(v):
                    try: return int(str(v).replace(",", ""))
                    except: return None
                db.execute(_t("""
                    INSERT INTO g2b_yega_details
                        (announcement_no, yega_no, base_amount, estimated_price,
                         yega_total, yega_price, is_selected, draw_count, bid_open_dt)
                    VALUES
                        (:ano, :no, :base, :est, :total, :price, :sel, :dcnt, :odt)
                    ON CONFLICT (announcement_no, yega_no) DO UPDATE SET
                        base_amount     = EXCLUDED.base_amount,
                        estimated_price = EXCLUDED.estimated_price,
                        yega_total      = EXCLUDED.yega_total,
                        yega_price      = EXCLUDED.yega_price,
                        is_selected     = EXCLUDED.is_selected,
                        draw_count      = EXCLUDED.draw_count,
                        bid_open_dt     = EXCLUDED.bid_open_dt
                """), {
                    "ano":   ano,
                    "no":    yega_no,
                    "base":  _si(item.get("bssamt")),
                    "est":   _si(item.get("plnprc")),
                    "total": _si(item.get("totRsrvtnPrceNum")),
                    "price": _si(item.get("bsisPlnprc")),
                    "sel":   str(item.get("drwtYn", "N")).upper() == "Y",
                    "dcnt":  _si(item.get("drwtNum")),
                    "odt":   _parse_datetime(item.get("rlOpengDt")),
                })
                batch_inserted += 1
            except Exception as exc:
                fail += 1
                logger.warning("G2B 예가상세 upsert 실패 {} no={}: {}", ano, yega_no, exc)

        try:
            db.commit()
            inserted += batch_inserted
        except Exception as exc:
            db.rollback()
            fail += batch_inserted
            logger.warning("G2B 예가상세 커밋 실패 page={}: {}", page_no, exc)

        total_count = client._extract_total_count(raw)
        if page_no * num_of_rows >= total_count:
            break
        page_no += 1

    elapsed = time.monotonic() - t0
    logger.info(
        "G2B 예가상세 수집 완료: inserted={} fail={} pages={} skipped_by_inpo={} ({:.1f}s)",
        inserted, fail, pages, skipped_by_inpo, elapsed,
    )
    return {
        "inserted": inserted,
        "fail": fail,
        "pages": pages,
        "skipped_by_inpo": skipped_by_inpo,
        "elapsed_s": round(elapsed, 1),
    }


def _upsert_agency_by_code(db: Session, code: str | None, name: str) -> Agency:
    """기관 upsert — code 우선, 없으면 name 기준."""
    if code:
        agency = db.query(Agency).filter(Agency.code == code).first()
        if agency:
            return agency
    agency = db.query(Agency).filter(Agency.name == name).first()
    if agency:
        if code and not agency.code:
            agency.code = code
        return agency
    agency = Agency(name=name, code=code)
    db.add(agency)
    db.flush()
    return agency


def backfill_historical_bids(
    db: Session,
    date_from: str = "2022-01-01",
    date_to: str | None = None,
    batch_months: int = 1,
) -> dict:
    """
    getScsbidListSttusCnstwkPPSSrch — 역사 낙찰 데이터 백필.

    date_from~date_to 기간을 batch_months 단위로 분할해 순차 수집.
    기존 bids 레코드가 있으면 bid_result만 보완, 없으면 최소 bid 생성.
    source='g2b_backfill'로 마킹.

    Returns: {inserted_bids, updated_bids, inserted_results, skipped, fail, elapsed_s}
    """
    from app.config import get_settings
    from app.collector.client import NarajangterClient
    from sqlalchemy import text as _t
    from datetime import date
    import calendar

    settings = get_settings()
    client = NarajangterClient(api_key=settings.g2b_api_key)

    end_dt = date_to or datetime.now().strftime("%Y-%m-%d")
    # date 객체로 변환
    cur = datetime.strptime(date_from, "%Y-%m-%d").date()
    end = datetime.strptime(end_dt, "%Y-%m-%d").date()

    inserted_bids = updated_bids = inserted_results = skipped = fail = 0
    t0 = time.monotonic()

    while cur <= end:
        # 월 범위 계산
        _, last_day = calendar.monthrange(cur.year, cur.month)
        chunk_end = min(date(cur.year, cur.month, last_day), end)
        bgn_str = cur.strftime("%Y%m%d") + "0000"
        end_str = chunk_end.strftime("%Y%m%d") + "2359"
        label = cur.strftime("%Y-%m")

        logger.info("백필 수집: {} ({} ~ {})", label, bgn_str, end_str)

        try:
            for page_items in client.paginate_scsbid_pps_search(bgn_str, end_str):
                for item in page_items:
                    ano = item.get("bidNtceNo", "").strip()
                    try:
                        if not ano:
                            skipped += 1
                            continue

                        # 낙찰률 파싱 — API는 퍼센트형 (e.g. "90.325")
                        rate_raw = item.get("sucsfbidRate", "")
                        try:
                            bid_rate = float(rate_raw)
                            bid_rate = bid_rate / 100 if bid_rate > 1.5 else bid_rate
                        except (ValueError, TypeError):
                            skipped += 1
                            continue
                        if bid_rate <= 0 or bid_rate > 1.5:
                            skipped += 1
                            continue

                        winner_name = (item.get("bidwinnrNm") or "").strip()
                        winner_biz  = (item.get("bidwinnrBizno") or "").strip() or None
                        if not winner_name:
                            skipped += 1
                            continue

                        def _si(v):
                            try: return int(str(v).replace(",", ""))
                            except: return None

                        bid_amount   = _si(item.get("sucsfbidAmt"))
                        part_count   = _si(item.get("prtcptCnum"))
                        open_dt_str  = item.get("rlOpengDt") or item.get("fnlSucsfDate")
                        open_dt      = _parse_datetime(open_dt_str)
                        if bid_amount and bid_rate > 0:
                            est_base = round(bid_amount / bid_rate)
                        else:
                            est_base = 0

                        agency_name = (item.get("dminsttNm") or "").strip()
                        agency_code = (item.get("dminsttCd") or "").strip() or None
                        if not agency_name:
                            skipped += 1
                            continue

                        # savepoint — 실패 시 이 항목만 롤백, 세션 유지
                        sp = db.begin_nested()
                        try:
                            agency = _upsert_agency_by_code(db, agency_code, agency_name)

                            bid = db.query(Bid).filter(Bid.announcement_no == ano).first()
                            if bid:
                                if (bid.base_amount or 0) == 0 and est_base > 0:
                                    bid.base_amount = est_base
                                if bid.participant_count is None and part_count:
                                    bid.participant_count = part_count
                                if bid.bid_open_date is None and open_dt:
                                    bid.bid_open_date = open_dt
                                updated_bids += 1
                            else:
                                title = (item.get("bidNtceNm") or "").strip()
                                industry_id = _infer_industry_from_title(db, title)
                                bid = Bid(
                                    announcement_no=ano,
                                    title=title,
                                    agency_id=agency.id,
                                    industry_id=industry_id,
                                    base_amount=est_base,
                                    bid_open_date=open_dt,
                                    participant_count=part_count,
                                    status="closed",
                                    source="g2b",
                                )
                                db.add(bid)
                                db.flush()
                                inserted_bids += 1

                            competitor = _upsert_competitor(db, winner_name, winner_biz)
                            existing_result = (
                                db.query(BidResult)
                                .filter(BidResult.bid_id == bid.id, BidResult.competitor_id == competitor.id)
                                .first()
                            )
                            if not existing_result:
                                db.add(BidResult(
                                    bid_id=bid.id,
                                    competitor_id=competitor.id,
                                    bid_amount=bid_amount or 0,
                                    bid_rate=bid_rate,
                                    rank=1,
                                    is_winner=True,
                                ))
                                inserted_results += 1
                            sp.commit()
                        except Exception as sp_exc:
                            sp.rollback()
                            raise sp_exc

                    except Exception as exc:
                        fail += 1
                        logger.debug("백필 항목 실패 {}: {}", ano, exc)
                        continue

                db.commit()

        except Exception as exc:
            db.rollback()
            fail += 1
            logger.warning("백필 월 {} 실패: {}", label, exc)

        # 다음 월로 이동
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)

    elapsed = time.monotonic() - t0
    logger.info(
        "역사 데이터 백필 완료: new_bids={} updated={} new_results={} skipped={} fail={} ({:.1f}s)",
        inserted_bids, updated_bids, inserted_results, skipped, fail, elapsed,
    )
    return {
        "inserted_bids": inserted_bids,
        "updated_bids": updated_bids,
        "inserted_results": inserted_results,
        "skipped": skipped,
        "fail": fail,
        "elapsed_s": round(elapsed, 1),
    }


# ================================================================== #
# Phase 2: 사전규격 수집 (HrcspSsstndrdInfoService)                   #
# ================================================================== #

def collect_pre_spec_notices(db: Session, days_back: int = 1) -> dict:
    """
    사전규격 공사 목록 수집 (getPublicPrcureThngInfoCnstwk).

    등록일시 기준 days_back일 범위 조회 → pre_spec_notices 테이블 upsert.
    수집 후 기관명 기반으로 bids 테이블과 자동 매핑.
    """
    from app.config import get_settings
    from sqlalchemy import text as _t
    from datetime import datetime, timedelta, timezone
    import json as _json

    settings = get_settings()
    client = NarajangterClient(api_key=settings.g2b_api_key)

    now = datetime.now(timezone.utc) + timedelta(hours=9)  # KST
    bgn_dt = (now - timedelta(days=days_back)).strftime("%Y%m%d%H%M")
    end_dt = now.strftime("%Y%m%d%H%M")

    inserted = fail = 0
    t0 = time.monotonic()

    def _si(v):
        try: return int(str(v).replace(",", ""))
        except: return None

    def _parse_dt(v):
        if not v: return None
        s = str(v).strip().rstrip("Z")
        for fmt, n in (
            ("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%dT%H:%M:%S", 19),
            ("%Y%m%d%H%M%S", 14), ("%Y%m%d%H%M", 12),
            ("%Y-%m-%d", 10), ("%Y%m%d", 8),
        ):
            try:
                dt = datetime.strptime(s[:n], fmt)
                return dt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                pass
        return None

    try:
        for items in client.paginate_pre_spec(bgn_dt, end_dt, inqry_div=1):
            for item in items:
                pre_spec_no = (
                    item.get("bfSpecRgstNo") or item.get("prcrmntReqNo") or ""
                )
                if not pre_spec_no:
                    continue
                try:
                    doc_files = []
                    for fk in ("atchFileDwnldUrl", "fileUrl", "rltnDocRgstNo"):
                        v = item.get(fk)
                        if v:
                            doc_files.append({"url": str(v), "key": fk})

                    db.execute(_t("""
                        INSERT INTO pre_spec_notices
                            (pre_spec_no, title, order_agency, demand_agency,
                             estimated_amount, industry_name, reg_date, changed_date,
                             end_date, doc_files, source_data)
                        VALUES
                            (:no, :title, :order_ag, :demand_ag,
                             :est, :industry, :reg_dt, :chg_dt,
                             :end_dt, CAST(:docs AS jsonb), CAST(:src AS jsonb))
                        ON CONFLICT (pre_spec_no) DO UPDATE SET
                            title            = EXCLUDED.title,
                            order_agency     = EXCLUDED.order_agency,
                            demand_agency    = EXCLUDED.demand_agency,
                            estimated_amount = EXCLUDED.estimated_amount,
                            industry_name    = EXCLUDED.industry_name,
                            reg_date         = COALESCE(EXCLUDED.reg_date, pre_spec_notices.reg_date),
                            changed_date     = EXCLUDED.changed_date,
                            end_date         = EXCLUDED.end_date,
                            doc_files        = EXCLUDED.doc_files,
                            source_data      = EXCLUDED.source_data,
                            updated_at       = NOW()
                    """), {
                        "no":        pre_spec_no,
                        "title":     item.get("prdctClsfcNoNm") or item.get("bfSpecTitle") or item.get("prdctNm") or "",
                        "order_ag":  item.get("ntceInsttNm") or item.get("orderInsttNm") or item.get("bidNtceInstNm"),
                        "demand_ag": item.get("rlDminsttNm") or item.get("dminsttNm"),
                        "est":       _si(item.get("presmptPrce") or item.get("asignBdgtAmt")),
                        "industry":  item.get("indutyNm") or item.get("prdctClsfcNoNm"),
                        "reg_dt":    _parse_dt(item.get("rgstDt") or item.get("bfSpecRgstDt") or item.get("registDt")),
                        "chg_dt":    _parse_dt(item.get("chgDt") or item.get("bfSpecChngDt")),
                        "end_dt":    _parse_dt(item.get("opninRgstClseDt") or item.get("opninRcptDt") or item.get("pubPurpDt")),
                        "docs":      _json.dumps(doc_files),
                        "src":       _json.dumps(item, ensure_ascii=False, default=str),
                    })
                    inserted += 1
                except Exception as exc:
                    fail += 1
                    logger.warning("사전규격 upsert 실패 {}: {}", pre_spec_no, exc)

            try:
                db.commit()
            except Exception as exc:
                db.rollback()
                logger.warning("사전규격 배치 커밋 실패: {}", exc)

    except Exception as exc:
        logger.error("사전규격 수집 실패 (API 오류 포함): {}", exc)

    # 공고 매핑: 기관명 기반
    try:
        matched = db.execute(_t("""
            UPDATE pre_spec_notices ps
            SET bid_announcement_no = b.announcement_no,
                bid_id = b.id,
                matched_at = NOW()
            FROM bids b
            JOIN agencies a ON a.id = b.agency_id
            WHERE (a.name = ps.order_agency OR a.name LIKE '%' || ps.order_agency || '%')
              AND b.notice_date >= (ps.reg_date::date - INTERVAL '14 days')
              AND b.notice_date <= (ps.reg_date::date + INTERVAL '90 days')
              AND ps.bid_id IS NULL
              AND ps.order_agency IS NOT NULL
        """)).rowcount
        db.commit()
        logger.info("사전규격→공고 매핑: {}건", matched)
    except Exception as exc:
        db.rollback()
        logger.warning("사전규격 공고 매핑 실패: {}", exc)

    elapsed = time.monotonic() - t0
    logger.info("사전규격 수집 완료: upsert={} fail={} ({:.1f}s)", inserted, fail, elapsed)
    return {"upserted": inserted, "fail": fail, "elapsed_s": round(elapsed, 1)}


def match_pre_spec_to_bids(db: Session) -> dict:
    """사전규격 → 공고 매핑 재실행 (정오 스케줄러에서 호출)."""
    from sqlalchemy import text as _t

    try:
        matched = db.execute(_t("""
            UPDATE pre_spec_notices ps
            SET bid_announcement_no = b.announcement_no,
                bid_id = b.id,
                matched_at = NOW()
            FROM bids b
            JOIN agencies a ON a.id = b.agency_id
            WHERE (
                a.name = ps.order_agency
                OR a.name LIKE '%' || ps.order_agency || '%'
                OR ps.order_agency LIKE '%' || a.name || '%'
            )
              AND b.notice_date >= (ps.reg_date::date - INTERVAL '14 days')
              AND b.notice_date <= (ps.reg_date::date + INTERVAL '90 days')
              AND ps.bid_id IS NULL
              AND ps.order_agency IS NOT NULL
              AND ps.reg_date >= NOW() - INTERVAL '6 months'
        """)).rowcount
        db.commit()
        logger.info("사전규격 공고 매핑 완료: {}건", matched)
        return {"matched": matched}
    except Exception as exc:
        db.rollback()
        logger.error("사전규격 공고 매핑 실패: {}", exc)
        return {"matched": 0, "error": str(exc)}


# ================================================================== #
# Phase 3: 계약정보 수집 (CntrctInfoService)                          #
# ================================================================== #

def collect_bid_contracts(db: Session, days_back: int = 1) -> dict:
    """
    나라장터 계약현황 공사 수집 (getCntrctInfoListCnstwkPPSSrch).

    계약체결일 기준 days_back일 범위 조회 → bid_contracts 테이블 upsert.
    공고번호로 bids.id 자동 매핑.
    """
    from app.config import get_settings
    from sqlalchemy import text as _t
    from datetime import datetime, timedelta, timezone
    import json as _json

    settings = get_settings()
    client = NarajangterClient(api_key=settings.g2b_api_key)

    now = datetime.now(timezone.utc) + timedelta(hours=9)  # KST
    bgn_date = (now - timedelta(days=days_back)).strftime("%Y%m%d")
    end_date = now.strftime("%Y%m%d")

    inserted = fail = 0
    t0 = time.monotonic()

    def _si(v):
        try: return int(str(v).replace(",", ""))
        except: return None

    def _parse_date(v):
        if not v: return None
        s = str(v).strip()
        for fmt, n in (("%Y-%m-%d", 10), ("%Y%m%d", 8)):
            try: return datetime.strptime(s[:n], fmt).date()
            except: pass
        return None

    def _parse_corp_list(v):
        """corpList 문자열 파싱.
        형식: [seq^role^type^corpNm^ofclNm^nation^share^corpNm2^empty^bizRegNo]
        bizRegNo는 index 9 (10번째 필드).
        """
        if not v: return []
        if isinstance(v, list): return v
        s = str(v).strip().lstrip("[").rstrip("]")
        if not s: return []
        items = []
        for seg in s.split("],["):
            parts = seg.split("^")
            if len(parts) >= 4:
                biz = parts[9].strip() if len(parts) > 9 else ""
                items.append({
                    "seq": parts[0], "role": parts[1], "type": parts[2],
                    "corpNm": parts[3],
                    "bizRegNo": biz if biz else None,
                })
        return items

    try:
        for items in client.paginate_contracts(bgn_date, end_date, inqry_div=1):
            for item in items:
                unty_no = item.get("untyCntrctNo") or item.get("cntrctNo", "")
                if not unty_no:
                    continue

                ntce_no = item.get("ntceNo") or item.get("bidNtceNo") or ""
                company_list = item.get("bizList") or item.get("cmpnyList") or []
                if isinstance(company_list, dict):
                    company_list = [company_list]
                demand_agencies = item.get("dminsttList") or item.get("rlDminsttList") or []
                if isinstance(demand_agencies, dict):
                    demand_agencies = [demand_agencies]

                try:
                    corp_list = _parse_corp_list(
                        item.get("corpList") or item.get("bizList") or item.get("cmpnyList") or []
                    )
                    db.execute(_t("""
                        INSERT INTO bid_contracts
                            (unty_cntrct_no, dcsn_cntrct_no, announcement_no,
                             contract_name, agency_code, agency_name,
                             total_amount, this_amount, contract_date,
                             start_date, completion_date, final_completion_date,
                             joint_contract, long_term_div, contract_method,
                             company_list, demand_agencies, source_data)
                        VALUES
                            (:unty, :dcsn, :ntce,
                             :name, :ag_code, :ag_name,
                             :total, :this_amt, :cdate,
                             :sdate, :compdate, :fcompdate,
                             :joint, :longterm, :method,
                             CAST(:companies AS jsonb), CAST(:demands AS jsonb), CAST(:src AS jsonb))
                        ON CONFLICT (unty_cntrct_no) DO UPDATE SET
                            contract_name         = EXCLUDED.contract_name,
                            announcement_no       = COALESCE(EXCLUDED.announcement_no, bid_contracts.announcement_no),
                            total_amount          = EXCLUDED.total_amount,
                            this_amount           = EXCLUDED.this_amount,
                            contract_date         = EXCLUDED.contract_date,
                            start_date            = EXCLUDED.start_date,
                            completion_date       = EXCLUDED.completion_date,
                            final_completion_date = EXCLUDED.final_completion_date,
                            joint_contract        = EXCLUDED.joint_contract,
                            contract_method       = EXCLUDED.contract_method,
                            company_list          = EXCLUDED.company_list,
                            demand_agencies       = EXCLUDED.demand_agencies,
                            source_data           = EXCLUDED.source_data,
                            updated_at            = NOW()
                    """), {
                        "unty":      unty_no,
                        "dcsn":      item.get("dcsnCntrctNo"),
                        "ntce":      ntce_no,
                        "name":      item.get("cnstwkNm") or item.get("cntrctNm") or item.get("bidNtceNm") or "",
                        "ag_code":   item.get("cntrctInsttCd") or item.get("instCd"),
                        "ag_name":   item.get("cntrctInsttNm") or item.get("instNm"),
                        "total":     _si(item.get("totCntrctAmt") or item.get("ttlCntrctAmt")),
                        "this_amt":  _si(item.get("thtmCntrctAmt") or item.get("thisCntrctAmt") or item.get("cntrctAmt")),
                        "cdate":     _parse_date(item.get("cntrctDate") or item.get("cntrctCnclsDate") or item.get("cntrctCnclsDt")),
                        "sdate":     _parse_date(item.get("cbgnDate") or item.get("strtDt") or item.get("cnstwkBgngDt")),
                        "compdate":  _parse_date(item.get("thtmCcmpltDate") or item.get("thisCmptnDt") or item.get("cmptnDt")),
                        "fcompdate": _parse_date(item.get("ttalCcmpltDate") or item.get("totCmptnDt")),
                        "joint":     item.get("cmmnCntrctYn") or item.get("jntContrYn") or item.get("cmmnSpldmdAgrmntYn"),
                        "longterm":  item.get("lngtrmCtnuDivNm") or item.get("lttrmCntnDivNm"),
                        "method":    item.get("cntrctCnclsMthdNm") or item.get("cntrctMthdNm"),
                        "companies": _json.dumps(corp_list, ensure_ascii=False, default=str),
                        "demands":   _json.dumps(demand_agencies if isinstance(demand_agencies, list) else [], ensure_ascii=False, default=str),
                        "src":       _json.dumps(item, ensure_ascii=False, default=str),
                    })
                    inserted += 1
                except Exception as exc:
                    fail += 1
                    logger.warning("계약정보 upsert 실패 {}: {}", unty_no, exc)

            try:
                db.commit()
            except Exception as exc:
                db.rollback()
                logger.warning("계약정보 배치 커밋 실패: {}", exc)

    except Exception as exc:
        logger.error("계약정보 수집 실패 (API 오류 포함): {}", exc)

    # bid_id 자동 매핑
    try:
        bid_mapped = db.execute(_t("""
            UPDATE bid_contracts bc
            SET bid_id = b.id
            FROM bids b
            WHERE b.announcement_no = bc.announcement_no
              AND bc.bid_id IS NULL
              AND bc.announcement_no != ''
        """)).rowcount
        db.commit()
        logger.info("계약정보→bids 매핑: {}건", bid_mapped)
    except Exception as exc:
        db.rollback()
        logger.warning("계약정보 bids 매핑 실패: {}", exc)

    elapsed = time.monotonic() - t0
    logger.info("계약정보 수집 완료: upsert={} fail={} ({:.1f}s)", inserted, fail, elapsed)
    return {"upserted": inserted, "fail": fail, "elapsed_s": round(elapsed, 1)}

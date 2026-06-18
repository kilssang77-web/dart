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

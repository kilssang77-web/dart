"""
데이터 수집 스케줄러 — 나라장터 공사 입찰 공고 + 개찰결과 수집 및 DB 저장.
"""
import os
import hashlib
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s — %(message)s",
)
logger = logging.getLogger(__name__)

DATABASE_URL    = os.getenv("DATABASE_URL", "")
G2B_API_KEY     = os.getenv("G2B_API_KEY", "")
COLLECT_ENABLED = os.getenv("COLLECT_ENABLED", "false").lower() == "true"

# 나라장터 낙찰정보서비스 (별도 승인 필요)
G2B_RESULT_BASE = "https://apis.data.go.kr/1230000/as/ScsbidInfoService"

engine    = create_engine(DATABASE_URL, pool_pre_ping=True) if DATABASE_URL else None
MkSession = sessionmaker(bind=engine) if engine else None


REGION_MAP = {
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시",
    "인천": "인천광역시", "광주": "광주광역시", "대전": "대전광역시",
    "울산": "울산광역시", "세종": "세종특별자치시", "경기": "경기도",
    "강원": "강원특별자치도", "충북": "충청북도", "충남": "충청남도",
    "전북": "전북특별자치도", "전남": "전라남도", "경북": "경상북도",
    "경남": "경상남도", "제주": "제주특별자치도",
}

# 기관명 → 지역 키워드 매핑 (더 구체적인 키워드를 앞에 배치)
AGENCY_REGION_KEYWORDS: list[tuple[str, int]] = [
    ("경상북도", 15), ("경상남도", 16),
    ("충청북도", 11), ("충청남도", 12),
    ("전라북도", 13), ("전북특별자치도", 13), ("전라남도", 14),
    ("강원특별자치도", 10), ("강원도", 10),
    ("서울특별시", 1), ("서울", 1),
    ("부산광역시", 2), ("부산", 2),
    ("대구광역시", 3), ("대구", 3),
    ("인천광역시", 4), ("인천", 4),
    ("광주광역시", 5),
    ("대전광역시", 6), ("대전", 6),
    ("울산광역시", 7), ("울산", 7),
    ("세종특별자치시", 8), ("세종", 8),
    ("경기도", 9), ("경기", 9),
    ("충북", 11), ("충남", 12),
    ("전북", 13), ("전남", 14),
    ("경북", 15), ("경남", 16),
    ("제주특별자치도", 17), ("제주", 17),
    ("강원", 10),
    ("광주", 5),
]

# 캐시: 반복 DB 조회 방지
_agency_cache: dict[str, int] = {}
_industry_cache: dict[str, int | None] = {}
_agency_region_cache: dict[str, int | None] = {}


def _extract_region_from_name(name: str) -> int | None:
    """기관명 키워드로 지역 ID를 추출한다."""
    if not name:
        return None
    if name in _agency_region_cache:
        return _agency_region_cache[name]
    for keyword, region_id in AGENCY_REGION_KEYWORDS:
        if keyword in name:
            _agency_region_cache[name] = region_id
            return region_id
    _agency_region_cache[name] = None
    return None


def _resolve_region(db: Session, api_item: dict, agency_name: str | None = None) -> int | None:
    for key in ("incntvRgnNm1", "incntvRgnNm2", "incntvRgnNm3"):
        raw = (api_item.get(key) or "").strip()
        if not raw:
            continue
        for prefix, full in REGION_MAP.items():
            if prefix in raw:
                row = db.execute(text("SELECT id FROM regions WHERE name=:n LIMIT 1"), {"n": full}).fetchone()
                if row:
                    return row[0]
    return _extract_region_from_name(agency_name) if agency_name else None


def _resolve_agency(db: Session, name: str) -> int:
    name = (name or "").strip() or "기타"
    if name in _agency_cache:
        return _agency_cache[name]
    row = db.execute(text("SELECT id FROM agencies WHERE name=:n LIMIT 1"), {"n": name}).fetchone()
    if row:
        _agency_cache[name] = row[0]
        return row[0]
    try:
        result = db.execute(
            text("INSERT INTO agencies (name) VALUES (:n) ON CONFLICT (name) DO UPDATE SET name=EXCLUDED.name RETURNING id"),
            {"n": name},
        )
        db.commit()
        aid = result.fetchone()[0]
        _agency_cache[name] = aid
        return aid
    except Exception:
        db.rollback()
        row = db.execute(text("SELECT id FROM agencies WHERE name=:n LIMIT 1"), {"n": name}).fetchone()
        return row[0] if row else 1


def _resolve_industry(db: Session, name: str) -> int | None:
    name = (name or "").strip()
    if not name:
        return None
    if name in _industry_cache:
        return _industry_cache[name]
    row = db.execute(text("SELECT id FROM industries WHERE name=:n LIMIT 1"), {"n": name}).fetchone()
    if row:
        _industry_cache[name] = row[0]
        return row[0]
    code = hashlib.md5(name.encode()).hexdigest()[:20]
    try:
        result = db.execute(
            text("INSERT INTO industries (code, name) VALUES (:c, :n) ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name RETURNING id"),
            {"c": code, "n": name},
        )
        db.commit()
        iid = result.fetchone()[0]
        _industry_cache[name] = iid
        return iid
    except Exception:
        db.rollback()
        return None


def _parse_amount(val) -> int | None:
    try:
        v = int(str(val).replace(",", "").strip())
        return v if v > 1 else None
    except Exception:
        return None


def _parse_dt(val: str | None) -> datetime | None:
    if not val:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y%m%d%H%M"):
        try:
            return datetime.strptime(val.strip(), fmt)
        except Exception:
            continue
    return None


def _parse_bid_close_date(date_str: str | None, time_str: str | None) -> datetime | None:
    """'20251130' + '1100' -> datetime(2025,11,30,11,0)"""
    if not date_str:
        return None
    try:
        d = date_str.strip()
        t = (time_str or "0000").strip().zfill(4)
        combined = d + t
        return datetime.strptime(combined, "%Y%m%d%H%M")
    except Exception:
        return None

def save_notices_to_db(db: Session, items: list[dict]) -> int:
    """API 공고 목록을 DB에 upsert. 저장된 건수 반환."""
    saved = 0
    for item in items:
        bid_no = (item.get("bidNtceNo") or "").strip()
        if not bid_no:
            continue
        try:
            amount       = _parse_amount(item.get("bdgtAmt")) or _parse_amount(item.get("presmptPrce")) or 0
            est_price    = _parse_amount(item.get("presmptPrce"))
            a_value      = _parse_amount(item.get("bssamt"))
            agency_name  = item.get("dminsttNm") or item.get("ntceInsttNm") or "기타"
            ind_name     = (item.get("mainCnsttyNm") or "").strip()

            agency_id    = _resolve_agency(db, agency_name)
            industry_id  = _resolve_industry(db, ind_name) if ind_name else None
            region_id    = _resolve_region(db, item, agency_name)

            # 신규 필드 파싱
            construction_site = (item.get("cnstwkPlce") or "")[:500] or None
            contract_method   = (item.get("cntrctCnclsMthdNm") or "")[:100] or None
            bid_method        = (item.get("bidMethdNm") or "")[:100] or None
            eligible_regions  = (item.get("prtcptPsblRgnNm") or item.get("prtcptLmtRgnCd") or "")[:500] or None
            industry_limit    = (item.get("cmpnArNm") or "")[:500] or None
            bid_close_date    = _parse_bid_close_date(item.get("bidClseDate"), item.get("bidClseTm"))
            contact_name      = (item.get("ntceInsttOfclNm") or "")[:100] or None
            contact_tel       = (item.get("ntceInsttOfclTelNo") or "")[:50] or None
            construction_period = None
            cp_raw = item.get("cnstwkPrdicPd")
            if cp_raw:
                try:
                    construction_period = int(cp_raw)
                except Exception:
                    pass
            try:
                floor_rate = float(item.get("sucsfbidLwltRate") or 0) / 100
            except Exception:
                floor_rate = 0.0
            if floor_rate < 0.8 or floor_rate > 1.0:
                floor_rate = 0.8775

            db.execute(text("""
                INSERT INTO bids
                    (announcement_no, title, agency_id, industry_id, region_id,
                     base_amount, estimated_price, a_value, min_bid_rate,
                     notice_date, bid_open_date, construction_period,
                     region_restriction, status, source, ntce_url,
                     construction_site, contract_method, bid_method,
                     eligible_regions, industry_limit, bid_close_date,
                     contact_name, contact_tel)
                VALUES
                    (:ano, :title, :agency, :ind, :reg,
                     :amt, :est, :aval, :frate,
                     :ndt, :odt, :cp,
                     :rlmt, 'open', 'g2b', :url,
                     :csite, :cmth, :bmth,
                     :eregs, :ilmt, :bclose,
                     :cname, :ctel)
                ON CONFLICT (announcement_no) DO UPDATE SET
                    title             = EXCLUDED.title,
                    agency_id         = EXCLUDED.agency_id,
                    industry_id       = COALESCE(EXCLUDED.industry_id, bids.industry_id),
                    region_id         = COALESCE(EXCLUDED.region_id, bids.region_id),
                    base_amount       = CASE WHEN EXCLUDED.base_amount > 1 THEN EXCLUDED.base_amount ELSE bids.base_amount END,
                    estimated_price   = COALESCE(EXCLUDED.estimated_price, bids.estimated_price),
                    a_value           = COALESCE(EXCLUDED.a_value, bids.a_value),
                    bid_open_date     = COALESCE(EXCLUDED.bid_open_date, bids.bid_open_date),
                    construction_period = COALESCE(EXCLUDED.construction_period, bids.construction_period),
                    ntce_url          = COALESCE(EXCLUDED.ntce_url, bids.ntce_url),
                    construction_site = COALESCE(EXCLUDED.construction_site, bids.construction_site),
                    contract_method   = COALESCE(EXCLUDED.contract_method, bids.contract_method),
                    bid_method        = COALESCE(EXCLUDED.bid_method, bids.bid_method),
                    eligible_regions  = COALESCE(EXCLUDED.eligible_regions, bids.eligible_regions),
                    industry_limit    = COALESCE(EXCLUDED.industry_limit, bids.industry_limit),
                    bid_close_date    = COALESCE(EXCLUDED.bid_close_date, bids.bid_close_date),
                    contact_name      = COALESCE(EXCLUDED.contact_name, bids.contact_name),
                    contact_tel       = COALESCE(EXCLUDED.contact_tel, bids.contact_tel),
                    updated_at        = NOW()
            """), {
                "ano":    bid_no,
                "title":  (item.get("bidNtceNm") or "")[:500],
                "agency": agency_id,
                "ind":    industry_id,
                "reg":    region_id,
                "amt":    amount,
                "est":    est_price,
                "aval":   a_value,
                "frate":  floor_rate,
                "ndt":    _parse_dt(item.get("bidNtceDt")),
                "odt":    _parse_dt(item.get("opengDt")),
                "cp":     construction_period,
                "rlmt":   (item.get("cmmnSpldmdCorpRgnLmtYn") or "N").upper() == "Y",
                "url":    (item.get("bidNtceDtlUrl") or "")[:500] or None,
                "csite":  construction_site,
                "cmth":   contract_method,
                "bmth":   bid_method,
                "eregs":  eligible_regions,
                "ilmt":   industry_limit,
                "bclose": bid_close_date,
                "cname":  contact_name,
                "ctel":   contact_tel,
            })
            saved += 1
        except Exception as e:
            logger.debug(f"저장 실패 {bid_no}: {e}")
            db.rollback()
            continue

    db.commit()
    return saved

async def fetch_and_save(client, date_from: str, date_to: str) -> int:
    """한 날짜 범위의 데이터를 페이지 단위로 fetch & 증분 저장."""
    import asyncio

    total_saved = 0
    page = 1
    while True:
        try:
            data = await client._get("getBidPblancListInfoCnstwk", {
                "inqryBgnDt": date_from,
                "inqryEndDt": date_to,
                "inqryDiv":   1,
                "numOfRows":  100,
                "pageNo":     page,
            })
            body  = data.get("response", {}).get("body", {})
            items = body.get("items", [])
            if not items:
                break
            if isinstance(items, dict):
                items = [items]

            total_count = int(body.get("totalCount", 0))

            if MkSession:
                db = MkSession()
                try:
                    n = save_notices_to_db(db, items)
                    total_saved += n
                finally:
                    db.close()

            logger.info(f"수집 저장 {date_from[:8]}: 페이지 {page} -> {total_saved}건 저장 (전체 {total_count}건)")
            if page * 100 >= total_count:
                break
            page += 1
            await asyncio.sleep(0.3)
        except Exception as e:
            logger.error(f"수집 오류 (page {page}): {e}")
            break
    return total_saved


async def fetch_results_for_bid(client, bid_no: str) -> list[dict]:
    """단일 공고의 개찰결과를 조회. API 오류 시 빈 목록 반환."""
    try:
        data = await client._get("getBidPblancRsltListInfoCnstwk", {
            "bidNtceNo": bid_no,
            "numOfRows": 100,
            "pageNo":    1,
        })
        body  = data.get("response", {}).get("body", {})
        items = body.get("items", [])
        if not items:
            return []
        if isinstance(items, dict):
            items = [items]
        return items
    except Exception:
        return []


def save_results_to_db(db: Session, bid_id: int, announcement_no: str, items: list[dict]) -> int:
    """개찰결과를 bid_results 테이블에 저장."""
    if not items:
        return 0
    saved = 0
    for item in items:
        try:
            comp_name = (item.get("bidprcpNm") or item.get("sucsfbidnm") or "").strip()
            if not comp_name:
                continue

            bid_amount_raw = item.get("bidAmt") or item.get("sucsfbidamt") or 0
            bid_amount = _parse_amount(bid_amount_raw) or 0
            if bid_amount <= 0:
                continue

            bid_rate_raw = item.get("bidRat") or item.get("sucsfbidrat")
            if bid_rate_raw:
                try:
                    bid_rate = float(str(bid_rate_raw).replace("%","").strip()) / 100
                except Exception:
                    bid_rate = 0.0
            else:
                bid_rate = 0.0

            rank_raw = item.get("bidprcpOrd") or item.get("sucsfOrd") or 1
            try:
                rank = int(rank_raw)
            except Exception:
                rank = 1

            is_winner = str(item.get("sucsfYn") or item.get("bidprcpOrd") or "N").upper() in ("Y","1","01")

            _cr = db.execute(text("SELECT id FROM competitors WHERE name=:n LIMIT 1"), {"n": comp_name}).fetchone()
            if _cr:
                comp_id = _cr[0]
            else:
                comp_id = db.execute(text("INSERT INTO competitors (name) VALUES (:n) RETURNING id"), {"n": comp_name}).fetchone()[0]
                db.commit()

            db.execute(text("""
                INSERT INTO bid_results (bid_id, competitor_id, bid_amount, bid_rate, rank, is_winner)
                VALUES (:bid, :comp, :amt, :rate, :rank, :win)
                ON CONFLICT (bid_id, competitor_id) DO UPDATE SET
                    bid_amount = EXCLUDED.bid_amount,
                    bid_rate   = EXCLUDED.bid_rate,
                    rank       = EXCLUDED.rank,
                    is_winner  = EXCLUDED.is_winner
            """), {
                "bid":  bid_id,
                "comp": comp_id,
                "amt":  bid_amount,
                "rate": bid_rate,
                "rank": rank,
                "win":  is_winner,
            })
            saved += 1
        except Exception as e:
            logger.debug(f"결과 저장 실패: {e}")
            db.rollback()
            continue

    if saved > 0:
        db.execute(text("UPDATE bids SET status='closed' WHERE id=:id"), {"id": bid_id})
    db.commit()
    return saved


def collect_today():
    if not COLLECT_ENABLED or not G2B_API_KEY:
        return
    import asyncio
    from g2b_client import G2BApiClient

    today = datetime.now().strftime("%Y%m%d")
    logger.info(f"오늘 공고 수집: {today}")

    async def _run():
        client = G2BApiClient(G2B_API_KEY)
        n = await fetch_and_save(client, today + "0000", today + "2359")
        logger.info(f"오늘 수집 완료: {n}건 저장")
        await client.close()

    asyncio.run(_run())


def collect_history(days_back: int = 180):
    if not COLLECT_ENABLED or not G2B_API_KEY or not engine:
        return
    import asyncio
    from g2b_client import G2BApiClient

    total = 0
    end   = datetime.now()
    start = end - timedelta(days=days_back)

    async def _run_range(df: str, dt: str) -> int:
        client = G2BApiClient(G2B_API_KEY)
        n = await fetch_and_save(client, df, dt)
        await client.close()
        return n

    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=30), end)
        df = cursor.strftime("%Y%m%d") + "0000"
        dt = chunk_end.strftime("%Y%m%d") + "2359"
        logger.info(f"구간 수집: {df[:8]} ~ {dt[:8]}")
        n = asyncio.run(_run_range(df, dt))
        total += n
        cursor = chunk_end + timedelta(days=1)

    logger.info(f"과거 데이터 수집 완료: 총 {total}건")


async def fetch_results_scsbid(date_from: str, date_to: str) -> list[dict]:
    """낙찰정보서비스(getScsbidListSttusCnstwk)에서 날짜 범위 낙찰 결과 수집."""
    import httpx
    import asyncio as _asyncio
    all_items = []
    page = 1
    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            retries = 0
            while retries < 3:
                try:
                    params = {
                        "inqryDiv":   1,
                        "inqryBgnDt": date_from,
                        "inqryEndDt": date_to,
                        "numOfRows":  100,
                        "pageNo":     page,
                        "type":       "json",
                        "serviceKey": G2B_API_KEY,
                    }
                    resp = await client.get(f"{G2B_RESULT_BASE}/getScsbidListSttusCnstwk", params=params)
                    if resp.status_code == 429:
                        wait = 60 * (retries + 1)
                        logger.warning(f"  429 Rate Limit — {wait}초 대기 후 재시도 ({retries+1}/3)")
                        await _asyncio.sleep(wait)
                        retries += 1
                        continue
                    resp.raise_for_status()
                    body = resp.json().get("response", {}).get("body", {})
                    items = body.get("items", [])
                    if not items:
                        return all_items
                    if isinstance(items, dict):
                        items = [items]
                    all_items.extend(items)
                    total = int(body.get("totalCount", 0) or 0)
                    logger.info(f"  낙찰결과 페이지 {page}: {len(all_items)}/{total}건")
                    if page * 100 >= total:
                        return all_items
                    page += 1
                    await _asyncio.sleep(1.0)
                    break
                except Exception as e:
                    if retries < 2:
                        retries += 1
                        logger.warning(f"낙찰결과 수집 오류 (page {page}, retry {retries}): {e}")
                        await _asyncio.sleep(5)
                        continue
                    logger.warning(f"낙찰결과 수집 포기 (page {page}): {e}")
                    return all_items
            else:
                logger.warning(f"낙찰결과 수집 재시도 초과 (page {page}) — 청크 스킵")
                return all_items
    return all_items


def save_scsbid_to_db(db: Session, items: list[dict]) -> int:
    """낙찰정보서비스 결과를 bid_results에 저장. 낙찰자(winner=True) 1건씩.

    API 필드: bidwinnrNm(낙찰자), sucsfbidRate(낙찰율%), sucsfbidAmt(낙찰금액), prtcptCnum(참가자수)
    """
    saved = 0
    for item in items:
        bid_no = (item.get("bidNtceNo") or "").strip()
        if not bid_no:
            continue
        try:
            row = db.execute(
                text("SELECT id FROM bids WHERE announcement_no = :no LIMIT 1"),
                {"no": bid_no}
            ).fetchone()
            if not row:
                continue
            bid_id = row[0]

            comp_name = (item.get("bidwinnrNm") or "").strip()
            if not comp_name:
                continue

            bid_rate_raw = item.get("sucsfbidRate") or 0
            try:
                bid_rate = float(str(bid_rate_raw).replace("%", "").strip()) / 100
            except Exception:
                bid_rate = 0.0

            bid_amount = _parse_amount(item.get("sucsfbidAmt")) or 0

            try:
                participant_count = int(item.get("prtcptCnum") or 0)
            except Exception:
                participant_count = 0

            _cr = db.execute(text("SELECT id FROM competitors WHERE name=:n LIMIT 1"), {"n": comp_name}).fetchone()
            if _cr:
                comp_id = _cr[0]
            else:
                comp_id = db.execute(text("INSERT INTO competitors (name) VALUES (:n) RETURNING id"), {"n": comp_name}).fetchone()[0]
                db.commit()
            db.execute(text("""
                INSERT INTO bid_results (bid_id, competitor_id, bid_amount, bid_rate, rank, is_winner)
                VALUES (:bid, :comp, :amt, :rate, 1, true)
                ON CONFLICT (bid_id, competitor_id) DO UPDATE SET
                    bid_amount = EXCLUDED.bid_amount,
                    bid_rate   = EXCLUDED.bid_rate,
                    rank       = EXCLUDED.rank,
                    is_winner  = EXCLUDED.is_winner
            """), {"bid": bid_id, "comp": comp_id, "amt": bid_amount, "rate": bid_rate})

            db.execute(
                text("UPDATE bids SET status='closed', participant_count = CASE WHEN :pc > 0 THEN :pc ELSE participant_count END WHERE id=:id"),
                {"id": bid_id, "pc": participant_count}
            )
            saved += 1
        except Exception as e:
            logger.debug(f"낙찰결과 저장 실패 {bid_no}: {e}")
            db.rollback()
            continue

    db.commit()
    return saved

def collect_results(limit: int = 500):
    """낙찰결과 수집 — ScsbidInfoService 날짜 범위 기반 (최근 30일)."""
    if not COLLECT_ENABLED or not G2B_API_KEY or not engine:
        return
    import asyncio

    end = datetime.now()
    start = end - timedelta(days=30)
    date_from = start.strftime("%Y%m%d0000")
    date_to   = end.strftime("%Y%m%d2359")

    logger.info(f"=== 낙찰결과 수집 ({date_from} ~ {date_to}) ===")
    try:
        items = asyncio.run(fetch_results_scsbid(date_from, date_to))
    except Exception as e:
        logger.error(f"낙찰결과 API 오류: {e}")
        return

    if not items:
        logger.info("낙찰결과 없음 (API 빈 응답)")
        return

    db = MkSession()
    try:
        saved = save_scsbid_to_db(db, items)
        logger.info(f"개찰결과 수집 완료: 저장 {saved}건")
    except Exception as e:
        logger.error(f"낙찰결과 저장 오류: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    if COLLECT_ENABLED and G2B_API_KEY:
        logger.info("수집 스케줄러 시작 (실제 수집 모드)")

        if engine:
            with engine.connect() as conn:
                recent = conn.execute(text(
                    "SELECT COUNT(*) FROM bids WHERE source='g2b' AND created_at >= NOW() - INTERVAL '7 days'"
                )).scalar()
            if recent == 0:
                logger.info("최근 7일 G2B 데이터 없음 — 180일 과거 데이터 수집 시작...")
                collect_history(180)

        scheduler = BlockingScheduler()
        scheduler.add_job(collect_today,   CronTrigger(hour="9,15",  minute=0))
        scheduler.add_job(collect_results, CronTrigger(hour=18,      minute=30))
        scheduler.start()
    else:
        logger.info("수집기 대기 모드")
        import time
        while True:
            time.sleep(3600)





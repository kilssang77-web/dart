"""
임시(Raw) 스테이징 방식 데이터 수집기.

Stage 1: ScsbidInfoService 전체 수집 (공종 필터 없음) → scsbid_raw
Stage 2: G2B 웹사이트 크롤링으로 공사 낙찰결과 수집 → scsbid_raw + bid_results
Stage 3: scsbid_raw ↔ bids 매칭 → bid_results 추출

사용법:
  docker exec bid_collector python collect_raw.py             # 전체 (730일)
  docker exec bid_collector python collect_raw.py --days 365  # 1년치
  docker exec bid_collector python collect_raw.py --stage 1   # API 수집만
  docker exec bid_collector python collect_raw.py --stage 2   # G2B 크롤링만
  docker exec bid_collector python collect_raw.py --stage 3   # 매칭만
"""
import os, sys, asyncio, logging, json, argparse
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATABASE_URL        = os.getenv("DATABASE_URL", "")
G2B_API_KEY         = os.getenv("G2B_API_KEY", "")
G2B_SCSBID_BASE     = "https://apis.data.go.kr/1230000/as/ScsbidInfoService"
TARGET_INDUSTRY_IDS = [20, 24, 31]

if not DATABASE_URL or not G2B_API_KEY:
    logger.error("DATABASE_URL 또는 G2B_API_KEY 환경변수가 설정되지 않았습니다.")
    sys.exit(1)

engine    = create_engine(DATABASE_URL, pool_pre_ping=True)
MkSession = sessionmaker(bind=engine)


# ─────────────────────────────────────────────────────────────
# DB 초기화
# ─────────────────────────────────────────────────────────────

def ensure_raw_table():
    """scsbid_raw 테이블 및 인덱스 생성."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS scsbid_raw (
                id               BIGSERIAL    PRIMARY KEY,
                bid_ntce_no      VARCHAR(60)  NOT NULL,
                bid_ntce_seq     VARCHAR(10)  NOT NULL DEFAULT '00',
                sucsfbid_mbrt_nm VARCHAR(200),
                sucsfbid_rate    NUMERIC(8,4),
                sucsfbid_amt     BIGINT,
                main_cnstty_nm   VARCHAR(200),
                ntce_instt_nm    VARCHAR(200),
                openg_dt         TIMESTAMPTZ,
                source           VARCHAR(20)  DEFAULT 'api',
                raw_json         JSONB,
                collected_at     TIMESTAMPTZ  DEFAULT NOW(),
                CONSTRAINT uq_scsbid_raw UNIQUE (bid_ntce_no, bid_ntce_seq)
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_scsbid_raw_no     ON scsbid_raw(bid_ntce_no)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_scsbid_raw_cnstty ON scsbid_raw(main_cnstty_nm)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_scsbid_raw_dt     ON scsbid_raw(openg_dt)"))
        conn.commit()
    logger.info("scsbid_raw 테이블 준비 완료")


# ─────────────────────────────────────────────────────────────
# Stage 1: ScsbidInfoService 전체 수집
# ─────────────────────────────────────────────────────────────

def _save_raw_items(items: list[dict], source: str = "api") -> int:
    saved = 0
    db = MkSession()
    try:
        for item in items:
            bid_no = (item.get("bidNtceNo") or "").strip()
            if not bid_no:
                continue
            bid_seq = (item.get("bidNtceSeq") or "00").strip()

            rate_raw = item.get("sucsfbidRate") or 0
            try:
                rate = float(str(rate_raw).replace("%", "").strip()) / 100
                if rate <= 0 or rate > 2:
                    rate = None
            except Exception:
                rate = None

            amt_raw = item.get("sucsfbidAmt") or 0
            try:
                amt = int(str(amt_raw).replace(",", "").strip())
                amt = amt if amt > 0 else None
            except Exception:
                amt = None

            openg_dt = None
            for key in ("opengDt", "bidClseDt", "bidNtceDt"):
                raw_dt = (item.get(key) or "").strip()
                if not raw_dt:
                    continue
                for fmt in ("%Y%m%d%H%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                    try:
                        openg_dt = datetime.strptime(raw_dt, fmt)
                        break
                    except Exception:
                        continue
                if openg_dt:
                    break

            db.execute(text("""
                INSERT INTO scsbid_raw (
                    bid_ntce_no, bid_ntce_seq, sucsfbid_mbrt_nm,
                    sucsfbid_rate, sucsfbid_amt, main_cnstty_nm,
                    ntce_instt_nm, openg_dt, source, raw_json
                ) VALUES (
                    :no, :seq, :mbrt,
                    :rate, :amt, :cnstty,
                    :instt, :odt, :src, :rjson
                )
                ON CONFLICT (bid_ntce_no, bid_ntce_seq) DO UPDATE SET
                    sucsfbid_mbrt_nm = COALESCE(EXCLUDED.sucsfbid_mbrt_nm, scsbid_raw.sucsfbid_mbrt_nm),
                    sucsfbid_rate    = COALESCE(EXCLUDED.sucsfbid_rate,    scsbid_raw.sucsfbid_rate),
                    sucsfbid_amt     = COALESCE(EXCLUDED.sucsfbid_amt,     scsbid_raw.sucsfbid_amt),
                    main_cnstty_nm   = COALESCE(EXCLUDED.main_cnstty_nm,   scsbid_raw.main_cnstty_nm),
                    raw_json         = EXCLUDED.raw_json,
                    collected_at     = NOW()
            """), {
                "no":    bid_no,
                "seq":   bid_seq,
                "mbrt":  (item.get("sucsfbidMbrtNm") or "").strip() or None,
                "rate":  rate,
                "amt":   amt,
                "cnstty":(item.get("mainCnsttyNm") or "").strip() or None,
                "instt": (item.get("ntceInsttNm") or item.get("dminsttNm") or "").strip() or None,
                "odt":   openg_dt,
                "src":   source,
                "rjson": json.dumps(item, ensure_ascii=False),
            })
            saved += 1
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"raw 저장 오류: {e}")
    finally:
        db.close()
    return saved


async def stage1_collect_all_scsbid(days_back: int = 730):
    """ScsbidInfoService 전체 날짜범위 수집 (공종 필터 없음) → scsbid_raw."""
    import httpx

    end_dt   = datetime.now()
    start_dt = end_dt - timedelta(days=days_back)
    logger.info(f"Stage 1: ScsbidInfoService 전체 수집 {start_dt.date()} ~ {end_dt.date()}")

    total_recv  = 0
    total_saved = 0
    cursor = start_dt

    async with httpx.AsyncClient(timeout=30.0) as client:
        while cursor < end_dt:
            chunk_end = min(cursor + timedelta(days=30), end_dt)
            df = cursor.strftime("%Y%m%d") + "0000"
            dt = chunk_end.strftime("%Y%m%d") + "2359"
            page = 1
            chunk_items = True

            while chunk_items:
                retries = 0
                while retries < 3:
                    try:
                        resp = await client.get(
                            f"{G2B_SCSBID_BASE}/getScsbidListSttusCnstwk",
                            params={
                                "inqryDiv":   1,
                                "inqryBgnDt": df,
                                "inqryEndDt": dt,
                                "numOfRows":  100,
                                "pageNo":     page,
                                "type":       "json",
                                "serviceKey": G2B_API_KEY,
                            }
                        )
                        if resp.status_code == 429:
                            wait = 60 * (retries + 1)
                            logger.warning(f"  429 — {wait}초 대기 후 재시도")
                            await asyncio.sleep(wait)
                            retries += 1
                            continue
                        resp.raise_for_status()
                        body  = resp.json().get("response", {}).get("body", {})
                        items = body.get("items", [])
                        if not items:
                            chunk_items = False
                            break
                        if isinstance(items, dict):
                            items = [items]

                        total_recv  += len(items)
                        n = _save_raw_items(items, source="api")
                        total_saved += n

                        total_count = int(body.get("totalCount", 0) or 0)
                        logger.info(f"  {df[:8]}~{dt[:8]} p{page}: {len(items)}건 수신, {n}건 저장 (누적 {total_saved}건)")

                        if page * 100 >= total_count:
                            chunk_items = False
                        else:
                            page += 1
                        await asyncio.sleep(0.5)
                        break
                    except Exception as e:
                        retries += 1
                        if retries >= 3:
                            logger.warning(f"  {df[:8]} p{page} 오류 (포기): {e}")
                            chunk_items = False
                        else:
                            await asyncio.sleep(5)

            cursor = chunk_end + timedelta(days=1)
            await asyncio.sleep(2.0)

    logger.info(f"Stage 1 완료: 수신 {total_recv}건 → scsbid_raw 저장 {total_saved}건")
    return total_saved


# ─────────────────────────────────────────────────────────────
# Stage 2: G2B 웹사이트 크롤링
# ─────────────────────────────────────────────────────────────

async def _try_httpx_scrape(bid_no: str) -> list[dict]:
    """Playwright 없이 httpx만으로 G2B 페이지 시도 (서버사이드 렌더링 확인용)."""
    import httpx
    from html.parser import HTMLParser

    class TableParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_row   = False
            self.in_cell  = False
            self.rows: list[list[str]] = []
            self.cur_row: list[str]    = []
            self.cur_cell = ""

        def handle_starttag(self, tag, attrs):
            if tag == "tr":
                self.in_row  = True
                self.cur_row = []
            elif tag == "td" and self.in_row:
                self.in_cell  = True
                self.cur_cell = ""

        def handle_endtag(self, tag):
            if tag == "td" and self.in_cell:
                self.cur_row.append(self.cur_cell.strip())
                self.in_cell = False
            elif tag == "tr" and self.in_row:
                if self.cur_row:
                    self.rows.append(self.cur_row)
                self.in_row = False

        def handle_data(self, data):
            if self.in_cell:
                self.cur_cell += data

    urls_to_try = [
        f"https://www.g2b.go.kr/pps/cns/prd-modify/open-close-result?bidNo={bid_no}",
        f"https://www.g2b.go.kr:8081/ep/tbid/tbidResult.do?bidNo={bid_no}&bidSeq=00&bidNtceOrd=00",
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, verify=False) as client:
        for url in urls_to_try:
            try:
                resp = await client.get(url, headers=headers)
                if resp.status_code != 200:
                    continue
                html = resp.text
                if not any(kw in html for kw in ("낙찰", "개찰", "입찰참가")):
                    continue  # JS-only page — no useful content

                parser = TableParser()
                parser.feed(html)
                results = []
                for row in parser.rows:
                    if len(row) < 3:
                        continue
                    try:
                        rank     = int(row[0])
                        company  = row[1]
                        rate_txt = row[3] if len(row) > 3 else row[2]
                        rate     = float(rate_txt.replace("%", "").replace(",", "").strip()) / 100
                        winner   = any("낙찰" in c for c in row)
                        results.append({"rank": rank, "company": company, "rate": rate, "is_winner": winner})
                    except (ValueError, IndexError):
                        continue
                if results:
                    logger.info(f"    httpx 스크래핑 성공 {bid_no}: {len(results)}건")
                    return results
            except Exception:
                continue
    return []


async def stage2_crawl_g2b():
    """G2B 웹사이트 크롤링 — Playwright 우선, 없으면 httpx 폴백."""
    db = MkSession()
    try:
        target_rows = db.execute(text("""
            SELECT b.id, b.announcement_no
            FROM bids b
            LEFT JOIN bid_results r ON r.bid_id = b.id AND r.is_winner = true
            WHERE b.industry_id = ANY(:ids)
              AND r.bid_id IS NULL
              AND b.bid_open_date IS NOT NULL
              AND b.bid_open_date < NOW()
            ORDER BY b.bid_open_date DESC
            LIMIT 500
        """), {"ids": TARGET_INDUSTRY_IDS}).fetchall()
    finally:
        db.close()

    if not target_rows:
        logger.info("Stage 2: 크롤링 대상 없음")
        return 0

    logger.info(f"Stage 2: G2B 크롤링 대상 {len(target_rows)}건")

    # Playwright 사용 가능 여부 확인
    playwright_ok = False
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            await browser.close()
        playwright_ok = True
        logger.info("  Playwright 사용 가능 — 브라우저 렌더링 모드")
    except Exception as e:
        logger.warning(f"  Playwright 불가 ({e}) — httpx 폴백 모드")

    if playwright_ok:
        saved = await _crawl_with_playwright(target_rows)
    else:
        saved = await _crawl_with_httpx(target_rows)

    logger.info(f"Stage 2 완료: {saved}건 저장")
    return saved


async def _crawl_with_playwright(rows: list) -> int:
    import random
    from playwright.async_api import async_playwright

    saved = 0
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        for idx, (bid_id, bid_no) in enumerate(rows, 1):
            page = None
            try:
                page = await browser.new_page()
                await page.set_extra_http_headers({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124"
                })
                url = f"https://www.g2b.go.kr/pps/cns/prd-modify/open-close-result?bidNo={bid_no}"
                await page.goto(url, wait_until="networkidle", timeout=20_000)
                await asyncio.sleep(random.uniform(1, 2))

                result_rows = await page.query_selector_all("table tbody tr")
                results = []
                for row_el in result_rows:
                    cells = await row_el.query_selector_all("td")
                    if len(cells) < 3:
                        continue
                    try:
                        rank     = int((await cells[0].inner_text()).strip())
                        company  = (await cells[1].inner_text()).strip()
                        rate_txt = (await cells[3].inner_text()).strip() if len(cells) > 3 else (await cells[2].inner_text()).strip()
                        rate     = float(rate_txt.replace("%", "").strip()) / 100
                        winner   = any("낙찰" in (await c.inner_text()) for c in cells)
                        results.append({"rank": rank, "company": company, "rate": rate, "is_winner": winner})
                    except (ValueError, IndexError):
                        continue

                if results:
                    n = _save_crawled_results(bid_id, bid_no, results)
                    saved += n
                    if n > 0:
                        logger.info(f"  [{idx}/{len(rows)}] {bid_no}: {n}건 저장")

                if idx % 50 == 0:
                    logger.info(f"  진행 {idx}/{len(rows)} — 저장 {saved}건")
                await asyncio.sleep(1.5)
            except Exception as e:
                logger.debug(f"  {bid_no} 크롤링 실패: {e}")
            finally:
                if page:
                    try:
                        await page.close()
                    except Exception:
                        pass
        await browser.close()
    return saved


async def _crawl_with_httpx(rows: list) -> int:
    saved = 0
    for idx, (bid_id, bid_no) in enumerate(rows, 1):
        results = await _try_httpx_scrape(bid_no)
        if results:
            n = _save_crawled_results(bid_id, bid_no, results)
            saved += n
            if n > 0:
                logger.info(f"  [{idx}/{len(rows)}] {bid_no}: {n}건 저장")
        await asyncio.sleep(0.3)
        if idx % 100 == 0:
            logger.info(f"  진행 {idx}/{len(rows)} — 저장 {saved}건")
    return saved


def _save_crawled_results(bid_id: int, bid_no: str, results: list[dict]) -> int:
    saved = 0
    db = MkSession()
    try:
        for r in results:
            comp_name = (r.get("company") or "").strip()
            if not comp_name:
                continue
            rate      = r.get("rate") or 0.0
            rank      = r.get("rank") or 1
            is_winner = bool(r.get("is_winner", False))

            comp_row = db.execute(
                text("INSERT INTO competitors (name) VALUES (:n) ON CONFLICT (name) DO UPDATE SET name=EXCLUDED.name RETURNING id"),
                {"n": comp_name},
            ).fetchone()
            db.commit()
            comp_id = comp_row[0]

            db.execute(text("""
                INSERT INTO bid_results (bid_id, competitor_id, bid_amount, bid_rate, rank, is_winner)
                VALUES (:bid, :comp, 0, :rate, :rank, :win)
                ON CONFLICT (bid_id, competitor_id) DO UPDATE SET
                    bid_rate  = EXCLUDED.bid_rate,
                    rank      = EXCLUDED.rank,
                    is_winner = EXCLUDED.is_winner
            """), {"bid": bid_id, "comp": comp_id, "rate": rate, "rank": rank, "win": is_winner})

            # scsbid_raw에도 기록 (크롤링 출처)
            db.execute(text("""
                INSERT INTO scsbid_raw (bid_ntce_no, bid_ntce_seq, sucsfbid_mbrt_nm, sucsfbid_rate, source, raw_json)
                VALUES (:no, :seq, :mbrt, :rate, 'crawl', :rjson)
                ON CONFLICT (bid_ntce_no, bid_ntce_seq) DO UPDATE SET
                    sucsfbid_mbrt_nm = COALESCE(EXCLUDED.sucsfbid_mbrt_nm, scsbid_raw.sucsfbid_mbrt_nm),
                    sucsfbid_rate    = COALESCE(EXCLUDED.sucsfbid_rate,    scsbid_raw.sucsfbid_rate),
                    collected_at     = NOW()
            """), {
                "no":   bid_no,
                "seq":  str(rank).zfill(2),
                "mbrt": comp_name,
                "rate": rate,
                "rjson": json.dumps(r, ensure_ascii=False),
            })
            saved += 1

        if saved > 0:
            db.execute(text("UPDATE bids SET status='closed' WHERE id=:id"), {"id": bid_id})
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"크롤링 결과 저장 실패 {bid_no}: {e}")
    finally:
        db.close()
    return saved


# ─────────────────────────────────────────────────────────────
# Stage 3: scsbid_raw → bid_results 매칭 추출
# ─────────────────────────────────────────────────────────────

def stage3_match_and_extract() -> int:
    """scsbid_raw ↔ bids 매칭 후 bid_results에 낙찰자 정보 upsert."""
    db = MkSession()
    try:
        raw_count = db.execute(text("SELECT COUNT(*) FROM scsbid_raw WHERE source='api'")).scalar()
        logger.info(f"Stage 3: scsbid_raw(api) {raw_count}건 — 매칭 시도")

        if raw_count == 0:
            logger.warning("  scsbid_raw에 API 수집 데이터 없음 — Stage 1을 먼저 실행하세요")
            return 0

        # 대상 공종 매칭
        match_target = db.execute(text("""
            SELECT COUNT(DISTINCT r.bid_ntce_no)
            FROM scsbid_raw r
            JOIN bids b ON b.announcement_no = r.bid_ntce_no
            WHERE b.industry_id = ANY(:ids)
        """), {"ids": TARGET_INDUSTRY_IDS}).scalar()
        logger.info(f"  대상 공종(20/24/31) 매칭 공고: {match_target}건")

        # 전체 DB 매칭 (공종 무관)
        match_all = db.execute(text("""
            SELECT COUNT(DISTINCT r.bid_ntce_no)
            FROM scsbid_raw r
            JOIN bids b ON b.announcement_no = r.bid_ntce_no
        """)).scalar()
        logger.info(f"  전체 DB 매칭 공고: {match_all}건")

        if match_all == 0:
            sample_raw  = db.execute(text("SELECT bid_ntce_no, main_cnstty_nm FROM scsbid_raw LIMIT 5")).fetchall()
            sample_bids = db.execute(text(
                "SELECT announcement_no FROM bids WHERE industry_id = ANY(:ids) LIMIT 5"
            ), {"ids": TARGET_INDUSTRY_IDS}).fetchall()
            logger.warning("  scsbid_raw 공고번호 샘플 : " + str([r[0] for r in sample_raw]))
            logger.warning("  bids 공고번호 샘플      : " + str([r[0] for r in sample_bids]))
            logger.warning("  → 공고번호 형식 불일치. ScsbidInfoService가 대상 공종을 미제공하는 것으로 확인됨")
            return 0

        # bid_results upsert (낙찰자 1건/공고)
        saved = db.execute(text("""
            WITH matched AS (
                SELECT DISTINCT ON (b.id)
                    b.id               AS bid_id,
                    r.sucsfbid_mbrt_nm AS comp_name,
                    r.sucsfbid_rate,
                    COALESCE(r.sucsfbid_amt, 0) AS sucsfbid_amt
                FROM scsbid_raw r
                JOIN bids b ON b.announcement_no = r.bid_ntce_no
                WHERE r.sucsfbid_mbrt_nm IS NOT NULL
                  AND r.sucsfbid_rate    IS NOT NULL
                  AND r.source = 'api'
                ORDER BY b.id, r.collected_at DESC
            ),
            upsert_comp AS (
                INSERT INTO competitors (name)
                SELECT DISTINCT comp_name FROM matched
                ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                RETURNING id, name
            )
            INSERT INTO bid_results (bid_id, competitor_id, bid_amount, bid_rate, rank, is_winner)
            SELECT m.bid_id, c.id, m.sucsfbid_amt, m.sucsfbid_rate, 1, true
            FROM matched m
            JOIN upsert_comp c ON c.name = m.comp_name
            ON CONFLICT (bid_id, competitor_id) DO UPDATE SET
                bid_amount = EXCLUDED.bid_amount,
                bid_rate   = EXCLUDED.bid_rate,
                is_winner  = EXCLUDED.is_winner
        """)).rowcount

        db.execute(text("""
            UPDATE bids SET status='closed'
            WHERE announcement_no IN (
                SELECT DISTINCT bid_ntce_no FROM scsbid_raw WHERE source='api'
            )
            AND id IN (SELECT DISTINCT bid_id FROM bid_results)
        """))
        db.commit()
        logger.info(f"Stage 3 완료: bid_results {saved}건 추가/갱신")
        return saved
    except Exception as e:
        db.rollback()
        logger.error(f"Stage 3 오류: {e}")
        return 0
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────
# 통계 출력
# ─────────────────────────────────────────────────────────────

def print_stats():
    db = MkSession()
    try:
        stats = db.execute(text("""
            SELECT
                source,
                COUNT(*)                       AS total,
                COUNT(DISTINCT bid_ntce_no)    AS unique_bids,
                COUNT(DISTINCT main_cnstty_nm) AS unique_cnstty,
                MIN(openg_dt)::DATE            AS earliest,
                MAX(openg_dt)::DATE            AS latest
            FROM scsbid_raw
            GROUP BY source
        """)).fetchall()

        print("\n" + "=" * 65)
        print("scsbid_raw 수집 현황")
        print("=" * 65)
        if stats:
            for s in stats:
                print(f"  [{s[0]}] {s[1]:,}건 / 공고 {s[2]:,}건 / 공종 {s[3]}가지 / {s[4]}~{s[5]}")
        else:
            print("  (데이터 없음)")

        dist = db.execute(text("""
            SELECT COALESCE(main_cnstty_nm,'미분류') AS cnstty, COUNT(*) AS cnt
            FROM scsbid_raw
            WHERE source='api'
            GROUP BY main_cnstty_nm
            ORDER BY cnt DESC LIMIT 15
        """)).fetchall()
        if dist:
            print("\n  공종별 분포 (API 수집, 상위 15개):")
            for row in dist:
                print(f"    {row[0]}: {row[1]:,}건")

        results = db.execute(text("""
            SELECT i.name,
                   COUNT(DISTINCT b.id)     AS total_bids,
                   COUNT(DISTINCT r.bid_id) AS with_results
            FROM industries i
            LEFT JOIN bids b        ON b.industry_id = i.id
            LEFT JOIN bid_results r ON r.bid_id       = b.id
            WHERE i.id = ANY(:ids)
            GROUP BY i.id, i.name
        """), {"ids": TARGET_INDUSTRY_IDS}).fetchall()

        print("\n  대상 공종 낙찰결과 현황:")
        for r in results:
            pct = round(r[2] / r[1] * 100, 1) if r[1] > 0 else 0
            print(f"    {r[0]}: 공고 {r[1]:,}건, 결과보유 {r[2]:,}건 ({pct}%)")
        print("=" * 65 + "\n")
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="임시(Raw) 스테이징 데이터 수집기")
    parser.add_argument("--days",  type=int, default=730,
                        help="수집 기간 일수 (기본 730일=2년)")
    parser.add_argument("--stage", type=int, default=0,
                        help="0=전체 1=API수집 2=G2B크롤링 3=매칭추출")
    args = parser.parse_args()

    logger.info("=" * 65)
    logger.info("임시(Raw) 스테이징 데이터 수집기 시작")
    logger.info(f"수집 기간: 최근 {args.days}일  stage={args.stage or '전체'}")
    logger.info("=" * 65)

    ensure_raw_table()

    if args.stage in (0, 1):
        await stage1_collect_all_scsbid(args.days)
    if args.stage in (0, 2):
        await stage2_crawl_g2b()
    if args.stage in (0, 3):
        stage3_match_and_extract()

    print_stats()


if __name__ == "__main__":
    asyncio.run(main())

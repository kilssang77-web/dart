"""
활성 공종(실내건축, 도장, 금속창호) 전용 백필 스크립트.

실행 순서:
  1. PHASE 1  공고 소급 수집 (최대 past_days일) — 결과 매칭에 필요한 공고 먼저 확보
  2. PHASE 2  낙찰결과 수집 (날짜 범위별, getScsbidListSttusCnstwk inqryDiv=1)
  3. PHASE 3  최근 90일 결과 재수집 (누락분 보완)
  4. PHASE 4  개찰결과 공고번호별 조회 (getOpengResultListInfoCnstwkPPSSrch inqryDiv=3) ← 권장

사용법:
  docker exec bid_collector python backfill_active_industries.py
  docker exec bid_collector python backfill_active_industries.py --days 365
  docker exec bid_collector python backfill_active_industries.py --phase 4
  docker exec bid_collector python backfill_active_industries.py --phase 4 --daily-limit 1000
"""
import os, sys, asyncio, logging, argparse
from datetime import datetime, timedelta, date as dt_date
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")
G2B_API_KEY  = os.getenv("G2B_API_KEY", "")

if not DATABASE_URL or not G2B_API_KEY:
    logger.error("DATABASE_URL 또는 G2B_API_KEY 환경변수가 설정되지 않았습니다.")
    sys.exit(1)

engine    = create_engine(DATABASE_URL, pool_pre_ping=True)
MkSession = sessionmaker(bind=engine)

TARGET_INDUSTRY_IDS = [20, 24, 31]
G2B_RESULT_BASE     = "https://apis.data.go.kr/1230000/as/ScsbidInfoService"
OPENG_ENDPOINT      = "getOpengResultListInfoCnstwkPPSSrch"  # 개찰결과 — inqryDiv=3 동작 확인됨


def _to_datetime(val):
    """date/datetime 모두 datetime으로 통일."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, dt_date):
        return datetime.combine(val, datetime.min.time())
    return val


# ─────────────────────────────────────────────────────────────────────
# PHASE 1: 공고 소급 수집
# ─────────────────────────────────────────────────────────────────────
async def collect_notices_extended(past_days: int = 365):
    from g2b_client import G2BApiClient
    from main import fetch_and_save

    db = MkSession()
    try:
        row = db.execute(text(
            "SELECT MIN(notice_date) FROM bids WHERE source='g2b'"
        )).fetchone()
        earliest = _to_datetime(row[0]) if row else None
    finally:
        db.close()

    cutoff = datetime.now() - timedelta(days=past_days)

    if earliest and earliest <= cutoff:
        logger.info(f"PHASE 1: 이미 {cutoff.date()} 이전 데이터 존재 — 공고 소급 불필요")
        return 0

    end_dt   = (earliest - timedelta(days=1)) if earliest else datetime.now()
    start_dt = cutoff
    logger.info(f"PHASE 1: 공고 소급 수집 {start_dt.date()} ~ {end_dt.date()}")

    total = 0
    client = G2BApiClient(G2B_API_KEY)
    cursor = start_dt
    while cursor < end_dt:
        chunk_end = min(cursor + timedelta(days=30), end_dt)
        df = cursor.strftime("%Y%m%d") + "0000"
        dt = chunk_end.strftime("%Y%m%d") + "2359"
        logger.info(f"  공고 수집 구간: {df[:8]} ~ {dt[:8]}")
        n = await fetch_and_save(client, df, dt)
        total += n
        cursor = chunk_end + timedelta(days=1)
        await asyncio.sleep(1.0)

    await client.close()
    logger.info(f"PHASE 1 완료: 공고 {total}건 추가")
    return total


# ─────────────────────────────────────────────────────────────────────
# PHASE 2: 낙찰결과 날짜범위 수집 (getScsbidListSttusCnstwk inqryDiv=1)
# ─────────────────────────────────────────────────────────────────────
async def collect_scsbid_results(past_days: int = 365):
    from main import fetch_results_scsbid, save_scsbid_to_db

    end_dt   = datetime.now()
    start_dt = end_dt - timedelta(days=past_days)

    logger.info(f"PHASE 2: 낙찰결과(날짜범위) 수집 {start_dt.date()} ~ {end_dt.date()}")
    total_saved = 0
    cursor = start_dt

    while cursor < end_dt:
        chunk_end = min(cursor + timedelta(days=30), end_dt)
        df = cursor.strftime("%Y%m%d") + "0000"
        dt = chunk_end.strftime("%Y%m%d") + "2359"
        logger.info(f"  구간: {df[:8]} ~ {dt[:8]}")

        items = await fetch_results_scsbid(df, dt)
        if items:
            db = MkSession()
            try:
                n = save_scsbid_to_db(db, items)
                total_saved += n
                logger.info(f"    API {len(items)}건 수신 → DB 저장 {n}건")
            finally:
                db.close()
        else:
            logger.info(f"    수신 0건")

        cursor = chunk_end + timedelta(days=1)
        await asyncio.sleep(5.0)

    logger.info(f"PHASE 2 완료: 총 {total_saved}건 저장")
    return total_saved


# ─────────────────────────────────────────────────────────────────────
# PHASE 3: 최근 90일 재수집
# ─────────────────────────────────────────────────────────────────────
async def collect_scsbid_recent():
    logger.info("PHASE 3: 최근 90일 낙찰결과 재수집...")
    n = await collect_scsbid_results(past_days=90)
    logger.info(f"PHASE 3 완료: {n}건")
    return n


# ─────────────────────────────────────────────────────────────────────
# PHASE 4: 개찰결과 공고번호별 조회 (getOpengResultListInfoCnstwkPPSSrch)
# ─────────────────────────────────────────────────────────────────────

def _parse_openg_corp_info(openg_corp_info: str) -> dict | None:
    """opengCorpInfo 파싱: '업체명^사업자번호^대표자^투찰금액^투찰율'"""
    if not openg_corp_info:
        return None
    parts = openg_corp_info.split("^")
    if len(parts) < 5:
        return None
    try:
        return {
            "comp_name": parts[0].strip(),
            "biz_reg_no": parts[1].strip() if len(parts) > 1 else None,
            "bid_amt": int(str(parts[3]).replace(",", "").strip()) if len(parts) > 3 else 0,
            "bid_rate": float(parts[4].strip()) / 100.0 if len(parts) > 4 else 0.0,
        }
    except (ValueError, IndexError):
        return None


def _get_or_create_competitor(db, comp_name: str) -> int:
    """name UNIQUE 제약 없으므로 SELECT-first 방식으로 경쟁사 upsert."""
    row = db.execute(
        text("SELECT id FROM competitors WHERE name = :n ORDER BY id LIMIT 1"),
        {"n": comp_name},
    ).fetchone()
    if row:
        return row[0]
    result = db.execute(
        text("INSERT INTO competitors (name) VALUES (:n) RETURNING id"),
        {"n": comp_name},
    ).fetchone()
    db.commit()
    return result[0]


def _save_openg_results(db, bid_id: int, bid_no: str, items: list[dict]) -> int:
    """개찰결과 API 응답의 전체 참가자를 bid_results에 저장.
    낙찰자(is_winner=True) 1명 + 비낙찰자(is_winner=False) 모두 포함.
    ML win_model 학습에 필요한 비낙찰 데이터를 확보하기 위한 핵심 함수."""
    if not items:
        return 0

    saved = 0
    parsed_list: list[dict] = []

    for idx, item in enumerate(items):
        openg_info_raw = (item.get("opengCorpInfo") or "").strip()
        parsed = _parse_openg_corp_info(openg_info_raw)
        if not parsed or not parsed["comp_name"]:
            continue

        # rank: bidprcpOrd(투찰순위) > sucsfOrd > 목록 인덱스
        rank_raw = item.get("bidprcpOrd") or item.get("sucsfOrd")
        try:
            rank = int(rank_raw)
        except (TypeError, ValueError):
            rank = idx + 1

        sucsfYn = str(item.get("sucsfYn") or "N").upper().strip()
        is_winner = sucsfYn in ("Y", "1")
        parsed_list.append({**parsed, "rank": rank, "is_winner": is_winner})

    if not parsed_list:
        return 0

    # 명시적 낙찰자 없으면 rank=1(가장 낮은) 항목을 낙찰자로 간주
    if not any(p["is_winner"] for p in parsed_list):
        parsed_list.sort(key=lambda p: p["rank"])
        parsed_list[0]["is_winner"] = True

    for p in parsed_list:
        try:
            comp_id = _get_or_create_competitor(db, p["comp_name"])
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
                "amt":  p["bid_amt"],
                "rate": p["bid_rate"],
                "rank": p["rank"],
                "win":  p["is_winner"],
            })
            saved += 1
        except Exception as e:
            db.rollback()
            logger.warning(f"    참가자 저장 실패 {bid_no} ({p['comp_name']}): {e}")
            continue

    if saved > 0:
        db.execute(text("UPDATE bids SET status='closed' WHERE id=:id"), {"id": bid_id})
    db.commit()
    return saved


async def collect_results_per_bid(daily_limit: int = 1000):
    """
    대상 공종 공고를 공고번호별로 개찰결과 조회.
    getOpengResultListInfoCnstwkPPSSrch (inqryDiv=3) 사용 — 테스트에서 88% 매칭 확인됨.
    """
    import httpx

    db = MkSession()
    try:
        rows = db.execute(text("""
            SELECT b.id, b.announcement_no
            FROM bids b
            WHERE b.industry_id = ANY(:ids)
              AND b.bid_open_date IS NOT NULL
              AND b.bid_open_date < NOW()
              AND (
                NOT EXISTS (SELECT 1 FROM bid_results r WHERE r.bid_id = b.id)
                OR (
                  EXISTS     (SELECT 1 FROM bid_results r WHERE r.bid_id = b.id AND r.is_winner = true)
                  AND NOT EXISTS (SELECT 1 FROM bid_results r WHERE r.bid_id = b.id AND r.is_winner = false)
                )
              )
            ORDER BY b.bid_open_date DESC
            LIMIT :lim
        """), {"ids": TARGET_INDUSTRY_IDS, "lim": daily_limit}).fetchall()
    finally:
        db.close()

    if not rows:
        logger.info("PHASE 4: 수집할 미결과 공고 없음")
        return 0

    logger.info(f"PHASE 4: 개찰결과 공고번호별 조회 — 대상 {len(rows)}건 (한도 {daily_limit})")
    saved_total  = 0
    no_result    = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        for idx, (bid_id, bid_no) in enumerate(rows, 1):
            retries = 0
            while retries < 3:
                try:
                    resp = await client.get(
                        f"{G2B_RESULT_BASE}/{OPENG_ENDPOINT}",
                        params={
                            "inqryDiv":   3,
                            "bidNtceNo":  bid_no,
                            "numOfRows":  100,
                            "pageNo":     1,
                            "type":       "json",
                            "serviceKey": G2B_API_KEY,
                        }
                    )
                    if resp.status_code == 429:
                        wait = 60 * (retries + 1)
                        logger.warning(f"  429 — {wait}초 대기 후 재시도 ({retries+1}/3)")
                        await asyncio.sleep(wait)
                        retries += 1
                        continue
                    resp.raise_for_status()

                    body  = resp.json().get("response", {}).get("body", {})
                    items = body.get("items", [])
                    if isinstance(items, dict):
                        items = [items]

                    if items:
                        db2 = MkSession()
                        try:
                            n = _save_openg_results(db2, bid_id, bid_no, items)
                            saved_total += n
                            if n > 0:
                                logger.info(
                                    f"  [{idx}/{len(rows)}] {bid_no}: "
                                    f"참가자 {len(items)}명 -> {n}건 저장 "
                                    f"(낙찰자 1명 + 비낙찰자 {n-1}명)"
                                )
                        finally:
                            db2.close()
                    else:
                        no_result += 1
                    break

                except Exception as e:
                    retries += 1
                    if retries >= 3:
                        logger.warning(f"  [{idx}/{len(rows)}] {bid_no} 오류: {e}")
                    else:
                        await asyncio.sleep(3)

            await asyncio.sleep(0.8)

            if idx % 100 == 0:
                logger.info(f"  진행 {idx}/{len(rows)} — 저장 {saved_total}건, 결과없음 {no_result}건")

    logger.info(f"PHASE 4 완료: 저장 {saved_total}건, 결과없음 {no_result}건 ({len(rows)}건 조회)")
    return saved_total


# ─────────────────────────────────────────────────────────────────────
# 결과 요약
# ─────────────────────────────────────────────────────────────────────
def print_summary():
    db = MkSession()
    try:
        rows = db.execute(text("""
            SELECT i.name,
                   COUNT(DISTINCT b.id)           AS total_bids,
                   COUNT(DISTINCT r.bid_id)        AS bids_with_results,
                   COUNT(r.id)                     AS total_results,
                   COUNT(CASE WHEN NOT r.is_winner THEN 1 END) AS non_winners,
                   COUNT(CASE WHEN r.is_winner THEN 1 END) AS winners,
                   COUNT(DISTINCT r.competitor_id) AS unique_competitors,
                   ROUND(AVG(CASE WHEN r.is_winner THEN r.bid_rate END)::numeric*100, 2) AS avg_win_rate_pct
            FROM industries i
            LEFT JOIN bids b        ON b.industry_id = i.id
            LEFT JOIN bid_results r ON r.bid_id = b.id
            WHERE i.id = ANY(:ids)
            GROUP BY i.id, i.name
        """), {"ids": TARGET_INDUSTRY_IDS}).fetchall()

        print("\n" + "="*70)
        print("수집 결과 요약")
        print("="*70)
        for r in rows:
            print(f"\n[{r[0]}]")
            print(f"  총 입찰공고  : {r[1]:,}건")
            print(f"  낙찰결과 보유: {r[2]:,}건  (총 결과 레코드 {r[3]:,}건)")
            print(f"  낙찰건수     : {r[4]:,}건  참여업체(경쟁사) {r[5]:,}개사")
            print(f"  평균낙찰률   : {r[6]}%")
        print("="*70 + "\n")
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────────────
async def main(past_days: int, phase: int = 0, daily_limit: int = 1000):
    """phase=0: 전체, 1: 공고만, 2: 날짜범위결과, 3: 최근90일, 4: 개찰결과공고번호별(권장)"""
    logger.info("=" * 60)
    logger.info("활성 공종 데이터 백필 시작")
    logger.info(f"대상 공종 ID: {TARGET_INDUSTRY_IDS}")
    logger.info(f"수집 기간: 최근 {past_days}일  (phase={phase or '전체'})")
    logger.info("=" * 60)

    if phase in (0, 1):
        await collect_notices_extended(past_days=past_days)
    if phase in (0, 2):
        await collect_scsbid_results(past_days=past_days)
    if phase in (0, 3):
        await collect_scsbid_recent()
    if phase in (0, 4):
        await collect_results_per_bid(daily_limit=daily_limit)
    print_summary()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days",        type=int, default=365,
                        help="수집 기간 일수 (기본 365일)")
    parser.add_argument("--phase",       type=int, default=0,
                        help="0=전체 1=공고만 2=날짜범위결과 3=최근90일 4=개찰결과공고번호별(권장)")
    parser.add_argument("--daily-limit", type=int, default=1000,
                        help="phase4 조회 한도 (기본 1000)")
    args = parser.parse_args()
    asyncio.run(main(args.days, args.phase, args.daily_limit))

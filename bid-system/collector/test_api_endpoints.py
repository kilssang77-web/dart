"""
나라장터 API 엔드포인트 진단 스크립트.

참고 파일(NaraJang_scheduler.py) 분석으로 발견한 내용을 검증:
1. 물품 ScsbidInfoService에서 bid_no 검색은 inqryDiv=3 (우리는 2로 시도했음)
2. getOpengResultListInfoThngPPSSrch 의 opengCorpInfo 필드 (전참여업체 데이터)
3. 공사 버전 동등 엔드포인트 존재 여부

사용법:
  docker exec bid_collector python test_api_endpoints.py
"""
import os, sys, asyncio, logging
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

G2B_API_KEY = os.getenv("G2B_API_KEY", "")
if not G2B_API_KEY:
    logger.error("G2B_API_KEY 미설정")
    sys.exit(1)

# 테스트할 공고번호 (DB에서 실제 존재하는 것 사용)
DATABASE_URL = os.getenv("DATABASE_URL", "")

SCSBID_BASE_AS = "https://apis.data.go.kr/1230000/as/ScsbidInfoService"   # 우리가 쓰던 URL
SCSBID_BASE    = "https://apis.data.go.kr/1230000/ScsbidInfoService"       # 물품용 (참고파일 기준)
BID_PUBLIC_AD  = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService" # 우리가 쓰던 공고 URL

COMMON_PARAMS = {
    "numOfRows": 5,
    "pageNo":    1,
    "type":      "json",
    "serviceKey": G2B_API_KEY,
}


async def test_endpoint(client: httpx.AsyncClient, label: str, url: str, params: dict) -> dict | None:
    try:
        resp = await client.get(url, params={**COMMON_PARAMS, **params}, timeout=15.0)
        code = resp.status_code
        if code != 200:
            logger.info(f"  [{label}] HTTP {code} — 접근 불가")
            return None
        data = resp.json()
        body = data.get("response", {}).get("body", {})
        result_code = data.get("response", {}).get("header", {}).get("resultCode", "??")
        result_msg  = data.get("response", {}).get("header", {}).get("resultMsg", "")
        total = body.get("totalCount", 0)
        items = body.get("items", [])
        if isinstance(items, dict):
            items = [items]
        logger.info(f"  [{label}] HTTP {code} | resultCode={result_code} | total={total} | items={len(items or [])}")
        if result_msg and result_msg not in ("NORMAL SERVICE.", "정상"):
            logger.info(f"    resultMsg: {result_msg}")
        if items:
            # 필드명 출력 (첫 번째 아이템)
            sample = items[0] if isinstance(items, list) else items
            keys = list(sample.keys())
            logger.info(f"    필드: {keys[:15]}...")
            if "opengCorpInfo" in sample:
                logger.info(f"    ★ opengCorpInfo 발견: {sample['opengCorpInfo'][:100]}...")
        return body
    except Exception as e:
        logger.info(f"  [{label}] 오류: {e}")
        return None


async def get_sample_bid_nos() -> list[str]:
    """DB에서 대상 공종의 실제 공고번호 가져오기."""
    if not DATABASE_URL:
        return ["20250401121", "20250401122"]
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT announcement_no
                FROM bids
                WHERE industry_id = ANY(ARRAY[20,24,31])
                  AND bid_open_date IS NOT NULL
                  AND bid_open_date < NOW()
                ORDER BY bid_open_date DESC
                LIMIT 5
            """)).fetchall()
        nos = [r[0] for r in rows]
        logger.info(f"DB에서 가져온 공고번호: {nos}")
        return nos
    except Exception as e:
        logger.warning(f"DB 조회 실패: {e}")
        return []


async def main():
    bid_nos = await get_sample_bid_nos()
    sample_no = bid_nos[0] if bid_nos else ""

    today   = __import__("datetime").datetime.now()
    dt_from = (today - __import__("datetime").timedelta(days=30)).strftime("%Y%m%d") + "0000"
    dt_to   = today.strftime("%Y%m%d") + "2359"

    print("\n" + "=" * 70)
    print("나라장터 API 엔드포인트 진단")
    print("=" * 70)

    async with httpx.AsyncClient(timeout=20.0) as client:

        # ── 1. 기존 공사 낙찰정보 (inqryDiv=1 날짜범위) ──────────────────
        print("\n[1] 공사 낙찰정보 — 날짜범위 (inqryDiv=1) — 기준선")
        await test_endpoint(client, "AS/ScsbidInfoService/getScsbidListSttusCnstwk(div=1)",
            f"{SCSBID_BASE_AS}/getScsbidListSttusCnstwk",
            {"inqryDiv": 1, "inqryBgnDt": dt_from, "inqryEndDt": dt_to})

        # ── 2. 공사 inqryDiv=3 (참고파일 힌트: 물품은 div=3 이 bid_no 검색) ─
        if sample_no:
            print(f"\n[2] 공사 낙찰정보 — 공고번호 inqryDiv=3 (참고파일 힌트) bid={sample_no}")
            await test_endpoint(client, "AS/ScsbidInfoService/getScsbidListSttusCnstwk(div=3)",
                f"{SCSBID_BASE_AS}/getScsbidListSttusCnstwk",
                {"inqryDiv": 3, "bidNtceNo": sample_no})

        # ── 3. 공사 개찰결과 완료목록 — 참고파일 operation_name4 공사 버전 ──
        print("\n[3] 공사 개찰완료 목록 (getOpengResultListInfoCnstwkOpengCompt) — /as/ 포함")
        await test_endpoint(client, "AS/getOpengResultListInfoCnstwkOpengCompt(date)",
            f"{SCSBID_BASE_AS}/getOpengResultListInfoCnstwkOpengCompt",
            {"inqryDiv": 2, "inqryBgnDt": dt_from, "inqryEndDt": dt_to})

        # ── 4. 공사 전참여업체 (ThngPPSSrch 의 공사버전 추정) ────────────
        print("\n[4] 공사 개찰결과 목록 PPSSrch 버전 추정")
        await test_endpoint(client, "AS/getOpengResultListInfoCnstwkPPSSrch(date)",
            f"{SCSBID_BASE_AS}/getOpengResultListInfoCnstwkPPSSrch",
            {"inqryDiv": 2, "inqryBgnDt": dt_from, "inqryEndDt": dt_to})

        # ── 5. no-/as/ URL 버전 시도 ─────────────────────────────────────
        print("\n[5] ScsbidInfoService (no /as/) — 물품URL로 공사 엔드포인트 시도")
        await test_endpoint(client, "ScsbidInfoService/getScsbidListSttusCnstwk(div=1)",
            f"{SCSBID_BASE}/getScsbidListSttusCnstwk",
            {"inqryDiv": 1, "inqryBgnDt": dt_from, "inqryEndDt": dt_to})

        # ── 6. BidPublicInfoService 개찰결과 엔드포인트 ─────────────────
        print("\n[6] BidPublicInfoService 공사 개찰결과 (우리가 쓰는 ad/ URL)")
        await test_endpoint(client, "AD/getBidPblancRsltListInfoCnstwk(date)",
            f"{BID_PUBLIC_AD}/getBidPblancRsltListInfoCnstwk",
            {"inqryDiv": 2, "inqryBgnDt": dt_from, "inqryEndDt": dt_to})

        # ── 7. BidPublicInfoService 개찰결과 OpengCompt ─────────────────
        print("\n[7] BidPublicInfoService 개찰완료 (OpengCompt)")
        await test_endpoint(client, "AD/getOpengResultListInfoOpengCompt",
            f"{BID_PUBLIC_AD}/getOpengResultListInfoOpengCompt",
            {"inqryDiv": 2, "inqryBgnDt": dt_from, "inqryEndDt": dt_to})

        # ── 8. 공사 개찰결과 날짜범위 — 다른 경로 ───────────────────────
        print("\n[8] 공사 전참여업체 — /as/ ScsbidInfoService 개찰결과 날짜범위")
        await test_endpoint(client, "AS/getOpengResultListInfoCnstwk(date)",
            f"{SCSBID_BASE_AS}/getOpengResultListInfoCnstwk",
            {"inqryDiv": 2, "inqryBgnDt": dt_from, "inqryEndDt": dt_to})

        # ── 9. 공고번호로 개찰완료 목록 (inqryDiv=3) ─────────────────────
        if sample_no:
            print(f"\n[9] 공사 개찰완료 목록 — 공고번호 inqryDiv=3, bid={sample_no}")
            await test_endpoint(client, "AS/getOpengResultListInfoCnstwkOpengCompt(div=3)",
                f"{SCSBID_BASE_AS}/getOpengResultListInfoCnstwkOpengCompt",
                {"inqryDiv": 3, "bidNtceNo": sample_no})

    print("\n" + "=" * 70)
    print("진단 완료 — HTTP 200 + totalCount>0 인 엔드포인트가 사용 가능한 것")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())

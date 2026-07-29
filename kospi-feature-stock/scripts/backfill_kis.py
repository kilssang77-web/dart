"""
KIS REST 기반 일봉 백필 — pykrx 완전 제거 버전
GCP e2-micro에서 직접 실행 가능 (KRX IP 차단 우회)
크론 등록 불필요 — 수동 1회 실행 또는 필요시 재실행

동작:
  1. Supabase stocks(is_active=true) 코드 전체 로드
  2. 종목별 KIS FHKST03010100 (기간별시세) 호출 → 일봉 OHLCV 취득
  3. daily_bars ON CONFLICT DO UPDATE upsert
  4. KOSPI지수(0001) / KOSDAQ지수(1001) 별도 처리 (FHKUP03500100)

환경변수:
  POSTGRES_DSN, KIS_APP_KEY, KIS_APP_SECRET
  BACKFILL_DAYS      : 소급 기간 (기본 90)
  BACKFILL_CONCURRENT: 동시 종목 수 (기본 5, 20 TPS 한도 고려)
"""
import asyncio
import asyncpg
import json
import logging
import os
import threading
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone

from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/.env"))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backfill_kis")

KST        = timezone(timedelta(hours=9))
DSN        = os.environ["POSTGRES_DSN"]
APP_KEY    = os.environ["KIS_APP_KEY"]
APP_SECRET = os.environ["KIS_APP_SECRET"]
KIS_BASE   = "https://openapi.koreainvestment.com:9443"
DAYS       = int(os.environ.get("BACKFILL_DAYS",       "90"))
CONCURRENT = int(os.environ.get("BACKFILL_CONCURRENT", "5"))

_TOKEN_CACHE: dict = {}
_TOKEN_LOCK = threading.Lock()   # BUG-5 fix: 멀티스레드 race condition 방지


# ── KIS 인증 ─────────────────────────────────────────────────

def _kis_token() -> str:
    with _TOKEN_LOCK:
        if _TOKEN_CACHE.get("expires", 0) > time.time() + 60:
            return _TOKEN_CACHE["token"]
        body = json.dumps({
            "grant_type": "client_credentials",
            "appkey":     APP_KEY,
            "appsecret":  APP_SECRET,
        }).encode()
        req = urllib.request.Request(
            f"{KIS_BASE}/oauth2/tokenP", data=body,
            headers={"content-type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read())
        _TOKEN_CACHE.update({"token": d["access_token"], "expires": time.time() + 23 * 3600})
        log.info("KIS 토큰 발급 완료")
        return _TOKEN_CACHE["token"]


def _kis_get(path: str, tr_id: str, params: dict) -> dict:
    qs  = "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(
        f"{KIS_BASE}{path}?{qs}",
        headers={
            "authorization":  f"Bearer {_kis_token()}",
            "appkey":         APP_KEY,
            "appsecret":      APP_SECRET,
            "tr_id":          tr_id,
            "content-type":   "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def _s(v) -> float:
    try:
        return float(str(v).replace(",", "").strip() or 0)
    except (ValueError, TypeError):
        return 0.0


# ── 일봉 조회 ─────────────────────────────────────────────────

class _APIReject(Exception):
    """KIS rt_cd != '0' — 재시도 의미 없음"""


def fetch_stock_bars(code: str, mkt_div: str, start: str, end: str) -> list[dict]:
    """
    FHKST03010100 — 종목 일봉 (output2 배열).
    mkt_div: J=KOSPI, Q=KOSDAQ
    Raises _APIReject if rt_cd != '0' (API 거절).
    Returns [] on network error.
    """
    try:
        d = _kis_get(
            "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
            "FHKST03010100",
            {
                "FID_COND_MRKT_DIV_CODE": mkt_div,
                "FID_INPUT_ISCD":         code,
                "FID_INPUT_DATE_1":       start,
                "FID_INPUT_DATE_2":       end,
                "FID_PERIOD_DIV_CODE":    "D",
                "FID_ORG_ADJ_PRC":        "0",
            },
        )
        if d.get("rt_cd") != "0":
            raise _APIReject(d.get("msg1", ""))
        rows = d.get("output2") or []
        result = []
        for r in rows:
            dt_s  = str(r.get("stck_bsop_date", "")).strip()
            close = int(_s(r.get("stck_clpr")))
            if len(dt_s) != 8 or close <= 0:
                continue
            result.append({
                "date":        date(int(dt_s[:4]), int(dt_s[4:6]), int(dt_s[6:8])),
                "code":        code,
                "open":        int(_s(r.get("stck_oprc"))),
                "high":        int(_s(r.get("stck_hgpr"))),
                "low":         int(_s(r.get("stck_lwpr"))),
                "close":       close,
                "volume":      int(_s(r.get("acml_vol"))),
                "amount":      int(_s(r.get("acml_tr_pbmn"))),
                "change_rate": float(_s(r.get("prdy_ctrt"))),
            })
        return result
    except _APIReject:
        raise
    except Exception as e:
        log.debug(f"일봉 조회 네트워크 오류({code}/{mkt_div}): {e}")
        return []


def fetch_index_bars(mkt_code: str, start: str, end: str) -> list[dict]:
    """FHKUP03500100 — 지수 일봉 (output2 배열). mkt_code: 0001 / 1001"""
    try:
        d = _kis_get(
            "/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice",
            "FHKUP03500100",
            {
                "FID_COND_MRKT_DIV_CODE": "U",
                "FID_INPUT_ISCD":         mkt_code,
                "FID_INPUT_DATE_1":       start,
                "FID_INPUT_DATE_2":       end,
                "FID_PERIOD_DIV_CODE":    "D",
            },
        )
        if d.get("rt_cd") != "0":
            return []
        result = []
        for r in d.get("output2", []):
            dt_s  = str(r.get("stck_bsop_date", "")).strip()
            close = int(float(_s(r.get("bstp_nmix_prpr"))))
            if len(dt_s) != 8 or close <= 0:
                continue
            result.append({
                "date":        date(int(dt_s[:4]), int(dt_s[4:6]), int(dt_s[6:8])),
                "code":        mkt_code,
                "open":        int(float(_s(r.get("bstp_nmix_oprc")))),
                "high":        int(float(_s(r.get("bstp_nmix_hgpr")))),
                "low":         int(float(_s(r.get("bstp_nmix_lwpr")))),
                "close":       close,
                "volume":      int(_s(r.get("acml_vol"))),
                "amount":      int(_s(r.get("acml_tr_pbmn"))),
                "change_rate": float(_s(r.get("bstp_nmix_prdy_ctrt"))),
            })
        return result
    except Exception as e:
        log.debug(f"지수 조회 오류({mkt_code}): {e}")
        return []


# ── DB ────────────────────────────────────────────────────────

async def upsert_bars(conn: asyncpg.Connection, rows: list[dict]) -> int:
    if not rows:
        return 0
    data = [
        (r["date"], r["code"], r["open"], r["high"], r["low"],
         r["close"], r["volume"], r["amount"], r["change_rate"])
        for r in rows
    ]
    await conn.executemany(
        """
        INSERT INTO daily_bars
            (date, code, open, high, low, close, volume, amount, change_rate)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
        ON CONFLICT (date, code) DO UPDATE SET
            open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
            close=EXCLUDED.close, volume=EXCLUDED.volume,
            amount=EXCLUDED.amount, change_rate=EXCLUDED.change_rate
        """,
        data,
    )
    return len(data)


# ── 병렬 백필 ─────────────────────────────────────────────────

async def _backfill_one(
    code: str, mkt_div: str, start: str, end: str,
    sem: asyncio.Semaphore, pool: asyncpg.Pool, counters: dict,  # BUG-1 fix: pool 사용
) -> None:
    async with sem:
        loop = asyncio.get_event_loop()
        bars: list[dict] = []
        try:
            bars = await loop.run_in_executor(None, fetch_stock_bars, code, mkt_div, start, end)
        except _APIReject:
            # BUG-6 fix: API 거절(Q 미지원)만 J로 재시도, 네트워크 오류는 재시도 안 함
            if mkt_div == "Q":
                try:
                    bars = await loop.run_in_executor(None, fetch_stock_bars, code, "J", start, end)
                except _APIReject:
                    pass

        if bars:
            async with pool.acquire() as conn:   # BUG-1 fix: 전용 커넥션 획득
                n = await upsert_bars(conn, bars)
                counters["rows"] += n

        counters["done"] += 1
        if counters["done"] % 200 == 0 or counters["done"] == counters["total"]:
            log.info(
                f"진행 {counters['done']:>4}/{counters['total']} | "
                f"저장 {counters['rows']:,}행"
            )
        await asyncio.sleep(0.05)   # KIS 20 TPS 한도


# ── 메인 ─────────────────────────────────────────────────────

async def main():
    now_kst    = datetime.now(KST)
    end_date   = now_kst.date()
    start_date = end_date - timedelta(days=DAYS + 14)
    end_str    = end_date.strftime("%Y%m%d")
    start_str  = start_date.strftime("%Y%m%d")

    log.info(f"KIS REST 백필: {start_str} ~ {end_str} (요청 {DAYS}일)")
    _kis_token()

    # BUG-1 fix: pool 생성 (pool_size = CONCURRENT + 여유)
    pool = await asyncpg.create_pool(
        DSN, min_size=2, max_size=CONCURRENT + 2, statement_cache_size=0
    )
    try:
        async with pool.acquire() as conn:
            stock_rows = await conn.fetch(
                "SELECT code, market FROM stocks WHERE is_active = true ORDER BY code"
            )

        if not stock_rows:
            log.error("stocks 테이블 비어있음 — 종목 마스터 먼저 적재 필요")
            return

        stocks = [
            (r["code"], "J" if r["market"] == "KOSPI" else "Q")
            for r in stock_rows
        ]
        kospi_cnt  = sum(1 for _, m in stocks if m == "J")
        kosdaq_cnt = sum(1 for _, m in stocks if m == "Q")
        log.info(f"종목 로드: 총 {len(stocks)}개 (KOSPI {kospi_cnt} / KOSDAQ {kosdaq_cnt})")

        # 종목 일봉 병렬 백필
        sem      = asyncio.Semaphore(CONCURRENT)
        counters = {"done": 0, "total": len(stocks), "rows": 0}

        await asyncio.gather(*[
            _backfill_one(code, mkt, start_str, end_str, sem, pool, counters)
            for code, mkt in stocks
        ])

        log.info(f"종목 백필 완료: {counters['rows']:,}행")

        # 지수 일봉
        loop = asyncio.get_event_loop()
        for mkt_code in ["0001", "1001"]:
            idx_bars = await loop.run_in_executor(
                None, fetch_index_bars, mkt_code, start_str, end_str
            )
            if idx_bars:
                async with pool.acquire() as conn:
                    n = await upsert_bars(conn, idx_bars)
                log.info(f"지수 {mkt_code}: {n}행 저장")
            else:
                log.warning(f"지수 {mkt_code}: 데이터 없음")
            await asyncio.sleep(0.1)

        async with pool.acquire() as conn:
            total_bars = await conn.fetchval("SELECT COUNT(*) FROM daily_bars")
        log.info(f"daily_bars 총 행수: {total_bars:,}")

    finally:
        await pool.close()

    log.info("백필 완료")


if __name__ == "__main__":
    asyncio.run(main())

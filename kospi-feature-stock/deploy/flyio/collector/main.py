"""
Fly.io 경량 수집 데몬 — 256MB 상시기동
───────────────────────────────────────
역할:
  1. KIS REST API 전 종목 현재가 스캔 (3~4분 사이클)
  2. 규칙 기반 패턴 탐지 (거래량급증, 신고가, 장대양봉, 해머)
  3. 패턴 감지 시 Fly.io API ML endpoint 호출 → 성공확률 취득
  4. Supabase에 이벤트 저장
  5. Telegram 즉시 발송

의존성: asyncpg, httpx, numpy, orjson, python-dotenv
  (torch/lightgbm 없음 → ML은 Render.com이 담당)
"""
import asyncio
import logging
import os
import time
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo

import asyncpg
import httpx
import numpy as np
import orjson
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("flyio-collector")

_KST = ZoneInfo("Asia/Seoul")

# ── 환경변수 ──────────────────────────────────────────────────────────────────
PG_DSN          = os.environ["POSTGRES_DSN"]         # Supabase PostgreSQL DSN
REDIS_URL       = os.environ.get("REDIS_URL", "")
KIS_APP_KEY     = os.environ["KIS_APP_KEY"]
KIS_APP_SECRET  = os.environ["KIS_APP_SECRET"]
KIS_ACCOUNT_NO  = os.environ["KIS_ACCOUNT_NO"]
KIS_BASE_URL    = os.environ.get("KIS_BASE_URL", "https://openapi.koreainvestment.com:9443")
API_URL         = os.environ.get("API_URL", "https://quant-eye-api.fly.dev")
TELEGRAM_TOKEN  = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID= os.environ.get("TELEGRAM_CHAT_ID", "")
DART_API_KEY    = os.environ.get("DART_API_KEY", "")

# ── 탐지 파라미터 ─────────────────────────────────────────────────────────────
VOL_SURGE_RATIO    = float(os.environ.get("VOL_SURGE_RATIO",    "3.0"))
BREAKOUT_MIN_PCT   = float(os.environ.get("BREAKOUT_MIN_PCT",   "0.5"))
CANDLE_BODY_RATIO  = float(os.environ.get("CANDLE_BODY_RATIO",  "0.7"))
MIN_AMOUNT         = int(os.environ.get("INTRADAY_MIN_AMOUNT",  "200000000"))
CONCURRENT         = int(os.environ.get("INTRADAY_CONCURRENT",  "5"))
SCAN_INTERVAL_SEC  = int(os.environ.get("SCAN_INTERVAL_SEC",    "180"))   # 3분

MARKET_OPEN  = (9, 0)
MARKET_CLOSE = (15, 35)


# ════════════════════════════════════════════════════════════════════════════
# KIS 인증
# ════════════════════════════════════════════════════════════════════════════
class KISAuth:
    def __init__(self):
        self._token: str | None = None
        self._expires: float = 0.0
        self._lock = asyncio.Lock()

    async def get_token(self, client: httpx.AsyncClient) -> str:
        async with self._lock:
            if self._token and time.time() < self._expires - 300:
                return self._token
            resp = await client.post(
                f"{KIS_BASE_URL}/oauth2/tokenP",
                json={
                    "grant_type":  "client_credentials",
                    "appkey":      KIS_APP_KEY,
                    "appsecret":   KIS_APP_SECRET,
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            self._token   = data["access_token"]
            self._expires = time.time() + int(data.get("expires_in", 86400))
            logger.info("KIS 토큰 갱신 완료")
            return self._token

    def headers(self, token: str, tr_id: str) -> dict:
        return {
            "authorization": f"Bearer {token}",
            "appkey":         KIS_APP_KEY,
            "appsecret":      KIS_APP_SECRET,
            "tr_id":          tr_id,
            "custtype":       "P",
        }


# ════════════════════════════════════════════════════════════════════════════
# 종목 현재가 조회
# ════════════════════════════════════════════════════════════════════════════
async def fetch_price(client: httpx.AsyncClient, auth: KISAuth, code: str) -> dict | None:
    try:
        token = await auth.get_token(client)
        resp  = await client.get(
            f"{KIS_BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price",
            headers=auth.headers(token, "FHKST01010100"),
            params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code},
            timeout=10,
        )
        data = resp.json()
        if data.get("rt_cd") != "0":
            return None
        o = data["output"]
        return {
            "code":        code,
            "price":       int(o.get("stck_prpr", 0)),
            "open":        int(o.get("stck_oprc", 0)),
            "high":        int(o.get("stck_hgpr", 0)),
            "low":         int(o.get("stck_lwpr", 0)),
            "volume":      int(o.get("acml_vol", 0)),
            "amount":      int(o.get("acml_tr_pbmn", 0)),
            "change_rate": float(o.get("prdy_ctrt", 0)),
            "high_52w":    int(o.get("w52_hgpr", 0)),
        }
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════════════════
# 통계 조회 (평균 거래량)
# ════════════════════════════════════════════════════════════════════════════
async def get_avg_vol(db: asyncpg.Pool, code: str) -> float:
    row = await db.fetchrow(
        """
        SELECT AVG(volume) AS avg_vol
        FROM (
            SELECT volume FROM daily_bars
            WHERE code = $1
            ORDER BY date DESC
            LIMIT 20
        ) t
        """,
        code,
    )
    return float(row["avg_vol"] or 0)


async def get_recent_high(db: asyncpg.Pool, code: str) -> int:
    row = await db.fetchrow(
        "SELECT MAX(high) AS h FROM daily_bars WHERE code = $1 AND date >= CURRENT_DATE - 52 * 7",
        code,
    )
    return int(row["h"] or 0)


# ════════════════════════════════════════════════════════════════════════════
# 패턴 탐지 (규칙 기반, 경량)
# ════════════════════════════════════════════════════════════════════════════
def detect_patterns(q: dict, avg_vol: float, high_52w: int) -> list[str]:
    patterns = []
    if q["amount"] < MIN_AMOUNT:
        return patterns

    # 거래량 급증
    if avg_vol > 0 and q["volume"] > avg_vol * VOL_SURGE_RATIO:
        patterns.append("volume_surge")

    # 신고가 돌파
    if high_52w > 0 and q["price"] >= high_52w * (1 - 0.005):
        patterns.append("new_high")

    # 장대양봉
    if q["open"] > 0:
        body = q["price"] - q["open"]
        rng  = q["high"] - q["low"]
        if rng > 0 and body / rng >= CANDLE_BODY_RATIO and q["change_rate"] >= 3.0:
            patterns.append("long_white_candle")

    # 해머 패턴 (하락 후 긴 아래꼬리)
    if q["open"] > 0 and q["low"] > 0:
        body       = abs(q["price"] - q["open"])
        lower_wick = min(q["open"], q["price"]) - q["low"]
        total_rng  = q["high"] - q["low"]
        if total_rng > 0 and lower_wick >= body * 2 and lower_wick / total_rng >= 0.5:
            patterns.append("hammer")

    return patterns


# ════════════════════════════════════════════════════════════════════════════
# Render.com ML 스코어링
# ════════════════════════════════════════════════════════════════════════════
async def get_ml_score(client: httpx.AsyncClient, code: str, event_type: str,
                        price: int, change_rate: float, volume_ratio: float) -> float | None:
    try:
        resp = await client.post(
            f"{API_URL}/api/v1/ml/score",
            json={
                "code":         code,
                "event_type":   event_type,
                "price":        price,
                "change_rate":  change_rate,
                "volume_ratio": volume_ratio,
            },
            timeout=8,
        )
        if resp.status_code == 200:
            return resp.json().get("success_prob")
    except Exception as e:
        logger.warning(f"ML 스코어 실패 [{code}]: {e}")
    return None


# ════════════════════════════════════════════════════════════════════════════
# Supabase 이벤트 저장
# ════════════════════════════════════════════════════════════════════════════
async def save_event(db: asyncpg.Pool, code: str, event_type: str,
                     q: dict, score: float | None) -> int | None:
    now = datetime.now(_KST)
    row = await db.fetchrow(
        """
        INSERT INTO feature_events
            (detected_at, code, event_type, price, change_rate,
             volume, amount, signal_score, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $1)
        ON CONFLICT DO NOTHING
        RETURNING id
        """,
        now, code, event_type, q["price"], q["change_rate"],
        q["volume"], q["amount"], score,
    )
    return row["id"] if row else None


# ════════════════════════════════════════════════════════════════════════════
# Telegram 알림
# ════════════════════════════════════════════════════════════════════════════
async def send_telegram(client: httpx.AsyncClient, code: str, name: str,
                         event_type: str, q: dict, score: float | None):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    type_label = {
        "volume_surge":       "📈 거래량 급증",
        "new_high":           "🚀 52주 신고가",
        "long_white_candle":  "🕯 장대양봉",
        "hammer":             "🔨 해머 패턴",
    }.get(event_type, event_type)

    score_str = f"{score:.1%}" if score else "산출 중"
    msg = (
        f"{type_label}\n"
        f"종목: {name}({code})\n"
        f"현재가: {q['price']:,}원 ({q['change_rate']:+.2f}%)\n"
        f"거래대금: {q['amount'] / 1e8:.1f}억\n"
        f"성공확률: {score_str}"
    )
    try:
        await client.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=5,
        )
    except Exception as e:
        logger.warning(f"Telegram 발송 실패: {e}")


# ════════════════════════════════════════════════════════════════════════════
# 전 종목 스캔 1 사이클
# ════════════════════════════════════════════════════════════════════════════
async def scan_cycle(db: asyncpg.Pool, auth: KISAuth, stock_map: dict[str, str]):
    sem = asyncio.Semaphore(CONCURRENT)
    detected = 0

    async def process(client: httpx.AsyncClient, code: str):
        nonlocal detected
        async with sem:
            q = await fetch_price(client, auth, code)
            if not q or q["price"] == 0:
                return

            avg_vol   = await get_avg_vol(db, code)
            high_52w  = q.get("high_52w") or await get_recent_high(db, code)
            vol_ratio = q["volume"] / avg_vol if avg_vol > 0 else 0

            patterns = detect_patterns(q, avg_vol, high_52w)
            if not patterns:
                return

            for event_type in patterns:
                score = await get_ml_score(
                    client, code, event_type,
                    q["price"], q["change_rate"], vol_ratio,
                )
                event_id = await save_event(db, code, event_type, q, score)
                if event_id:
                    detected += 1
                    name = stock_map.get(code, code)
                    await send_telegram(client, code, name, event_type, q, score)
                    logger.info(f"[탐지] {code} {event_type} score={score}")

    async with httpx.AsyncClient(timeout=15) as client:
        tasks = [process(client, code) for code in stock_map]
        await asyncio.gather(*tasks, return_exceptions=True)

    return detected


# ════════════════════════════════════════════════════════════════════════════
# 메인 루프
# ════════════════════════════════════════════════════════════════════════════
async def main():
    logger.info("Fly.io 수집 데몬 시작")
    db   = await asyncpg.create_pool(PG_DSN, min_size=2, max_size=5)
    auth = KISAuth()

    # 종목 목록 캐시 (1시간마다 갱신)
    stock_map: dict[str, str] = {}
    last_stock_load = 0.0

    while True:
        now_kst = datetime.now(_KST)

        # 장중 여부 확인
        is_weekday   = now_kst.weekday() < 5
        is_open_time = MARKET_OPEN <= (now_kst.hour, now_kst.minute) <= MARKET_CLOSE
        is_market    = is_weekday and is_open_time

        if not is_market:
            wait = 60 if is_weekday else 300
            logger.info(f"장외 시간 — {wait}초 대기")
            await asyncio.sleep(wait)
            continue

        # 종목 목록 갱신 (시작 시 또는 1시간마다)
        if time.time() - last_stock_load > 3600:
            rows = await db.fetch(
                "SELECT code, name FROM stocks WHERE is_active = TRUE ORDER BY code"
            )
            stock_map = {r["code"]: r["name"] for r in rows}
            last_stock_load = time.time()
            logger.info(f"종목 목록 갱신: {len(stock_map):,}개")

        if not stock_map:
            logger.warning("종목 없음, 60초 대기")
            await asyncio.sleep(60)
            continue

        cycle_start = time.time()
        detected = await scan_cycle(db, auth, stock_map)
        elapsed  = time.time() - cycle_start

        logger.info(f"스캔 완료: {len(stock_map):,}종목, 탐지 {detected}건, 소요 {elapsed:.1f}초")

        # KIS API 한도 고려: 사이클이 짧으면 최소 간격 보장
        sleep_time = max(0, SCAN_INTERVAL_SEC - elapsed)
        if sleep_time > 0:
            await asyncio.sleep(sleep_time)


if __name__ == "__main__":
    asyncio.run(main())

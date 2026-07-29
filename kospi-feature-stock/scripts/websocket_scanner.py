"""
KIS WebSocket 실시간 스캐너 — H0STCNT0 (체결가) 구독
크론: */5 0-6 * * 1-5  (UTC 00:00~06:30 = KST 09:00~15:30, 5분 간격)

동작:
  1. approval_key 발급 (POST /oauth2/Approval)
  2. Supabase stocks에서 거래량 상위 종목 선정 (KOSPI 10 + KOSDAQ 10)
  3. H0STCNT0 구독 → 실시간 ACML_VOL 모니터링
  4. 급등 감지(거래량 전일비 VOL_RATIO_MIN배 이상 & 등락률 CHANGE_MIN% 이상) 시
     → Supabase 이력으로 ML 스코어링 → Telegram 즉시 전송
  5. PINGPONG 자동 응답, 5분 후 자동 종료 (크론 재실행으로 구독 갱신)

설치 추가 패키지: websockets (pip install websockets)
환경변수: POSTGRES_DSN, KIS_APP_KEY, KIS_APP_SECRET, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
"""
import asyncio
import asyncpg
import json
import logging
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

try:
    import websockets
except ImportError:
    print("websockets 패키지 필요: pip install websockets")
    sys.exit(1)

load_dotenv(os.path.expanduser("~/.env"))

# market_scan.py 공통 함수 재사용
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from market_scan import (   # noqa: E402
    load_models, compute_features, add_rank_features, ml_score,
    fetch_history, fetch_kospi_index, fetch_financials, save_recommendations,
    send_telegram, _s, HISTORY_DAYS, DSN, TG_TOKEN, TG_CHAT,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ws_scanner")

KST     = timezone(timedelta(hours=9))
NOW     = datetime.now(KST)
TODAY_D = NOW.date()

APP_KEY    = os.environ["KIS_APP_KEY"]
APP_SECRET = os.environ["KIS_APP_SECRET"]
KIS_REST   = "https://openapi.koreainvestment.com:9443"
WS_URL     = "ws://ops.koreainvestment.com:21000"

SCORE_THRESHOLD = float(os.environ.get("SCORE_THRESHOLD", "0.27"))
RISK_THRESHOLD  = float(os.environ.get("RISK_THRESHOLD", "0.55"))
VOL_RATIO_MIN   = float(os.environ.get("SIGNAL_VOL_RATIO", "2.0"))
CHANGE_MIN      = float(os.environ.get("SIGNAL_CHANGE_MIN", "3.0"))
COOLDOWN_FILE   = Path(os.path.expanduser("~/quant/ws_cooldown.json"))
COOLDOWN_MINS   = int(os.environ.get("COOLDOWN_MINS", "60"))
MAX_STOCKS      = 20    # KIS 현재 한도
RUN_SECONDS     = 270   # 5분 이내 종료 (크론 재실행 전 자동 정리)

# 동적 임계값 반영
_DYN_CFG = Path(os.path.expanduser("~/quant/dynamic_config.json"))
if _DYN_CFG.exists():
    try:
        _d = json.loads(_DYN_CFG.read_text())
        if "score_threshold" in _d:
            SCORE_THRESHOLD = float(_d["score_threshold"])
    except Exception:
        pass

# H0STCNT0 응답 필드 순서 (48개, ^ 구분)
_FIELDS = [
    "MKSC_SHRN_ISCD", "STCK_CNTG_HOUR", "STCK_PRPR", "PRDY_VRSS_SIGN",
    "PRDY_VRSS", "PRDY_CTRT", "WGHN_AVRG_STCK_PRC", "STCK_OPRC",
    "STCK_HGPR", "STCK_LWPR", "ASKP1", "BIDP1", "CNTG_VOL", "ACML_VOL",
    "ACML_TR_PBMN", "SELN_CNTG_CSNU", "SHNU_CNTG_CSNU", "NTBY_CNTG_CSNU",
    "CTTR", "SELN_CNTG_SMTN", "SHNU_CNTG_SMTN", "CCLD_DVSN", "SHNU_RATE",
    "PRDY_VOL_VRSS_ACML_VOL_RATE", "OPRC_HOUR", "OPRC_VRSS_PRPR_SIGN",
    "OPRC_VRSS_PRPR", "HGPR_HOUR", "HGPR_VRSS_PRPR_SIGN", "HGPR_VRSS_PRPR",
    "LWPR_HOUR", "LWPR_VRSS_PRPR_SIGN", "LWPR_VRSS_PRPR", "BSOP_DATE",
    "NEW_MKOP_CLS_CODE", "TRHT_YN", "ASKP_RSQN1", "BIDP_RSQN1",
    "TOTAL_ASKP_RSQN", "TOTAL_BIDP_RSQN", "VOL_TNRT",
    "PRDY_SMNS_HOUR_ACML_VOL", "PRDY_SMNS_HOUR_ACML_VOL_RATE",
    "HOUR_CLS_CODE", "MRKT_TRTM_CLS_CODE", "VI_STND_PRC",
]


# ── KIS 인증 ─────────────────────────────────────────────────

_TOKEN_CACHE: dict = {}

def _rest_token() -> str:
    if _TOKEN_CACHE.get("exp", 0) > time.time() + 60:
        return _TOKEN_CACHE["tok"]
    body = json.dumps({
        "grant_type": "client_credentials",
        "appkey":     APP_KEY,
        "appsecret":  APP_SECRET,
    }).encode()
    req = urllib.request.Request(
        f"{KIS_REST}/oauth2/tokenP", data=body,
        headers={"content-type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read())
    _TOKEN_CACHE.update({"tok": d["access_token"], "exp": time.time() + 23 * 3600})
    return _TOKEN_CACHE["tok"]


def get_approval_key() -> str:
    """WebSocket 전용 approval_key 발급"""
    body = json.dumps({
        "grant_type": "client_credentials",
        "appkey":     APP_KEY,
        "secretkey":  APP_SECRET,
    }).encode()
    req = urllib.request.Request(
        f"{KIS_REST}/oauth2/Approval", data=body,
        headers={"content-type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read())
    key = d.get("approval_key", "")
    if not key:
        raise RuntimeError(f"approval_key 발급 실패: {d}")
    log.info("WebSocket approval_key 발급 완료")
    return key


# ── 종목 선정 ─────────────────────────────────────────────────

async def pick_top_stocks(conn: asyncpg.Connection) -> list[tuple[str, str, str]]:
    """
    거래량 기준 KOSPI 상위 10 + KOSDAQ 상위 10 선정.
    반환: [(code, market, name), ...]
    """
    rows = await conn.fetch("""
        SELECT d.code,
               COALESCE(s.market, 'KOSPI') AS market,
               COALESCE(s.name,   d.code)  AS name,
               d.volume
        FROM daily_bars d
        JOIN stocks s ON s.code = d.code AND s.is_active = true
        WHERE d.date = (SELECT MAX(date) FROM daily_bars WHERE code = d.code AND date < CURRENT_DATE)
          AND d.volume > 0
        ORDER BY d.volume DESC
        LIMIT 200
    """)
    kospi  = [(r["code"], r["market"], r["name"]) for r in rows if r["market"] == "KOSPI"][:10]
    kosdaq = [(r["code"], r["market"], r["name"]) for r in rows if r["market"] == "KOSDAQ"][:10]
    picks  = kospi + kosdaq
    log.info(f"구독 선정: KOSPI {len(kospi)} + KOSDAQ {len(kosdaq)} = {len(picks)}종목")
    return picks


# ── 쿨다운 ───────────────────────────────────────────────────

def load_cooldown() -> dict:
    if COOLDOWN_FILE.exists():
        try:
            return json.loads(COOLDOWN_FILE.read_text())
        except Exception:
            pass
    return {}


def save_cooldown(cd: dict) -> None:
    COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
    cutoff = (NOW - timedelta(minutes=COOLDOWN_MINS)).isoformat()
    COOLDOWN_FILE.write_text(json.dumps(
        {k: v for k, v in cd.items() if v >= cutoff},
        ensure_ascii=False,
    ))


def in_cooldown(code: str, cd: dict) -> bool:
    cutoff = (NOW - timedelta(minutes=COOLDOWN_MINS)).isoformat()
    return cd.get(code, "") >= cutoff


# ── 메시지 파싱 ───────────────────────────────────────────────

def parse_h0stcnt0(raw: str) -> dict | None:
    """'0|H0STCNT0|1|field1^field2^...' → dict"""
    try:
        parts = raw.split("|", 3)
        if len(parts) < 4 or parts[1] != "H0STCNT0":
            return None
        vals = parts[3].split("^")
        if len(vals) < len(_FIELDS):
            return None
        return dict(zip(_FIELDS, vals))
    except Exception:
        return None


# ── ML 스코어링 파이프라인 ────────────────────────────────────

async def score_and_alert(
    data: dict, stock_info: dict,
    conn: asyncpg.Connection, models: dict, feature_cols: list,
    cooldown: dict,
) -> bool:
    """급등 감지 종목 ML 스코어링 후 Telegram 알림. 추천 시 True 반환."""
    code   = data["MKSC_SHRN_ISCD"].strip()
    name   = stock_info.get(code, {}).get("name", code)
    market = stock_info.get(code, {}).get("market", "KOSPI")

    if in_cooldown(code, cooldown):
        return False

    price      = int(_s(data.get("STCK_PRPR")))
    open_p     = int(_s(data.get("STCK_OPRC"))) or price
    high_p     = int(_s(data.get("STCK_HGPR"))) or price
    low_p      = int(_s(data.get("STCK_LWPR"))) or price
    acml_vol   = int(_s(data.get("ACML_VOL")))
    acml_amt   = int(_s(data.get("ACML_TR_PBMN")))
    prdy_ctrt  = float(_s(data.get("PRDY_CTRT")))
    prev_vol_rate = float(_s(data.get("PRDY_VOL_VRSS_ACML_VOL_RATE")))  # 전일 동시간 대비 거래량 비율(%)
    vol_ratio  = prev_vol_rate / 100 + 1  # 2.0배 = 전일 동시간 대비 2배

    if price <= 0:
        return False

    today_row = {
        "code":        code,
        "name":        name,
        "close":       price,
        "open":        open_p,
        "high":        high_p,
        "low":         low_p,
        "volume":      acml_vol,
        "amount":      acml_amt,
        "change_rate": prdy_ctrt,
        "market":      market,
        "vol_ratio":   round(vol_ratio, 2),
    }

    from datetime import date as _date
    since    = TODAY_D - timedelta(days=HISTORY_DAYS + 10)
    hist     = await fetch_history(conn, [code], since)
    kospi_h  = await fetch_kospi_index(conn)
    fin_data = await fetch_financials(conn, [code])

    is_kosdaq = 1.0 if market == "KOSDAQ" else 0.0
    feats = compute_features(
        today_row, hist.get(code, []),
        is_kosdaq, kospi_h, feature_cols,
        fin=fin_data.get(code),
    )
    feats_list = add_rank_features([feats])
    probs, risks = ml_score(pd.DataFrame(feats_list), models, feature_cols)

    prob = float(probs[0])
    risk = float(risks[0])
    log.info(f"{code} {name}: prob={prob:.3f} risk={risk:.3f}")

    if prob < SCORE_THRESHOLD or risk > RISK_THRESHOLD:
        return False

    rec = {
        "code":            code,
        "name":            name,
        "success_prob":    round(prob, 4),
        "risk_score":      round(risk, 4),
        "expected_return": round((prob - 0.5) * 20.0, 2),
        "hold_days":       5,
        "close_price":     price,
        "change_rate":     round(prdy_ctrt, 2),
        "vol_ratio":       round(vol_ratio, 2),
    }

    conn2 = await asyncpg.connect(DSN, statement_cache_size=0)
    try:
        await save_recommendations(conn2, [rec])
    finally:
        await conn2.close()

    cooldown[code] = NOW.isoformat()

    chg_str = f"+{prdy_ctrt:.1f}%" if prdy_ctrt >= 0 else f"{prdy_ctrt:.1f}%"
    msg = (
        f"<b>⚡ 실시간 매수 추천</b> ({NOW.strftime('%H:%M')} KST)\n"
        f"• <b>{name}</b> ({code})"
        f"  확률 {prob:.0%}"
        f"  {chg_str}  거래량 {vol_ratio:.1f}x  ₩{price:,}"
    )
    await send_telegram(msg)
    log.info(f"추천 전송: {code} {name}")
    return True


# ── WebSocket 메인 ────────────────────────────────────────────

async def main():
    # 장 시간 확인 (KST 09:05 ~ 15:25)
    kst_min = NOW.hour * 60 + NOW.minute
    if not (545 <= kst_min <= 925):
        log.info(f"장 외 시간 ({NOW.strftime('%H:%M KST')}) — 스킵")
        return

    log.info(f"WebSocket 스캐너 시작 {NOW.strftime('%Y-%m-%d %H:%M KST')}")

    approval_key = get_approval_key()
    models, feature_cols = load_models()
    cooldown = load_cooldown()

    conn = await asyncpg.connect(DSN, statement_cache_size=0)
    try:
        stocks = await pick_top_stocks(conn)
    finally:
        await conn.close()

    if not stocks:
        log.warning("구독 종목 없음")
        return

    stock_info = {code: {"name": name, "market": mkt} for code, mkt, name in stocks}

    # 구독 메시지 생성
    def make_sub_msg(code: str) -> str:
        return json.dumps({
            "header": {
                "approval_key": approval_key,
                "custtype":     "P",
                "tr_type":      "1",
                "content-type": "utf-8",
            },
            "body": {"input": {"tr_id": "H0STCNT0", "tr_key": code}},
        })

    alert_queue: asyncio.Queue = asyncio.Queue()
    deadline = asyncio.get_event_loop().time() + RUN_SECONDS

    async def process_alerts():
        """alert_queue에서 ML 스코어링 순차 처리 (rate limit 보호)"""
        conn_ml = await asyncpg.connect(DSN, statement_cache_size=0)
        try:
            while True:
                try:
                    data = await asyncio.wait_for(alert_queue.get(), timeout=5.0)
                except asyncio.TimeoutError:
                    if asyncio.get_event_loop().time() >= deadline:
                        break
                    continue
                try:
                    await score_and_alert(
                        data, stock_info, conn_ml, models, feature_cols, cooldown
                    )
                except Exception as e:
                    log.error(f"ML 스코어링 오류: {e}")
                await asyncio.sleep(0.1)
        finally:
            await conn_ml.close()

    async def ws_listener():
        """WebSocket 연결 및 수신 루프"""
        try:
            async with websockets.connect(
                WS_URL,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5,
            ) as ws:
                log.info(f"WebSocket 연결: {WS_URL}")

                # 종목 구독 등록
                for code, _, _ in stocks:
                    await ws.send(make_sub_msg(code))
                    await asyncio.sleep(0.02)
                log.info(f"{len(stocks)}종목 구독 등록 완료")

                async for raw_msg in ws:
                    if asyncio.get_event_loop().time() >= deadline:
                        log.info("실행 시간 초과 — 종료")
                        break

                    # PINGPONG 처리
                    if isinstance(raw_msg, str) and raw_msg[0] not in ("0", "1"):
                        try:
                            sys_msg = json.loads(raw_msg)
                            if sys_msg.get("header", {}).get("tr_id") == "PINGPONG":
                                await ws.pong(raw_msg)
                        except Exception:
                            pass
                        continue

                    # 체결 데이터 파싱
                    parsed = parse_h0stcnt0(raw_msg)
                    if not parsed:
                        continue

                    code       = parsed.get("MKSC_SHRN_ISCD", "").strip()
                    prdy_ctrt  = float(_s(parsed.get("PRDY_CTRT")))
                    vol_pct    = float(_s(parsed.get("PRDY_VOL_VRSS_ACML_VOL_RATE")))
                    vol_ratio  = vol_pct / 100 + 1

                    # 급등 조건 필터
                    if vol_ratio >= VOL_RATIO_MIN or prdy_ctrt >= CHANGE_MIN:
                        if code and not in_cooldown(code, cooldown):
                            await alert_queue.put(parsed)

        except Exception as e:
            log.error(f"WebSocket 오류: {e}")

    await asyncio.gather(ws_listener(), process_alerts())
    save_cooldown(cooldown)
    log.info("WebSocket 스캐너 종료")


if __name__ == "__main__":
    asyncio.run(main())

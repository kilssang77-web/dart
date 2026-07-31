"""
실시간 매수 추천 파이프라인 — GCP e2-micro 상시 데몬 (systemd)

대체 대상:
  - websocket_scanner.py (5분 cron → 영구 연결 유지)
  - intraday_scan.py     (10분 cron → 30분 REST 보조 스캔)
  - send_telegram_alerts.py / telegram-alert.yml (즉시 발송)

동작:
  1. KIS WebSocket H0STCNT0 영구 연결 (재연결 자동)
  2. 거래량 급등 / 등락률 기준 실시간 탐지 → 즉시 ML 스코어링 → Telegram
  3. 30분마다 REST 거래량 순위 보조 스캔 (WebSocket 미구독 종목 보완)
  4. 30분마다 구독 종목 갱신 (상위 20종목 재선정, 연결은 유지)
  5. approval_key 11시간마다 자동 갱신

환경변수: POSTGRES_DSN, KIS_APP_KEY, KIS_APP_SECRET,
          TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
          SCORE_THRESHOLD (기본 0.27), RISK_THRESHOLD (기본 0.55)
          SIGNAL_VOL_RATIO (기본 2.0), SIGNAL_CHANGE_MIN (기본 3.0)
          WS_MAX_STOCKS (기본 20), COOLDOWN_MINS (기본 60)

설치: pip install websockets asyncpg lightgbm numpy pandas python-dotenv
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg
import numpy as np
import pandas as pd
from dotenv import load_dotenv

try:
    import websockets
except ImportError:
    print("websockets 필요: pip install websockets", flush=True)
    sys.exit(1)

load_dotenv(os.path.expanduser("~/.env"))

# market_scan.py 공통 함수 재사용
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from market_scan import (  # noqa: E402
    load_models, compute_features, add_rank_features, ml_score,
    fetch_history, fetch_kospi_index, fetch_financials, save_recommendations,
    send_telegram, _s, HISTORY_DAYS, DSN,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.expanduser("~/quant/realtime_pipeline.log"),
            encoding="utf-8",
        ),
    ],
)
log = logging.getLogger("realtime")

KST = timezone(timedelta(hours=9))

APP_KEY    = os.environ["KIS_APP_KEY"]
APP_SECRET = os.environ["KIS_APP_SECRET"]
KIS_REST   = "https://openapi.koreainvestment.com:9443"
WS_URL     = "ws://ops.koreainvestment.com:21000"

SCORE_THRESHOLD  = float(os.environ.get("SCORE_THRESHOLD", "0.27"))
RISK_THRESHOLD   = float(os.environ.get("RISK_THRESHOLD", "0.55"))
VOL_RATIO_MIN    = float(os.environ.get("SIGNAL_VOL_RATIO", "2.0"))
CHANGE_MIN       = float(os.environ.get("SIGNAL_CHANGE_MIN", "3.0"))
MAX_STOCKS       = int(os.environ.get("WS_MAX_STOCKS", "20"))
COOLDOWN_MINS    = int(os.environ.get("COOLDOWN_MINS", "60"))
COOLDOWN_FILE    = Path(os.path.expanduser("~/quant/realtime_cooldown.json"))
DYN_CFG          = Path(os.path.expanduser("~/quant/dynamic_config.json"))

# REST 보조 스캔 주기 (초)
REST_SCAN_INTERVAL  = int(os.environ.get("REST_SCAN_INTERVAL", "1800"))
# 구독 종목 갱신 주기 (초)
STOCK_REFRESH_INTERVAL = int(os.environ.get("STOCK_REFRESH_INTERVAL", "1800"))
# approval_key 갱신 주기 (초) — KIS 유효기간 12h, 여유 1h
APPROVAL_KEY_INTERVAL = int(os.environ.get("APPROVAL_KEY_INTERVAL", "39600"))  # 11h

# H0STCNT0 응답 필드 순서
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
_MIN_FIELDS = 14


def _is_trading_time() -> bool:
    now = datetime.now(KST)
    m   = now.hour * 60 + now.minute
    return now.weekday() < 5 and 540 <= m <= 930  # KST 09:00~15:30


def _load_dynamic_threshold():
    global SCORE_THRESHOLD
    if DYN_CFG.exists():
        try:
            d = json.loads(DYN_CFG.read_text())
            if "score_threshold" in d:
                SCORE_THRESHOLD = float(d["score_threshold"])
        except Exception:
            pass


# ── KIS 인증 ─────────────────────────────────────────────────────────────

_token_cache: dict = {}


def _get_rest_token() -> str:
    if _token_cache.get("exp", 0) > time.time() + 60:
        return _token_cache["tok"]
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
    _token_cache.update({"tok": d["access_token"], "exp": time.time() + 23 * 3600})
    log.info("KIS REST 토큰 발급")
    return _token_cache["tok"]


def _get_approval_key() -> str:
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
    log.info("WebSocket approval_key 발급")
    return key


# ── 쿨다운 ───────────────────────────────────────────────────────────────

def _load_cooldown() -> dict:
    if COOLDOWN_FILE.exists():
        try:
            return json.loads(COOLDOWN_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_cooldown(cd: dict) -> None:
    now    = datetime.now(KST)
    cutoff = (now - timedelta(minutes=COOLDOWN_MINS)).isoformat()
    COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
    COOLDOWN_FILE.write_text(json.dumps(
        {k: v for k, v in cd.items() if v >= cutoff},
        ensure_ascii=False,
    ))


def _in_cooldown(code: str, cd: dict) -> bool:
    now    = datetime.now(KST)
    cutoff = (now - timedelta(minutes=COOLDOWN_MINS)).isoformat()
    return cd.get(code, "") >= cutoff


# ── WebSocket 파싱 ───────────────────────────────────────────────────────

def _parse_h0stcnt0(raw: str) -> dict | None:
    try:
        parts = raw.split("|", 3)
        if len(parts) < 4 or parts[1] != "H0STCNT0":
            return None
        vals = parts[3].split("^")
        if len(vals) < _MIN_FIELDS:
            return None
        n = min(len(vals), len(_FIELDS))
        return dict(zip(_FIELDS[:n], vals[:n]))
    except Exception:
        return None


# ── KIS REST 헬퍼 ────────────────────────────────────────────────────────

def _kis_get(path: str, tr_id: str, params: dict) -> dict:
    qs  = "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(
        f"{KIS_REST}{path}?{qs}",
        headers={
            "authorization": f"Bearer {_get_rest_token()}",
            "appkey":        APP_KEY,
            "appsecret":     APP_SECRET,
            "tr_id":         tr_id,
            "content-type":  "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def _fetch_volume_rank(market_div: str) -> list[dict]:
    try:
        d = _kis_get(
            "/uapi/domestic-stock/v1/quotations/volume-rank",
            "FHPST01710000",
            {
                "FID_COND_MRKT_DIV_CODE": market_div,
                "FID_COND_SCR_DIV_CODE":  "20171",
                "FID_INPUT_ISCD":          "0000",
                "FID_DIV_CLS_CODE":        "0",
                "FID_BLNG_CLS_CODE":       "0",
                "FID_TRGT_CLS_CODE":       "111111111",
                "FID_TRGT_EXLS_CLS_CODE":  "000000",
                "FID_INPUT_PRICE_1":        "",
                "FID_INPUT_PRICE_2":        "",
                "FID_VOL_CNT":              "10000",
                "FID_INPUT_DATE_1":         "",
            },
        )
        if d.get("rt_cd") != "0":
            log.warning(f"volume-rank({market_div}) 실패: {d.get('msg1','')}")
            return []
        return d.get("output", [])
    except Exception as e:
        log.warning(f"volume-rank({market_div}) 오류: {e}")
        return []


def _fetch_current_price(code: str, mkt_div: str = "J") -> dict | None:
    try:
        d = _kis_get(
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            "FHKST01010100",
            {"FID_COND_MRKT_DIV_CODE": mkt_div, "FID_INPUT_ISCD": code},
        )
        if d.get("rt_cd") != "0":
            return None
        out = d.get("output", {})
        c = int(_s(out.get("stck_prpr")))
        return {
            "open":        int(_s(out.get("stck_oprc"))) or c,
            "high":        int(_s(out.get("stck_hgpr"))) or c,
            "low":         int(_s(out.get("stck_lwpr"))) or c,
            "close":       c,
            "volume":      int(_s(out.get("acml_vol"))),
            "amount":      int(_s(out.get("acml_tr_pbmn"))),
            "change_rate": float(_s(out.get("prdy_ctrt"))),
        } if c > 0 else None
    except Exception as e:
        log.debug(f"현재가 조회 실패({code}): {e}")
        return None


# ── DB 저장 (전체 컬럼 버전) ─────────────────────────────────────────────

async def _save_rec_full(conn: asyncpg.Connection, rec: dict) -> None:
    rationale = rec.get("rationale", "{}")
    if isinstance(rationale, dict):
        rationale = json.dumps(rationale, ensure_ascii=False)
    try:
        await conn.execute("""
            INSERT INTO recommendations
                (code, action, entry_price, entry_price_low, entry_price_high,
                 target_price, stop_loss_price, risk_reward_ratio,
                 success_prob, risk_score, expected_return,
                 expected_hold_days, rationale)
            VALUES ($1,'BUY',$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::JSONB)
        """,
            rec["code"],
            rec.get("entry_price", rec.get("close_price", 0)),
            rec.get("entry_price", rec.get("close_price", 0)),
            rec.get("entry_price", rec.get("close_price", 0)),
            rec.get("target_price", 0),
            rec.get("stop_loss_price", 0),
            rec.get("risk_reward_ratio", 0),
            rec["success_prob"],
            rec["risk_score"],
            rec["expected_return"],
            rec.get("hold_days", 5),
            rationale,
        )
    except Exception as e:
        log.error(f"추천 저장 실패 [{rec['code']}]: {e}")


# ── ML 스코어링 + 저장 + 알림 ────────────────────────────────────────────

async def _score_and_alert(
    today_row: dict,
    pool: asyncpg.Pool,
    models: dict,
    feature_cols: list,
    cooldown: dict,
) -> bool:
    """ML 점수화 → DB 저장 → Telegram 즉시 발송. 추천 시 True."""
    code  = today_row["code"]
    now   = datetime.now(KST)
    today = now.date()

    if _in_cooldown(code, cooldown):
        return False

    from datetime import timedelta as _td
    since = today - _td(days=HISTORY_DAYS + 10)

    async with pool.acquire() as conn:
        hist     = await fetch_history(conn, [code], since)
        kospi_h  = await fetch_kospi_index(conn)
        fin_data = await fetch_financials(conn, [code])

    market    = today_row.get("market", "KOSPI")
    is_kosdaq = 1.0 if market == "KOSDAQ" else 0.0

    feats = compute_features(
        today_row, hist.get(code, []),
        is_kosdaq, kospi_h, feature_cols,
        fin=fin_data.get(code),
    )
    feats_list   = add_rank_features([feats])
    probs, risks = ml_score(pd.DataFrame(feats_list), models, feature_cols)

    prob = float(probs[0])
    risk = float(risks[0])
    log.info(f"ML [{code}] prob={prob:.3f} risk={risk:.3f}")

    if prob < SCORE_THRESHOLD or risk > RISK_THRESHOLD:
        return False

    price      = today_row["close"]
    entry      = price
    target     = round(entry * 1.10)
    stop_loss  = round(entry * 0.95)
    rr         = round((target - entry) / (entry - stop_loss), 2) if entry > stop_loss else 0

    grade = "A" if prob >= 0.40 else ("B" if prob >= 0.32 else "C")
    chg   = today_row.get("change_rate", 0.0)
    vr    = today_row.get("vol_ratio", 1.0)

    rec = {
        "code":            code,
        "name":            today_row.get("name", code),
        "success_prob":    round(prob, 4),
        "risk_score":      round(risk, 4),
        "expected_return": round((prob - 0.5) * 20.0, 2),
        "hold_days":       5,
        "close_price":     price,
        "change_rate":     round(chg, 2),
        "vol_ratio":       round(vr, 2),
        "entry_price":     entry,
        "target_price":    target,
        "stop_loss_price": stop_loss,
        "risk_reward_ratio": rr,
        "confidence_grade": grade,
        "rationale": json.dumps({
            "event_type": "realtime_ws" if today_row.get("_source") == "ws" else "volume_rank",
            "vol_ratio":  round(vr, 2),
        }, ensure_ascii=False),
    }

    async with pool.acquire() as conn:
        await _save_rec_full(conn, rec)

    cooldown[code] = now.isoformat()
    _save_cooldown(cooldown)

    chg_str = f"+{chg:.1f}%" if chg >= 0 else f"{chg:.1f}%"
    target_pct = (target / entry - 1) * 100 if entry > 0 else 0
    stop_pct   = (stop_loss / entry - 1) * 100 if entry > 0 else 0
    msg = (
        f"🚨 <b>[실시간 매수 추천]</b> {today_row.get('name', code)} ({code})"
        f"  {now.strftime('%H:%M')}\n"
        f"진입가:  <b>₩{entry:,}</b>  ({chg_str} | 거래량 {vr:.1f}x)\n"
        f"목표가:  ₩{target:,}  (<b>+{target_pct:.1f}%</b>)\n"
        f"손절가:  ₩{stop_loss:,}  ({stop_pct:.1f}%)\n"
        f"R:R {rr:.2f}  |  신뢰도: <b>{grade}</b>  |  확률: {prob:.1%}"
    )
    await send_telegram(msg)
    log.info(f"추천 발송: {code} {today_row.get('name', '')} prob={prob:.3f}")
    return True


# ── 구독 종목 선정 ────────────────────────────────────────────────────────

async def _pick_top_stocks(pool: asyncpg.Pool) -> list[tuple[str, str, str]]:
    today_kst = datetime.now(KST).date()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            WITH latest AS (
                SELECT code, MAX(date) AS last_date
                FROM daily_bars WHERE date < $1 GROUP BY code
            ),
            ranked AS (
                SELECT d.code,
                       COALESCE(s.market,'KOSPI') AS market,
                       COALESCE(s.name, d.code)   AS name,
                       d.volume,
                       ROW_NUMBER() OVER (
                           PARTITION BY COALESCE(s.market,'KOSPI')
                           ORDER BY d.volume DESC
                       ) AS rn
                FROM daily_bars d
                JOIN latest l ON l.code = d.code AND l.last_date = d.date
                JOIN stocks  s ON s.code = d.code AND s.is_active = true
                WHERE d.volume > 0
            )
            SELECT code, market, name FROM ranked WHERE rn <= 10
            ORDER BY market, rn
        """, today_kst)
    stocks = [(r["code"], r["market"], r["name"]) for r in rows]
    kospi  = [(c, m, n) for c, m, n in stocks if m == "KOSPI"]
    kosdaq = [(c, m, n) for c, m, n in stocks if m == "KOSDAQ"]
    picks  = (kospi + kosdaq)[:MAX_STOCKS]
    log.info(f"구독 선정: KOSPI {len(kospi)} + KOSDAQ {len(kosdaq)} = {len(picks)}")
    return picks


# ── 메인 파이프라인 클래스 ────────────────────────────────────────────────

class RealtimePipeline:
    def __init__(self):
        self.models:       dict  = {}
        self.feature_cols: list  = []
        self.pool:         asyncpg.Pool | None = None
        self.cooldown:     dict  = {}
        self.stock_info:   dict  = {}   # code → {name, market}
        self.subscribed:   set   = set()
        self.approval_key: str   = ""
        self.approval_ts:  float = 0.0
        self._ws_send_queue: asyncio.Queue | None = None

    # ── 초기화 ──────────────────────────────────────────────────────────

    async def setup(self):
        log.info("파이프라인 초기화 시작")
        self.pool = await asyncpg.create_pool(
            DSN, min_size=2, max_size=5, statement_cache_size=0
        )
        self.models, self.feature_cols = load_models()
        self.cooldown = _load_cooldown()
        _load_dynamic_threshold()
        await self._refresh_stocks()
        self._renew_approval_key()
        log.info("파이프라인 초기화 완료")

    def _renew_approval_key(self):
        self.approval_key = _get_approval_key()
        self.approval_ts  = time.time()

    # ── 구독 갱신 ────────────────────────────────────────────────────────

    async def _refresh_stocks(self):
        picks = await _pick_top_stocks(self.pool)
        self.stock_info = {code: {"name": name, "market": mkt}
                           for code, mkt, name in picks}
        new_set = set(self.stock_info.keys())
        added   = new_set - self.subscribed
        removed = self.subscribed - new_set

        if self._ws_send_queue and added:
            for code in added:
                await self._ws_send_queue.put(("subscribe", code))
            log.info(f"구독 추가: {len(added)}종목")
        if removed:
            log.info(f"구독 해제 대상: {len(removed)}종목 (연결 유지)")

        self.subscribed = new_set
        log.info(f"구독 현황: {len(self.subscribed)}종목")

    # ── WebSocket 태스크 ─────────────────────────────────────────────────

    async def ws_task(self):
        RECONNECT_DELAY = 30
        while True:
            try:
                await self._ws_connect()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.error(f"WebSocket 오류 — {RECONNECT_DELAY}초 후 재연결: {e}")
            await asyncio.sleep(RECONNECT_DELAY)

    async def _ws_connect(self):
        if time.time() - self.approval_ts > APPROVAL_KEY_INTERVAL:
            self._renew_approval_key()

        send_queue: asyncio.Queue = asyncio.Queue()
        self._ws_send_queue = send_queue

        alert_queue: asyncio.Queue = asyncio.Queue()

        def _sub_msg(code: str) -> str:
            return json.dumps({
                "header": {
                    "approval_key": self.approval_key,
                    "custtype":     "P",
                    "tr_type":      "1",
                    "content-type": "utf-8",
                },
                "body": {"input": {"tr_id": "H0STCNT0", "tr_key": code}},
            })

        async with websockets.connect(
            WS_URL,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
            max_size=2**20,
        ) as ws:
            log.info(f"WebSocket 연결 성공: {WS_URL}")

            # 초기 구독
            for code in self.subscribed:
                await ws.send(_sub_msg(code))
                await asyncio.sleep(0.02)
            log.info(f"{len(self.subscribed)}종목 초기 구독 완료")

            async def sender():
                while True:
                    try:
                        action, code = await asyncio.wait_for(
                            send_queue.get(), timeout=1.0
                        )
                        if action == "subscribe":
                            await ws.send(_sub_msg(code))
                    except asyncio.TimeoutError:
                        pass
                    except Exception as e:
                        log.debug(f"sender 오류: {e}")
                        break

            async def receiver():
                async for raw in ws:
                    if isinstance(raw, bytes):
                        continue
                    # PINGPONG 처리
                    if raw and raw[0] not in ("0", "1"):
                        try:
                            hdr = json.loads(raw).get("header", {})
                            if hdr.get("tr_id") == "PINGPONG":
                                await ws.send(raw)
                        except Exception:
                            pass
                        continue

                    parsed = _parse_h0stcnt0(raw)
                    if not parsed:
                        continue

                    code      = parsed.get("MKSC_SHRN_ISCD", "").strip()
                    prdy_ctrt = float(_s(parsed.get("PRDY_CTRT")))
                    vol_pct   = float(_s(parsed.get("PRDY_VOL_VRSS_ACML_VOL_RATE")))
                    vol_ratio = vol_pct / 100 + 1

                    if (
                        code
                        and (vol_ratio >= VOL_RATIO_MIN or prdy_ctrt >= CHANGE_MIN)
                        and _is_trading_time()
                        and not _in_cooldown(code, self.cooldown)
                    ):
                        await alert_queue.put((parsed, "ws"))

            async def alert_processor():
                while True:
                    try:
                        item, source = await asyncio.wait_for(
                            alert_queue.get(), timeout=5.0
                        )
                    except asyncio.TimeoutError:
                        continue
                    except Exception:
                        break

                    try:
                        parsed = item
                        code   = parsed.get("MKSC_SHRN_ISCD", "").strip()
                        info   = self.stock_info.get(code, {})
                        price  = int(_s(parsed.get("STCK_PRPR")))
                        if price <= 0:
                            continue

                        today_row = {
                            "code":        code,
                            "name":        info.get("name", code),
                            "close":       price,
                            "open":        int(_s(parsed.get("STCK_OPRC"))) or price,
                            "high":        int(_s(parsed.get("STCK_HGPR"))) or price,
                            "low":         int(_s(parsed.get("STCK_LWPR"))) or price,
                            "volume":      int(_s(parsed.get("ACML_VOL"))),
                            "amount":      int(_s(parsed.get("ACML_TR_PBMN"))),
                            "change_rate": float(_s(parsed.get("PRDY_CTRT"))),
                            "market":      info.get("market", "KOSPI"),
                            "vol_ratio":   float(_s(parsed.get("PRDY_VOL_VRSS_ACML_VOL_RATE"))) / 100 + 1,
                            "_source":     source,
                        }
                        _load_dynamic_threshold()
                        await _score_and_alert(
                            today_row, self.pool,
                            self.models, self.feature_cols,
                            self.cooldown,
                        )
                    except Exception as e:
                        log.error(f"alert_processor 오류 [{code}]: {e}")

            await asyncio.gather(sender(), receiver(), alert_processor())

    # ── REST 보조 스캔 태스크 ────────────────────────────────────────────

    async def rest_scan_task(self):
        """30분마다 KIS REST 거래량 순위 스캔 (WebSocket 미구독 종목 보완)"""
        await asyncio.sleep(300)  # 시작 5분 후 첫 실행
        while True:
            if _is_trading_time():
                try:
                    await self._run_rest_scan()
                except Exception as e:
                    log.error(f"REST 스캔 오류: {e}")
            await asyncio.sleep(REST_SCAN_INTERVAL)

    async def _run_rest_scan(self):
        now = datetime.now(KST)
        log.info(f"REST 스캔 시작 {now.strftime('%H:%M KST')}")

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT code, market FROM stocks WHERE is_active = true"
            )
        valid_codes = {r["code"]: r["market"] for r in rows}

        raw_items: list[dict] = []
        for mkt_div, mkt_name in [("J", "KOSPI"), ("Q", "KOSDAQ")]:
            items = await asyncio.to_thread(_fetch_volume_rank, mkt_div)
            for it in items:
                it["_market"] = mkt_name
            raw_items.extend(items)
            if mkt_div == "Q" and not items:
                log.info("KOSDAQ volume-rank 미지원 — KOSPI 결과만 사용")

        candidates: list[str]  = []
        today_rows: dict       = {}

        for item in raw_items:
            code = item.get("mksc_shrn_iscd", "").strip()
            if not code or len(code) != 6 or code not in valid_codes:
                continue
            if _in_cooldown(code, self.cooldown):
                continue

            price     = _s(item.get("stck_prpr"))
            vol_inrt  = _s(item.get("vol_inrt"))
            prdy_ctrt = _s(item.get("prdy_ctrt"))
            vol_ratio = vol_inrt / 100 + 1

            if price <= 0:
                continue
            if vol_ratio < VOL_RATIO_MIN and prdy_ctrt < CHANGE_MIN:
                continue

            candidates.append(code)
            today_rows[code] = {
                "code":        code,
                "name":        item.get("hts_kor_isnm", code),
                "close":       int(price),
                "open":        int(price),
                "high":        int(price),
                "low":         int(price),
                "volume":      int(_s(item.get("acml_vol"))),
                "amount":      int(_s(item.get("acml_tr_pbmn", 0))),
                "change_rate": prdy_ctrt,
                "market":      item["_market"],
                "vol_ratio":   round(vol_ratio, 2),
                "_source":     "rest",
            }

        if not candidates:
            log.info("REST 스캔: 신호 없음")
            return

        # 개별 OHLCV 보완
        for code in candidates:
            mkt_div  = "J" if valid_codes.get(code) == "KOSPI" else "Q"
            price_dat = await asyncio.to_thread(_fetch_current_price, code, mkt_div)
            if price_dat:
                today_rows[code].update(price_dat)
            await asyncio.sleep(0.05)

        log.info(f"REST 스캔 후보: {len(candidates)}개")
        _load_dynamic_threshold()

        for code in candidates:
            try:
                await _score_and_alert(
                    today_rows[code], self.pool,
                    self.models, self.feature_cols,
                    self.cooldown,
                )
            except Exception as e:
                log.error(f"REST 스캔 ML 오류 [{code}]: {e}")
            await asyncio.sleep(0.1)

    # ── 구독 갱신 태스크 ────────────────────────────────────────────────

    async def stock_refresh_task(self):
        while True:
            await asyncio.sleep(STOCK_REFRESH_INTERVAL)
            try:
                await self._refresh_stocks()
            except Exception as e:
                log.error(f"구독 갱신 오류: {e}")

    # ── 실행 ─────────────────────────────────────────────────────────────

    async def run(self):
        await self.setup()
        log.info("실시간 파이프라인 실행 시작")

        # 장 외 시간에도 데몬은 살아있고, _is_trading_time() 체크로 처리
        try:
            await asyncio.gather(
                self.ws_task(),
                self.rest_scan_task(),
                self.stock_refresh_task(),
            )
        finally:
            if self.pool:
                await self.pool.close()
            _save_cooldown(self.cooldown)
            log.info("파이프라인 종료")


async def _main():
    pipeline = RealtimePipeline()
    await pipeline.run()


if __name__ == "__main__":
    log.info("=" * 60)
    log.info("실시간 매수 추천 파이프라인 시작")
    log.info("=" * 60)
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        log.info("사용자 중단")

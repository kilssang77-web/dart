"""
장 중 실시간 스캐너 — KIS 거래량 급등 순위 → Supabase 이력 → ML → Telegram
크론: */10 0-6 * * 1-5  (UTC 00:00~06:30 = KST 09:00~15:30, 10분 간격)

KIS REST /volume-rank 로 KOSPI 거래량 급등 종목 수신.
후보 종목별 /inquire-price 로 시가·고가·저가 실값 보완.
Supabase daily_bars 이력으로 75개 피처 계산 후 ML 스코어링.
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

load_dotenv(os.path.expanduser("~/.env"))

# market_scan.py 공통 함수 재사용
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from market_scan import (  # noqa: E402
    load_models, compute_features, add_rank_features, ml_score,
    fetch_history, fetch_kospi_index, fetch_financials, save_recommendations,
    send_telegram, _s, HISTORY_DAYS, MODEL_DIR, DSN, TG_TOKEN, TG_CHAT,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("intraday")

KST     = timezone(timedelta(hours=9))
NOW     = datetime.now(KST)
TODAY_D = NOW.date()

APP_KEY    = os.environ["KIS_APP_KEY"]
APP_SECRET = os.environ["KIS_APP_SECRET"]
KIS_BASE   = "https://openapi.koreainvestment.com:9443"

SCORE_THRESHOLD = float(os.environ.get("SCORE_THRESHOLD", "0.27"))
RISK_THRESHOLD  = float(os.environ.get("RISK_THRESHOLD", "0.55"))
VOL_RATIO_MIN   = float(os.environ.get("SIGNAL_VOL_RATIO", "2.0"))
CHANGE_MIN      = float(os.environ.get("SIGNAL_CHANGE_MIN", "3.0"))
COOLDOWN_MINS   = int(os.environ.get("COOLDOWN_MINS", "60"))
COOLDOWN_FILE   = Path(os.path.expanduser("~/quant/intraday_cooldown.json"))

_TOKEN_CACHE: dict = {}


# ── KIS REST ─────────────────────────────────────────────────────────

def _kis_token() -> str:
    if _TOKEN_CACHE.get("expires", 0) > time.time():
        return _TOKEN_CACHE["token"]
    body = json.dumps({
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
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
            "authorization": f"Bearer {_kis_token()}",
            "appkey": APP_KEY,
            "appsecret": APP_SECRET,
            "tr_id": tr_id,
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def fetch_current_price(code: str, mkt_div: str = "J") -> dict | None:
    """KIS 개별 종목 현재가·시가·고가·저가 실값 조회"""
    try:
        d = _kis_get(
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            "FHKST01010100",
            {"FID_COND_MRKT_DIV_CODE": mkt_div, "FID_INPUT_ISCD": code},
        )
        if d.get("rt_cd") != "0":
            return None
        out = d.get("output", {})
        o = int(_s(out.get("stck_oprc")))
        h = int(_s(out.get("stck_hgpr")))
        l = int(_s(out.get("stck_lwpr")))
        c = int(_s(out.get("stck_prpr")))
        if c <= 0:
            return None
        return {
            "open":        o if o > 0 else c,
            "high":        h if h > 0 else c,
            "low":         l if l > 0 else c,
            "close":       c,
            "volume":      int(_s(out.get("acml_vol"))),
            "amount":      int(_s(out.get("acml_tr_pbmn"))),
            "change_rate": _s(out.get("prdy_ctrt")),
        }
    except Exception as e:
        log.debug(f"개별가 조회 실패({code}): {e}")
        return None


def fetch_volume_rank(market_div: str) -> list[dict]:
    """KIS 거래량 급등 순위 (J=KOSPI, Q=KOSDAQ)"""
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
                "FID_INPUT_PRICE_1":       "",
                "FID_INPUT_PRICE_2":       "",
                "FID_VOL_CNT":             "10000",
                "FID_INPUT_DATE_1":        "",
            },
        )
        if d.get("rt_cd") != "0":
            log.warning(f"volume-rank 실패({market_div}): {d.get('msg1', '')}")
            return []
        items = d.get("output", [])
        log.info(f"volume-rank({market_div}): {len(items)}개")
        return items
    except Exception as e:
        log.warning(f"volume-rank 오류({market_div}): {e}")
        return []


# ── 쿨다운 ───────────────────────────────────────────────────────────

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


# ── 메인 ─────────────────────────────────────────────────────────────

async def main():
    # 장 시간 확인 (KST 09:05 ~ 15:25)
    kst_min = NOW.hour * 60 + NOW.minute
    if not (545 <= kst_min <= 925):
        log.info(f"장 외 시간 ({NOW.strftime('%H:%M KST')}) — 스킵")
        return

    log.info(f"장 중 스캔 시작 {NOW.strftime('%Y-%m-%d %H:%M KST')}")
    models, feature_cols = load_models()
    cooldown = load_cooldown()

    # Supabase 유효 종목 코드 사전 로드 (ETF·미수집 종목 제외용)
    conn = await asyncpg.connect(DSN, statement_cache_size=0)
    try:
        rows = await conn.fetch(
            "SELECT code, market FROM stocks WHERE is_active = true"
        )
        valid_codes_db = {r["code"]: r["market"] for r in rows}
    finally:
        await conn.close()
    log.info(f"Supabase 유효 종목: {len(valid_codes_db)}개")

    # KIS 거래량 급등 순위 수신 (KOSPI only — KOSDAQ TR 별도)
    raw_items: list[dict] = []
    for mkt_div, mkt_name in [("J", "KOSPI")]:
        items = fetch_volume_rank(mkt_div)
        for item in items:
            item["_market"] = mkt_name
        raw_items.extend(items)

    if not raw_items:
        log.warning("거래량 순위 데이터 없음")
        return

    # 신호 필터링 + today_row 구성
    candidates:  list[str]  = []
    today_rows:  dict       = {}

    for item in raw_items:
        # volume-rank 응답 종목코드 필드명: mksc_shrn_iscd
        code = item.get("mksc_shrn_iscd", "").strip()
        if not code or len(code) != 6:
            continue
        if code not in valid_codes_db:   # Supabase에 없으면 이력·피처 계산 불가
            continue
        if in_cooldown(code, cooldown):
            continue

        price     = _s(item.get("stck_prpr"))
        vol_inrt  = _s(item.get("vol_inrt"))    # 거래량 증가율 (%)
        prdy_ctrt = _s(item.get("prdy_ctrt"))   # 등락률 (%)
        vol_ratio = vol_inrt / 100 + 1           # 100% 증가 = 2.0배

        if price <= 0:
            continue
        if vol_ratio < VOL_RATIO_MIN and prdy_ctrt < CHANGE_MIN:
            continue

        candidates.append(code)
        today_rows[code] = {
            "code":        code,
            "name":        item.get("hts_kor_isnm", code),
            "close":       int(price),
            "open":        int(price),   # volume-rank 미제공 → 현재가로 대체
            "high":        int(price),
            "low":         int(price),
            "volume":      int(_s(item.get("acml_vol"))),
            "amount":      int(_s(item.get("acml_tr_pbmn", 0))),
            "change_rate": prdy_ctrt,
            "market":      item["_market"],
            "vol_ratio":   round(vol_ratio, 2),
        }

    log.info(f"신호 후보: {len(candidates)}개 (쿨다운 제외)")
    if not candidates:
        save_cooldown(cooldown)
        return

    # 개별 종목 OHLCV 실값 보완 (시가·고가·저가 volume-rank 미제공)
    log.info(f"개별 OHLCV 조회: {len(candidates)}종목")
    for code in candidates:
        mkt_div   = "J" if valid_codes_db.get(code) == "KOSPI" else "Q"
        price_dat = fetch_current_price(code, mkt_div)
        if price_dat:
            today_rows[code].update(price_dat)
        time.sleep(0.05)   # KIS 레이트 리밋 (20 TPS 한도)

    # Supabase 이력 로드 (오늘치는 아직 없으므로 어제까지 이력)
    conn = await asyncpg.connect(DSN, statement_cache_size=0)
    try:
        since      = TODAY_D - timedelta(days=HISTORY_DAYS + 10)
        hist_data  = await fetch_history(conn, candidates, since)
        kospi_hist = await fetch_kospi_index(conn)
        fin_data   = await fetch_financials(conn, candidates)
        log.info(f"이력: {len(hist_data)}종목, 재무: {len(fin_data)}종목")
    finally:
        await conn.close()

    # 피처 계산
    feats_list:  list[dict] = []
    valid_codes: list[str]  = []

    for code in candidates:
        today_r   = today_rows.get(code)
        if not today_r or today_r["close"] <= 0:
            continue
        is_kosdaq = 1.0 if today_r["market"] == "KOSDAQ" else 0.0
        feats = compute_features(
            today_r, hist_data.get(code, []),
            is_kosdaq, kospi_hist, feature_cols,
            fin=fin_data.get(code),
        )
        feats_list.append(feats)
        valid_codes.append(code)

    if not feats_list:
        log.info("유효 피처 없음")
        return

    feats_list   = add_rank_features(feats_list)
    probs, risks = ml_score(pd.DataFrame(feats_list), models, feature_cols)

    log.info(
        f"점수 분포 — prob: min={probs.min():.3f} mean={probs.mean():.3f} max={probs.max():.3f}"
        f" | risk: min={risks.min():.3f} max={risks.max():.3f}"
    )

    # 추천 필터링
    new_recs: list[dict] = []
    for i, code in enumerate(valid_codes):
        prob = float(probs[i])
        risk = float(risks[i])
        if prob >= SCORE_THRESHOLD and risk <= RISK_THRESHOLD:
            r = today_rows[code]
            new_recs.append({
                "code":            code,
                "name":            r.get("name", code),
                "success_prob":    round(prob, 4),
                "risk_score":      round(risk, 4),
                "expected_return": round((prob - 0.5) * 20.0, 2),
                "hold_days":       5,
                "close_price":     r["close"],
                "change_rate":     round(r["change_rate"], 2),
                "vol_ratio":       r["vol_ratio"],
            })
            cooldown[code] = NOW.isoformat()

    log.info(f"추천 종목: {len(new_recs)}개 / 후보 {len(valid_codes)}개")

    if new_recs:
        conn = await asyncpg.connect(DSN, statement_cache_size=0)
        try:
            n = await save_recommendations(conn, new_recs)
            log.info(f"저장 완료: {n}건")
        finally:
            await conn.close()

        lines = [f"<b>⚡ 장 중 매수 추천 {len(new_recs)}종목</b> ({NOW.strftime('%H:%M')} KST)\n"]
        for r in sorted(new_recs, key=lambda x: -x["success_prob"])[:10]:
            chg = r["change_rate"]
            chg_str = f"+{chg:.1f}%" if chg >= 0 else f"{chg:.1f}%"
            lines.append(
                f"• <b>{r.get('name', r['code'])}</b> ({r['code']})"
                f"  확률 {r['success_prob']:.0%}"
                f"  {chg_str}  거래량 {r['vol_ratio']:.1f}x  ₩{r['close_price']:,}"
            )
        await send_telegram("\n".join(lines))

    save_cooldown(cooldown)


if __name__ == "__main__":
    asyncio.run(main())

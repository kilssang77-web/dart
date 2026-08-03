"""
보유 종목 모니터링 — 손절/목표가 SELL 알림
크론: */30 0-7 * * 1-5  (UTC 00:00~07:30 = KST 09:00~16:30, 30분 간격)

동작:
  1. recommendations WHERE action='BUY' AND actual_return IS NULL 로드
  2. 최근 5 영업일 이내 추천만 모니터링
  3. KIS REST 현재가 조회 (FHKST01010100)
  4. 손절(-5% 이하) 또는 목표가(+10% 이상) 도달 시 Telegram SELL 알림 전송
  5. actual_return, is_success 업데이트 (DB 결산)

환경변수: POSTGRES_DSN, KIS_APP_KEY, KIS_APP_SECRET, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
          STOP_LOSS (기본 -5.0), TAKE_PROFIT (기본 10.0)
"""
import asyncio
import asyncpg
import json
import logging
import os
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/.env"))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("hold_monitor")

KST = timezone(timedelta(hours=9))

DSN        = os.environ["POSTGRES_DSN"]
APP_KEY    = os.environ["KIS_APP_KEY"]
APP_SECRET = os.environ["KIS_APP_SECRET"]
TG_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHAT    = os.environ.get("TELEGRAM_CHAT_ID", "")
KIS_BASE   = "https://openapi.koreainvestment.com:9443"

STOP_LOSS   = float(os.environ.get("STOP_LOSS",   "-5.0"))   # 손절 기준 (%)
TAKE_PROFIT = float(os.environ.get("TAKE_PROFIT", "10.0"))   # 목표가 기준 (%)
MAX_HOLD_DAYS = int(os.environ.get("MAX_HOLD_DAYS", "5"))     # 최대 보유 영업일

_TOKEN_CACHE: dict = {}


# ── 텔레그램 설정 (Redis telegram:config 연동) ─────────────────

def _load_tg_config() -> dict:
    """Redis에서 설정 UI 값을 조회. REDIS_URL 없거나 실패 시 env 기본값."""
    default = {
        "enabled":         os.environ.get("TELEGRAM_ENABLED", "1") == "1",
        "min_prob":        float(os.environ.get("REC_MIN_PROB",        "0.22")),
        "max_risk":        float(os.environ.get("REC_MAX_RISK",        "0.60")),
        "min_risk_reward": float(os.environ.get("REC_MIN_RISK_REWARD", "2.0")),
    }
    redis_url = os.environ.get("REDIS_URL", "")
    if not redis_url:
        return default
    try:
        import redis as _r
        rc = _r.from_url(redis_url, decode_responses=True, socket_timeout=3)
        raw = rc.get("telegram:config")
        rc.close()
        if raw:
            cfg = json.loads(raw)
            log.info(
                f"Redis 설정 로드: enabled={cfg.get('enabled')} "
                f"min_prob={cfg.get('min_prob'):.3f}"
            )
            return cfg
    except Exception as e:
        log.warning(f"Redis 설정 로드 실패, env 기본값 사용: {e}")
    return default


async def _log_telegram(
    conn: asyncpg.Connection,
    *,
    msg_type: str,
    code: str,
    name: str,
    title: str,
    message: str,
    success: bool,
) -> None:
    try:
        await conn.execute(
            """
            INSERT INTO telegram_logs (msg_type, code, name, title, message, success)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            msg_type, code or None, name or None, title, message, success,
        )
    except Exception as e:
        log.warning(f"telegram_logs 기록 실패: {e}")


# ── KIS REST ──────────────────────────────────────────────────

def _kis_token() -> str:
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


def _s(v) -> float:
    try:
        return float(str(v).replace(",", "").strip() or 0)
    except (ValueError, TypeError):
        return 0.0


def fetch_current_price(code: str, mkt_div: str = "J") -> float | None:
    """KIS 현재가 조회. 실패 시 None."""
    for div in ([mkt_div] if mkt_div != "J" else ["J"]) + (["Q"] if mkt_div == "J" else ["J"]):
        try:
            qs = f"FID_COND_MRKT_DIV_CODE={div}&FID_INPUT_ISCD={code}"
            req = urllib.request.Request(
                f"{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-price?{qs}",
                headers={
                    "authorization":  f"Bearer {_kis_token()}",
                    "appkey":         APP_KEY,
                    "appsecret":      APP_SECRET,
                    "tr_id":          "FHKST01010100",
                    "content-type":   "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                d = json.loads(r.read())
            if d.get("rt_cd") != "0":
                continue
            price = _s(d.get("output", {}).get("stck_prpr"))
            if price > 0:
                return price
        except Exception as e:
            log.debug(f"현재가 조회 실패({code}/{div}): {e}")
    return None


# ── Telegram ──────────────────────────────────────────────────

def send_telegram(text: str) -> bool:
    if not TG_TOKEN or not TG_CHAT:
        return False
    success = True
    for chat_id in TG_CHAT.split(","):
        chat_id = chat_id.strip()
        if not chat_id:
            continue
        try:
            payload = json.dumps({
                "chat_id":    chat_id,
                "text":       text,
                "parse_mode": "HTML",
            }).encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                pass
        except Exception as e:
            log.warning(f"Telegram 전송 실패({chat_id}): {e}")
            success = False
    return success


# ── DB ────────────────────────────────────────────────────────

async def load_open_positions(conn: asyncpg.Connection) -> list[dict]:
    """actual_return이 없고 MAX_HOLD_DAYS 이내인 BUY 추천 로드."""
    cutoff = datetime.now(KST) - timedelta(days=MAX_HOLD_DAYS * 2)  # 영업일 여유
    rows = await conn.fetch(
        """
        SELECT r.id, r.code, COALESCE(s.name, r.code) AS name,
               r.entry_price, r.created_at AT TIME ZONE 'Asia/Seoul' AS kst_time,
               COALESCE(s.market, 'KOSPI') AS market
        FROM recommendations r
        LEFT JOIN stocks s ON s.code = r.code
        WHERE r.action = 'BUY'
          AND r.actual_return IS NULL
          AND r.created_at >= $1
        ORDER BY r.created_at DESC
        """,
        cutoff,
    )
    return [dict(r) for r in rows]


async def close_position(
    conn: asyncpg.Connection,
    rec_id: int,
    entry_price: float,
    current_price: float,
    reason: str,
) -> float:
    """actual_return 업데이트 + is_success 기록."""
    ret = (current_price - entry_price) / entry_price * 100
    is_success = ret >= 0
    await conn.execute(
        """
        UPDATE recommendations
        SET actual_return = $1,
            is_success    = $2
        WHERE id = $3
        """,
        round(ret, 4), is_success, rec_id,
    )
    log.info(f"포지션 결산(id={rec_id}): {ret:+.2f}% ({reason})")
    return ret


# ── 메인 ──────────────────────────────────────────────────────

async def main() -> None:
    now_kst = datetime.now(KST)
    kst_min = now_kst.hour * 60 + now_kst.minute
    # 장 시간 외에는 실행하지 않음 (KST 09:00~15:30)
    if not (540 <= kst_min <= 930):
        log.info(f"장 외 시간 ({now_kst.strftime('%H:%M KST')}) — 스킵")
        return

    cfg = _load_tg_config()
    log.info(f"보유 모니터링 시작 {now_kst.strftime('%Y-%m-%d %H:%M KST')}")

    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=3, statement_cache_size=0)
    try:
        async with pool.acquire() as conn:
            positions = await load_open_positions(conn)

        if not positions:
            log.info("모니터링 대상 포지션 없음")
            return

        log.info(f"모니터링 대상: {len(positions)}건")

        sell_msgs: list[str] = []
        sell_meta: list[dict] = []

        for pos in positions:
            rec_id      = pos["id"]
            code        = pos["code"]
            name        = pos["name"]
            entry_price = float(pos["entry_price"])
            market      = pos["market"]
            mkt_div     = "J" if market == "KOSPI" else "Q"

            if entry_price <= 0:
                continue

            current = fetch_current_price(code, mkt_div)
            if current is None:
                log.debug(f"현재가 조회 실패 — 스킵: {code}")
                continue

            chg_pct = (current - entry_price) / entry_price * 100
            time.sleep(0.05)  # KIS 20 TPS 한도

            reason = None
            if chg_pct <= STOP_LOSS:
                reason = f"손절 {chg_pct:.1f}%"
            elif chg_pct >= TAKE_PROFIT:
                reason = f"목표가 달성 +{chg_pct:.1f}%"

            if reason:
                async with pool.acquire() as conn:
                    ret = await close_position(conn, rec_id, entry_price, current, reason)
                icon = "🛑" if chg_pct <= STOP_LOSS else "🎯"
                body = (
                    f"{icon} <b>{name}</b> ({code}) — <b>SELL</b>\n"
                    f"   사유: {reason}\n"
                    f"   매수가 ₩{int(entry_price):,} → 현재 ₩{int(current):,}\n"
                    f"   수익률: {ret:+.2f}%\n"
                    f"   🕐 탐지 일시: {now_kst.strftime('%Y-%m-%d %H:%M')} KST"
                )
                sell_msgs.append(body)
                sell_meta.append({"code": code, "name": name, "reason": reason, "body": body})

        if sell_msgs:
            header   = f"<b>📢 SELL 알림 {len(sell_msgs)}건</b> ({now_kst.strftime('%H:%M')} KST)\n"
            full_msg = header + "\n\n".join(sell_msgs)

            if cfg.get("enabled", True):
                ok = send_telegram(full_msg)
                log.info(f"SELL 알림 {'전송 완료' if ok else '전송 실패'}: {len(sell_msgs)}건")
            else:
                ok = False
                log.info(f"텔레그램 알림 비활성화 — SELL 발송 스킵 ({len(sell_msgs)}건)")

            # 알림이력 기록 (발송 시도분만)
            if cfg.get("enabled", True):
                async with pool.acquire() as conn:
                    for m in sell_meta:
                        await _log_telegram(
                            conn,
                            msg_type="sell_alert",
                            code=m["code"],
                            name=m["name"],
                            title=f"{m['name']} SELL ({m['reason']})",
                            message=m["body"],
                            success=ok,
                        )
        else:
            log.info(f"손절/목표가 도달 없음 (모니터링 {len(positions)}건)")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())

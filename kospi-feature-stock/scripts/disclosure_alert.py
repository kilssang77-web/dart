"""
공시 키워드 Telegram 알림 — is_flagged=TRUE 공시 감지 후 즉시 발송
크론: */30 0-7 * * 1-5  (UTC 00:00~07:30 = KST 09:00~16:30, 장 중 30분 간격)

동작:
  1. disclosures WHERE is_flagged=TRUE AND disclosed_at > 마지막처리시각 조회
  2. 신규 항목만 Telegram 전송
  3. telegram_logs에 발송 이력 기록
  4. 오프셋(~/quant/disclosure_offset.json)으로 중복 발송 방지

환경변수: POSTGRES_DSN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
"""
import asyncio
import asyncpg
import json
import logging
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/.env"))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("disclosure_alert")

KST          = timezone(timedelta(hours=9))
DSN          = os.environ["POSTGRES_DSN"]
TG_TOKEN     = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHAT      = os.environ.get("TELEGRAM_CHAT_ID", "")
OFFSET_FILE  = Path(os.path.expanduser("~/quant/disclosure_offset.json"))
LOOKBACK_HRS = int(os.environ.get("DISCLOSURE_LOOKBACK_HRS", "24"))  # 첫 실행 시 소급 시간


# ── 오프셋 관리 ───────────────────────────────────────────────

def load_offset() -> datetime:
    if OFFSET_FILE.exists():
        try:
            d = json.loads(OFFSET_FILE.read_text())
            return datetime.fromisoformat(d["last_at"]).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HRS)


def save_offset(last_at: datetime) -> None:
    OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
    OFFSET_FILE.write_text(json.dumps({"last_at": last_at.isoformat()}))


# ── Telegram ─────────────────────────────────────────────────

def send_telegram(text: str) -> bool:
    if not TG_TOKEN or not TG_CHAT:
        log.warning("TELEGRAM_TOKEN 또는 TELEGRAM_CHAT_ID 미설정")
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


# ── 포맷 ─────────────────────────────────────────────────────

def _category_icon(category: str | None) -> str:
    return {"favorable": "📈", "unfavorable": "📉", "neutral": "📋"}.get(category or "", "📋")


def format_disclosure(row: dict) -> str:
    icon     = _category_icon(row.get("category"))
    corp     = row.get("corp_name") or row.get("code") or "—"
    code     = row.get("code") or ""
    title    = row.get("title") or ""
    score    = row.get("sentiment_score")
    kws      = row.get("keywords") or []
    dt       = row.get("disclosed_at")
    dt_str   = dt.astimezone(KST).strftime("%m/%d %H:%M") if dt else "—"
    score_str = f"  감성점수: {float(score):+.2f}" if score is not None else ""
    kw_str   = "  키워드: " + ", ".join(kws[:5]) if kws else ""
    code_str  = f" ({code})" if code else ""
    return (
        f"{icon} <b>공시 알림</b> [{dt_str}]\n"
        f"<b>{corp}</b>{code_str}\n"
        f"📄 {title}"
        f"{score_str}"
        f"{kw_str}"
    )


# ── 메인 ─────────────────────────────────────────────────────

async def main() -> None:
    last_at = load_offset()
    log.info(f"공시 알림 시작 — 마지막 처리: {last_at.astimezone(KST).strftime('%Y-%m-%d %H:%M KST')}")

    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=2, statement_cache_size=0)
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT rcept_no, code, corp_name, title,
                       category, sentiment_score, keywords, disclosed_at
                FROM disclosures
                WHERE is_flagged = TRUE
                  AND disclosed_at > $1
                ORDER BY disclosed_at ASC
                LIMIT 20
                """,
                last_at,
            )

        if not rows:
            log.info("신규 플래그 공시 없음")
            return

        log.info(f"신규 플래그 공시: {len(rows)}건")
        max_at = last_at
        sent   = 0

        for row in rows:
            row = dict(row)
            # keywords JSONB → Python list
            kws = row.get("keywords")
            if isinstance(kws, str):
                try:
                    row["keywords"] = json.loads(kws)
                except Exception:
                    row["keywords"] = []

            msg  = format_disclosure(row)
            ok   = send_telegram(msg)
            err  = None if ok else "Telegram 전송 실패"

            # telegram_logs 기록
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO telegram_logs
                        (msg_type, code, name, title, message, success, error_msg)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    "disclosure",
                    row.get("code"),
                    row.get("corp_name"),
                    row.get("rcept_no", ""),
                    msg,
                    ok,
                    err,
                )

            dt = row.get("disclosed_at")
            if dt and dt > max_at:
                max_at = dt
            if ok:
                sent += 1

        # 오프셋 업데이트 (마지막 처리된 공시 시각 + 1초)
        save_offset(max_at + timedelta(seconds=1))
        log.info(f"발송 완료: {sent}/{len(rows)}건")

    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())

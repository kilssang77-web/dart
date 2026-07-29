"""
Telegram 봇 명령어 인터페이스 — polling 방식
크론: */5 * * * *  (5분 간격 polling, 항상 실행)

지원 명령어:
  /recs   — 최근 24시간 BUY 추천 목록
  /top    — 성공 확률 상위 5종목 (오늘)
  /result — 최근 30일 성과 요약
  /status — 시스템 상태 (DB 연결, 최근 스캔 시각)
  /help   — 명령어 안내

동작 방식:
  - getUpdates long-poll (timeout=10s)로 새 메시지 수신
  - offset 파일(~/quant/tg_offset.json)로 중복 처리 방지
  - asyncpg로 Supabase 조회 → 결과 sendMessage
"""
import asyncio
import asyncpg
import json
import logging
import os
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/.env"))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("tg_bot")

KST     = timezone(timedelta(hours=9))
NOW     = datetime.now(KST)

DSN      = os.environ["POSTGRES_DSN"]
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TG_BASE  = f"https://api.telegram.org/bot{TG_TOKEN}"
OFFSET_FILE = Path(os.path.expanduser("~/quant/tg_offset.json"))

ALLOWED_CHATS: set[int] = set()
_allow_env = os.environ.get("TELEGRAM_CHAT_ID", "")
if _allow_env:
    for _c in _allow_env.split(","):
        try:
            ALLOWED_CHATS.add(int(_c.strip()))
        except ValueError:
            pass


# ── Telegram API ──────────────────────────────────────────────

def _tg_request(method: str, params: dict) -> dict:
    url     = f"{TG_BASE}/{method}"
    payload = json.dumps(params).encode()
    req     = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def get_updates(offset: int) -> list[dict]:
    try:
        d = _tg_request("getUpdates", {"offset": offset, "timeout": 10, "limit": 20})
        return d.get("result", []) if d.get("ok") else []
    except Exception as e:
        log.warning(f"getUpdates 실패: {e}")
        return []


def send_message(chat_id: int, text: str) -> None:
    try:
        _tg_request("sendMessage", {
            "chat_id":    chat_id,
            "text":       text,
            "parse_mode": "HTML",
        })
    except Exception as e:
        log.warning(f"sendMessage 실패({chat_id}): {e}")


# ── offset 관리 ────────────────────────────────────────────────

def load_offset() -> int:
    if OFFSET_FILE.exists():
        try:
            return int(json.loads(OFFSET_FILE.read_text()).get("offset", 0))
        except Exception:
            pass
    return 0


def save_offset(offset: int) -> None:
    OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
    OFFSET_FILE.write_text(json.dumps({"offset": offset}))


# ── DB 조회 ────────────────────────────────────────────────────

async def query_recent_recs(conn) -> str:
    """최근 24시간 BUY 추천"""
    rows = await conn.fetch("""
        SELECT r.code, COALESCE(s.name, r.code) AS name,
               r.success_prob, r.risk_score, r.entry_price,
               r.created_at AT TIME ZONE 'Asia/Seoul' AS kst_time
        FROM recommendations r
        LEFT JOIN stocks s ON s.code = r.code
        WHERE r.action = 'BUY'
          AND r.created_at >= NOW() - INTERVAL '24 hours'
        ORDER BY r.success_prob DESC
        LIMIT 15
    """)
    if not rows:
        return "최근 24시간 BUY 추천이 없습니다."
    lines = [f"<b>📋 최근 24h BUY 추천 ({len(rows)}건)</b>\n"]
    for r in rows:
        t = r["kst_time"].strftime("%H:%M")
        lines.append(
            f"• <b>{r['name']}</b> ({r['code']})"
            f"  확률 {r['success_prob']:.0%}"
            f"  위험 {r['risk_score']:.0%}"
            f"  ₩{r['entry_price']:,}  [{t}]"
        )
    return "\n".join(lines)


async def query_top_today(conn) -> str:
    """오늘 상위 5종목"""
    rows = await conn.fetch("""
        SELECT r.code, COALESCE(s.name, r.code) AS name,
               r.success_prob, r.risk_score, r.entry_price
        FROM recommendations r
        LEFT JOIN stocks s ON s.code = r.code
        WHERE r.action = 'BUY'
          AND r.created_at::date = CURRENT_DATE
        ORDER BY r.success_prob DESC
        LIMIT 5
    """)
    if not rows:
        return f"오늘({NOW.strftime('%m/%d')}) 추천 종목이 없습니다."
    lines = [f"<b>🏆 오늘의 TOP 5</b>\n"]
    for i, r in enumerate(rows, 1):
        lines.append(
            f"{i}. <b>{r['name']}</b> ({r['code']})"
            f"  {r['success_prob']:.0%}  ₩{r['entry_price']:,}"
        )
    return "\n".join(lines)


async def query_result(conn) -> str:
    """최근 30일 성과 요약"""
    stats = await conn.fetchrow("""
        SELECT
            COUNT(*)                                              AS total,
            SUM(CASE WHEN is_success THEN 1 ELSE 0 END)         AS success_cnt,
            SUM(CASE WHEN NOT is_success THEN 1 ELSE 0 END)     AS fail_cnt,
            AVG(actual_return)                                    AS avg_ret,
            MAX(actual_return)                                    AS max_ret,
            MIN(actual_return)                                    AS min_ret
        FROM recommendations
        WHERE action = 'BUY'
          AND actual_return IS NOT NULL
          AND created_at >= NOW() - INTERVAL '30 days'
    """)
    total = int(stats["total"] or 0)
    if total == 0:
        return "최근 30일 성과 데이터가 없습니다.\n(추천 후 5 영업일이 지나야 집계됩니다)"
    success = int(stats["success_cnt"] or 0)
    fail    = int(stats["fail_cnt"]    or 0)
    avg_r   = float(stats["avg_ret"]   or 0)
    max_r   = float(stats["max_ret"]   or 0)
    min_r   = float(stats["min_ret"]   or 0)
    rate    = success / total
    return (
        f"<b>📊 최근 30일 성과</b>\n\n"
        f"총 추천: {total}건\n"
        f"✅ 성공: {success}건 ({rate:.0%})\n"
        f"❌ 실패: {fail}건\n"
        f"평균 수익: {avg_r:+.2f}%\n"
        f"최대: {max_r:+.2f}%  최소: {min_r:+.2f}%"
    )


async def query_status(conn) -> str:
    """시스템 상태"""
    last_rec = await conn.fetchval(
        "SELECT MAX(created_at) AT TIME ZONE 'Asia/Seoul' FROM recommendations WHERE action='BUY'"
    )
    bar_cnt = await conn.fetchval("SELECT COUNT(*) FROM daily_bars")
    rec_cnt = await conn.fetchval("SELECT COUNT(*) FROM recommendations WHERE action='BUY'")
    pending = await conn.fetchval(
        "SELECT COUNT(*) FROM recommendations WHERE action='BUY' AND actual_return IS NULL AND created_at < NOW() - INTERVAL '5 days'"
    )
    dyn_cfg = Path(os.path.expanduser("~/quant/dynamic_config.json"))
    thr_info = ""
    if dyn_cfg.exists():
        try:
            d = json.loads(dyn_cfg.read_text())
            thr_info = f"\nML 임계값: {d.get('score_threshold', '?')} (성공률 {d.get('recent_rate', 0):.0%})"
        except Exception:
            pass
    last_str = last_rec.strftime("%Y-%m-%d %H:%M") if last_rec else "없음"
    return (
        f"<b>🖥 시스템 상태</b>\n\n"
        f"DB 연결: ✅ 정상\n"
        f"일봉 데이터: {bar_cnt:,}행\n"
        f"총 추천: {rec_cnt:,}건\n"
        f"마지막 추천: {last_str} KST\n"
        f"성과 평가 대기: {pending}건"
        f"{thr_info}"
    )


HELP_TEXT = (
    "<b>📈 KOSPI Quant Scanner 봇 도움말</b>\n\n"
    "/recs    — 최근 24h BUY 추천 목록\n"
    "/top     — 오늘 확률 상위 5종목\n"
    "/result  — 최근 30일 성과 요약\n"
    "/status  — 시스템 상태\n"
    "/help    — 이 도움말\n\n"
    "크론 스캔: 장 마감 후 KST 16:30, 장 중 10분 간격"
)


# ── 명령어 처리 ────────────────────────────────────────────────

async def handle_command(cmd: str, chat_id: int) -> None:
    try:
        conn = await asyncpg.connect(DSN, statement_cache_size=0)
        try:
            cmd = cmd.split("@")[0].lower().strip()   # /cmd@botname → /cmd
            if cmd == "/recs":
                text = await query_recent_recs(conn)
            elif cmd == "/top":
                text = await query_top_today(conn)
            elif cmd == "/result":
                text = await query_result(conn)
            elif cmd == "/status":
                text = await query_status(conn)
            elif cmd == "/help" or cmd == "/start":
                text = HELP_TEXT
            else:
                text = f"알 수 없는 명령어: {cmd}\n/help 로 명령어 목록을 확인하세요."
        finally:
            await conn.close()
    except Exception as e:
        log.error(f"명령어 처리 오류({cmd}): {e}")
        text = f"오류가 발생했습니다: {e}"
    send_message(chat_id, text)


async def main():
    if not TG_TOKEN:
        log.error("TELEGRAM_TOKEN 미설정")
        return

    offset = load_offset()
    log.info(f"Telegram 봇 시작 — offset={offset}")

    updates = get_updates(offset)
    if not updates:
        log.info("새 메시지 없음")
        return

    tasks = []
    for update in updates:
        offset = max(offset, update["update_id"] + 1)
        msg = update.get("message") or update.get("edited_message")
        if not msg:
            continue
        chat_id = msg.get("chat", {}).get("id")
        text    = msg.get("text", "")
        if not chat_id or not text.startswith("/"):
            continue
        if ALLOWED_CHATS and chat_id not in ALLOWED_CHATS:
            log.warning(f"허용되지 않은 채팅: {chat_id}")
            continue
        log.info(f"명령어 수신: {text!r} from {chat_id}")
        tasks.append(handle_command(text.strip(), chat_id))

    if tasks:
        await asyncio.gather(*tasks)

    save_offset(offset)
    log.info(f"처리 완료 — offset={offset}")


if __name__ == "__main__":
    asyncio.run(main())

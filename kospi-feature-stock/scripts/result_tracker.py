"""
5일 성과 피드백 루프 — 추천 결과 자동 평가 + 동적 임계값 조정
크론: 0 9 * * 1-5  (UTC 09:00 = KST 18:00, 장 마감 후)

동작:
  - 5 영업일 이상 경과된 BUY 추천 중 actual_return IS NULL인 항목 평가
  - Supabase daily_bars에서 평가일 종가 조회 → actual_return / is_success 업데이트
  - 최근 30일 성공률로 ~/quant/dynamic_config.json 임계값 자동 조정
  - Telegram으로 성과 요약 전송
"""
import asyncio
import asyncpg
import json
import logging
import os
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/.env"))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("result_tracker")

KST     = timezone(timedelta(hours=9))
NOW     = datetime.now(KST)
TODAY_D = NOW.date()

DSN      = os.environ["POSTGRES_DSN"]
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHAT  = os.environ.get("TELEGRAM_CHAT_ID", "")

SUCCESS_THRESHOLD = float(os.environ.get("SUCCESS_THRESHOLD", "3.0"))   # 3% 이상 = 성공
BASE_SCORE_THR    = float(os.environ.get("SCORE_THRESHOLD",   "0.27"))  # 기본 ML 임계값
DYNAMIC_CONFIG    = Path(os.path.expanduser("~/quant/dynamic_config.json"))

EVAL_HOLD_DAYS = 5   # 매수 후 평가 기준 영업일


# ── 날짜 유틸 ─────────────────────────────────────────────────

def _biz_days_ago(n: int, ref: date | None = None) -> date:
    """n 영업일 이전 날짜"""
    d = ref or TODAY_D
    count = 0
    while count < n:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            count += 1
    return d


def _biz_days_after(ref: date, n: int) -> date:
    """ref 기준 n 영업일 이후 날짜"""
    d = ref
    count = 0
    while count < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            count += 1
    return d


# ── Telegram ──────────────────────────────────────────────────

async def send_telegram(text: str) -> None:
    if not TG_TOKEN or not TG_CHAT:
        return
    url     = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = json.dumps({"chat_id": TG_CHAT, "text": text, "parse_mode": "HTML"}).encode()
    try:
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
        log.info("Telegram 전송 완료")
    except Exception as e:
        log.warning(f"Telegram 전송 실패: {e}")


# ── 동적 설정 ─────────────────────────────────────────────────

def load_dynamic_config() -> dict:
    if DYNAMIC_CONFIG.exists():
        try:
            return json.loads(DYNAMIC_CONFIG.read_text())
        except Exception:
            pass
    return {}


def save_dynamic_config(cfg: dict) -> None:
    DYNAMIC_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    DYNAMIC_CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))
    log.info(f"동적 설정 저장: {cfg}")


# ── 메인 ──────────────────────────────────────────────────────

async def main():
    eval_cutoff = _biz_days_ago(EVAL_HOLD_DAYS)
    log.info(f"성과 평가 기준일: {eval_cutoff} 이전 추천")

    conn = await asyncpg.connect(DSN, statement_cache_size=0)
    try:
        # ① 미평가 추천 조회
        recs = await conn.fetch("""
            SELECT id, code, entry_price, created_at::date AS entry_date
            FROM recommendations
            WHERE action = 'BUY'
              AND actual_return IS NULL
              AND created_at::date <= $1
        """, eval_cutoff)
        log.info(f"미평가 추천: {len(recs)}건")

        updated = 0
        results: list[dict] = []

        for r in recs:
            code        = r["code"]
            entry_price = r["entry_price"] or 0
            entry_date  = r["entry_date"]
            eval_date   = _biz_days_after(entry_date, EVAL_HOLD_DAYS)

            if entry_price <= 0:
                log.debug(f"{code}: entry_price 없음 — 스킵")
                continue

            # ② 평가일 종가 (없으면 eval_date 이전 가장 최근 종가)
            close_price = await conn.fetchval("""
                SELECT close FROM daily_bars
                WHERE code = $1
                  AND date <= $2
                  AND date > $3
                ORDER BY date DESC
                LIMIT 1
            """, code, eval_date, entry_date)

            if not close_price or close_price <= 0:
                log.debug(f"{code} ({entry_date}): 평가일 종가 없음")
                continue

            actual_return = (close_price - entry_price) / entry_price * 100.0
            is_success    = actual_return >= SUCCESS_THRESHOLD

            await conn.execute("""
                UPDATE recommendations
                SET actual_return = $1, is_success = $2
                WHERE id = $3
            """, round(actual_return, 2), is_success, r["id"])
            updated += 1
            results.append({
                "code":          code,
                "entry_date":    str(entry_date),
                "close_price":   close_price,
                "actual_return": round(actual_return, 2),
                "is_success":    is_success,
            })
            log.info(f"{code} ({entry_date}): {actual_return:+.2f}% {'✅' if is_success else '❌'}")

        log.info(f"업데이트 완료: {updated}건")

        # ③ 최근 30일 성공률
        stats = await conn.fetchrow("""
            SELECT
                COUNT(*)                                              AS total,
                SUM(CASE WHEN is_success THEN 1 ELSE 0 END)         AS success_cnt,
                AVG(actual_return)                                    AS avg_return
            FROM recommendations
            WHERE action = 'BUY'
              AND actual_return IS NOT NULL
              AND created_at >= NOW() - INTERVAL '30 days'
        """)
    finally:
        await conn.close()

    total   = int(stats["total"]       or 0)
    success = int(stats["success_cnt"] or 0)
    avg_ret = float(stats["avg_return"] or 0.0)
    rate    = success / total if total > 0 else 0.0
    log.info(f"최근 30일: 총{total}건  성공{success}건  성공률{rate:.1%}  평균수익{avg_ret:+.2f}%")

    # ④ 동적 임계값 조정
    cfg = load_dynamic_config()
    if total >= 10:
        cur_thr = float(cfg.get("score_threshold", BASE_SCORE_THR))
        if rate >= 0.55:
            new_thr = max(cur_thr - 0.02, 0.20)   # 성공률 ↑ → 기준 완화
        elif rate <= 0.30:
            new_thr = min(cur_thr + 0.03, 0.45)   # 성공률 ↓ → 기준 강화
        else:
            new_thr = cur_thr
        cfg.update({
            "score_threshold": round(new_thr, 3),
            "recent_rate":     round(rate, 3),
            "total_recs":      total,
            "avg_return":      round(avg_ret, 2),
            "updated_at":      NOW.isoformat(),
        })
        save_dynamic_config(cfg)
        log.info(f"ML 임계값: {cur_thr:.3f} → {new_thr:.3f}")
    else:
        log.info(f"샘플 부족({total}건 < 10) — 임계값 조정 스킵")

    # ⑤ Telegram 리포트
    if updated == 0 and total == 0:
        log.info("리포트 없음")
        return

    lines = [f"<b>📊 5일 성과 평가 ({TODAY_D})</b>\n"]
    if updated > 0:
        wins  = [r for r in results if r["is_success"]]
        loses = [r for r in results if not r["is_success"]]
        lines.append(f"금일 평가 {updated}건  ✅성공 {len(wins)}  ❌실패 {len(loses)}")
        for r in sorted(results, key=lambda x: -x["actual_return"])[:8]:
            mark = "✅" if r["is_success"] else "❌"
            lines.append(
                f"{mark} {r['code']} {r['actual_return']:+.1f}%"
                f"  ₩{r['close_price']:,}  ({r['entry_date']} 매수)"
            )

    if total >= 5:
        lines.append(f"\n최근 30일: 성공률 {rate:.0%}  평균수익 {avg_ret:+.2f}%")
    if "score_threshold" in cfg and total >= 10:
        lines.append(f"ML 임계값 자동조정 → {cfg['score_threshold']:.3f}")

    await send_telegram("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())

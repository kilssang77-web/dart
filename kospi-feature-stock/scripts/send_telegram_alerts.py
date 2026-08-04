"""
Supabase 폴링 → Telegram 알림 (GitHub Actions 30분 간격 실행).

- 최근 35분 이내 신규 BUY 추천을 Supabase에서 조회
- TELEGRAM_SENT_IDS 환경변수(Actions cache)로 중복 방지
- 종목명·진입가·목표가·손절가·탐지근거·신뢰도 포함한 포맷으로 전송
"""
import asyncio
import json
import logging
import os
import urllib.request
from datetime import datetime, timedelta, timezone

import asyncpg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("telegram_alert")

_KST = timezone(timedelta(hours=9))
_WINDOW_MIN = 35   # 35분 이내 신규 추천 조회 (30분 간격 + 여유 5분)


def _publish_signal(code: str, name: str, prob: float, risk: float, rr: float,
                     entry: float, target: float, stop: float, rationale: dict) -> bool:
    """ch:signal-generated 발행 → notifier가 필터링 후 Telegram 발송."""
    redis_url = os.environ.get("REDIS_URL", "")
    if not redis_url:
        log.warning("REDIS_URL 미설정 — Telegram 발행 스킵")
        return False
    try:
        import redis as _r
        rc = _r.from_url(redis_url, decode_responses=True, socket_timeout=5)
        rc.publish("ch:signal-generated", json.dumps({
            "code":              code,
            "name":              name,
            "success_prob":      prob,
            "risk_score":        risk,
            "risk_reward_ratio": rr,
            "entry_price":       entry,
            "target_price":      target,
            "stop_loss_price":   stop,
            "rationale":         rationale,
        }, ensure_ascii=False))
        rc.close()
        return True
    except Exception as e:
        log.warning(f"Redis publish 실패: {e}")
        return False


def _format_message(r: dict) -> str:
    action_emoji = "🚨" if r["action"] == "BUY" else "📉"
    grade = r.get("confidence_grade") or "—"
    prob = r.get("success_prob", 0) * 100
    entry = r.get("entry_price", 0)
    target = r.get("target_price", 0)
    stop = r.get("stop_loss_price", 0)
    rr = r.get("risk_reward_ratio", 0)
    target_pct = ((target / entry) - 1) * 100 if entry > 0 else 0
    stop_pct = ((stop / entry) - 1) * 100 if entry > 0 else 0

    rationale = r.get("rationale") or {}
    if isinstance(rationale, str):
        try:
            rationale = json.loads(rationale)
        except Exception:
            rationale = {}

    event_type = rationale.get("event_type", "신호감지")
    vol_ratio = rationale.get("vol_ratio", 0)

    reasons = []
    if vol_ratio and vol_ratio > 2:
        reasons.append(f"거래량 {vol_ratio:.1f}배 급증")
    if rationale.get("has_favorable_disclosure"):
        reasons.append("호재 공시")
    if rationale.get("foreign_cumnet_streak", 0) >= 3:
        reasons.append(f"외국인 {rationale['foreign_cumnet_streak']}일 연속 순매수")
    reason_str = "\n".join(f"• {r}" for r in reasons) if reasons else f"• {event_type}"

    created_kst = r.get("created_at")
    time_str = ""
    if created_kst:
        if hasattr(created_kst, "astimezone"):
            time_str = created_kst.astimezone(_KST).strftime("%H:%M")
        else:
            time_str = str(created_kst)[:16]

    stock = f"{r['name']}({r['code']})" if r.get("name") and r["name"] != r["code"] else r["code"]
    return (
        f"{action_emoji} <b>[매수신호] {stock}</b>  {time_str}\n"
        f"진입가:  <b>{entry:,.0f}원</b>\n"
        f"목표가:  {target:,.0f}원  (<b>+{target_pct:.1f}%</b>)\n"
        f"손절가:  {stop:,.0f}원  ({stop_pct:.1f}%)\n"
        f"R:R  {rr:.2f}  |  신뢰도: <b>{grade}</b>  |  확률: {prob:.1f}%\n"
        f"\n[탐지 근거]\n{reason_str}"
    )


async def main():
    dsn = os.environ.get("POSTGRES_DSN", "").replace("+asyncpg", "")
    if not dsn:
        log.error("POSTGRES_DSN 환경변수 누락")
        return

    ssl = "require" if "supabase" in dsn else False
    since = datetime.now(timezone.utc) - timedelta(minutes=_WINDOW_MIN)
    conn = await asyncpg.connect(dsn, statement_cache_size=0, ssl=ssl)
    try:
        rows = await conn.fetch(
            """
            SELECT r.id, r.code, COALESCE(s.name, r.code) AS name,
                   r.action, r.created_at,
                   r.entry_price, r.target_price, r.stop_loss_price,
                   r.success_prob, r.risk_score, r.risk_reward_ratio,
                   r.confidence_grade, r.rationale
            FROM recommendations r
            LEFT JOIN stocks s ON s.code = r.code
            WHERE r.action = 'BUY'
              AND r.created_at >= $1
            ORDER BY r.created_at DESC
            LIMIT 20
            """,
            since,
        )

        if not rows:
            log.info(f"최근 {_WINDOW_MIN}분 내 신규 추천 없음")
            return

        log.info(f"신규 추천 {len(rows)}건 → ch:signal-generated 발행")
        for row in rows:
            r = dict(row)
            rationale = r.get("rationale") or {}
            if isinstance(rationale, str):
                try:
                    rationale = json.loads(rationale)
                except Exception:
                    rationale = {}
            ok = _publish_signal(
                code     = r["code"],
                name     = r.get("name", r["code"]),
                prob     = float(r.get("success_prob") or 0),
                risk     = float(r.get("risk_score") or 0),
                rr       = float(r.get("risk_reward_ratio") or 0),
                entry    = float(r.get("entry_price") or 0),
                target   = float(r.get("target_price") or 0),
                stop     = float(r.get("stop_loss_price") or 0),
                rationale = rationale,
            )
            log.info(f"{'✅' if ok else '❌'} {r['code']} 발행")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

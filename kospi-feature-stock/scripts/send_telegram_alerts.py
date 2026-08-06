"""
Supabase 폴링 → Telegram 직접 발송 (GitHub Actions 실행).

- 최근 35분 이내 신규 BUY 추천을 Supabase에서 조회
- Redis telegram:config 로 enabled/min_prob/max_risk/min_rr 필터 적용
- Redis tg:sent:rec:{id} 로 중복 발송 방지 (24h TTL)
- urllib.request 직접 발송 — notifier 서비스 의존 없음
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

_KST       = timezone(timedelta(hours=9))
_WINDOW_MIN = 35
TG_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHAT    = os.environ.get("TELEGRAM_CHAT_ID", "")
REDIS_URL  = os.environ.get("REDIS_URL", "")

_DEFAULT_CFG = {
    "enabled":         True,
    "min_prob":        0.22,
    "max_risk":        0.60,
    "min_risk_reward": 2.0,
}


def _load_tg_config() -> dict:
    if not REDIS_URL:
        return _DEFAULT_CFG
    try:
        import redis as _r
        rc = _r.from_url(REDIS_URL, decode_responses=True, socket_timeout=3)
        raw = rc.get("telegram:config")
        rc.close()
        if raw:
            return json.loads(raw)
    except Exception as e:
        log.warning(f"Redis 설정 로드 실패, 기본값 사용: {e}")
    return _DEFAULT_CFG


def _is_sent(rec_id: int) -> bool:
    """Redis에서 이미 발송된 추천인지 확인."""
    if not REDIS_URL:
        return False
    try:
        import redis as _r
        rc = _r.from_url(REDIS_URL, decode_responses=True, socket_timeout=3)
        result = rc.exists(f"tg:sent:rec:{rec_id}")
        rc.close()
        return bool(result)
    except Exception:
        return False


def _mark_sent(rec_id: int) -> None:
    """발송 완료 표시 (24h TTL)."""
    if not REDIS_URL:
        return
    try:
        import redis as _r
        rc = _r.from_url(REDIS_URL, decode_responses=True, socket_timeout=3)
        rc.set(f"tg:sent:rec:{rec_id}", "1", ex=86400)
        rc.close()
    except Exception:
        pass


def _send_telegram(text: str) -> bool:
    if not TG_TOKEN or not TG_CHAT:
        log.warning("TELEGRAM_TOKEN / TELEGRAM_CHAT_ID 미설정")
        return False
    url  = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    body = json.dumps({
        "chat_id": TG_CHAT, "text": text, "parse_mode": "HTML",
    }).encode()
    try:
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        log.warning(f"Telegram 전송 실패: {e}")
        return False


def _format_message(r: dict) -> str:
    prob  = float(r.get("success_prob") or 0)
    entry = float(r.get("entry_price") or 0)
    target = float(r.get("target_price") or 0)
    stop   = float(r.get("stop_loss_price") or 0)
    rr     = float(r.get("risk_reward_ratio") or 0)
    grade  = r.get("confidence_grade") or "—"

    target_pct = ((target / entry) - 1) * 100 if entry > 0 else 0
    stop_pct   = ((stop   / entry) - 1) * 100 if entry > 0 else 0

    rationale = r.get("rationale") or {}
    if isinstance(rationale, str):
        try:
            rationale = json.loads(rationale)
        except Exception:
            rationale = {}

    event_type = rationale.get("event_type", "신호감지")
    vol_ratio  = rationale.get("vol_ratio", 0)

    reasons = []
    if vol_ratio and vol_ratio > 2:
        reasons.append(f"거래량 {vol_ratio:.1f}배 급증")
    if rationale.get("has_favorable_disclosure"):
        reasons.append("호재 공시")
    if rationale.get("foreign_cumnet_streak", 0) >= 3:
        reasons.append(f"외국인 {rationale['foreign_cumnet_streak']}일 연속 순매수")
    reason_str = "\n".join(f"• {x}" for x in reasons) if reasons else f"• {event_type}"

    created_kst = r.get("created_at")
    time_str = ""
    if created_kst:
        if hasattr(created_kst, "astimezone"):
            time_str = created_kst.astimezone(_KST).strftime("%H:%M")
        else:
            time_str = str(created_kst)[:16]

    name  = r.get("name", r["code"])
    stock = f"{name}({r['code']})" if name != r["code"] else r["code"]

    return (
        f"🚨 <b>[매수신호] {stock}</b>  {time_str}\n"
        f"진입가:  <b>{entry:,.0f}원</b>\n"
        f"목표가:  {target:,.0f}원  (<b>+{target_pct:.1f}%</b>)\n"
        f"손절가:  {stop:,.0f}원  ({stop_pct:.1f}%)\n"
        f"R:R  {rr:.2f}  |  신뢰도: <b>{grade}</b>  |  확률: {prob*100:.1f}%\n"
        f"\n[탐지 근거]\n{reason_str}"
    )


async def main():
    dsn = os.environ.get("POSTGRES_DSN", "").replace("+asyncpg", "")
    if not dsn:
        log.error("POSTGRES_DSN 환경변수 누락")
        return
    if not TG_TOKEN or not TG_CHAT:
        log.error("TELEGRAM_TOKEN / TELEGRAM_CHAT_ID 환경변수 누락")
        return

    cfg = _load_tg_config()
    if not cfg.get("enabled", True):
        log.info("텔레그램 알림 비활성화 (UI 설정) — 스킵")
        return

    min_prob = float(cfg.get("min_prob", 0.22))
    max_risk = float(cfg.get("max_risk", 0.60))
    min_rr   = float(cfg.get("min_risk_reward", 2.0))

    ssl   = "require" if "supabase" in dsn else False
    since = datetime.now(timezone.utc) - timedelta(minutes=_WINDOW_MIN)
    conn  = await asyncpg.connect(dsn, statement_cache_size=0, ssl=ssl)
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
    finally:
        await conn.close()

    if not rows:
        log.info(f"최근 {_WINDOW_MIN}분 내 신규 추천 없음")
        return

    sent = 0
    for row in rows:
        r    = dict(row)
        prob = float(r.get("success_prob") or 0)
        risk = float(r.get("risk_score")   or 0)
        rr   = float(r.get("risk_reward_ratio") or 0)

        # 중복 방지
        if _is_sent(r["id"]):
            log.debug(f"이미 발송됨 스킵: {r['code']} id={r['id']}")
            continue

        # UI 설정 필터
        if prob < min_prob:
            log.debug(f"스킵 {r['code']}: prob={prob:.3f} < min_prob={min_prob:.3f}")
            continue
        if risk > max_risk:
            log.debug(f"스킵 {r['code']}: risk={risk:.3f} > max_risk={max_risk:.3f}")
            continue
        if rr < min_rr:
            log.debug(f"스킵 {r['code']}: rr={rr:.2f} < min_rr={min_rr:.2f}")
            continue

        text = _format_message(r)
        ok   = _send_telegram(text)
        if ok:
            _mark_sent(r["id"])
            sent += 1
            log.info(f"✅ 발송 완료: {r['code']} ({r.get('name','')})")
        else:
            log.warning(f"❌ 발송 실패: {r['code']}")

    log.info(f"텔레그램 알림 완료: {sent}건 발송 / {len(rows)}건 조회")


if __name__ == "__main__":
    asyncio.run(main())

"""
장중 인트라데이 신호 알림 + 미니 추천 생성.

supply_worker 완료 후 실행. 최근 60분 feature_events 중 미처리된 이벤트를
간단한 규칙 기반으로 추천 DB에 저장하고 Telegram 알림을 발송한다.

의존성: asyncpg, orjson (collector requirements에 포함) + stdlib
"""
import asyncio
import json
import logging
import os
import sys
import orjson
import asyncpg
from datetime import datetime, timedelta, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [intraday-notify] %(levelname)s %(message)s",
)
logger = logging.getLogger("intraday-notify")

_KST       = timezone(timedelta(hours=9))
# 추천 생성 기준
MIN_SCORE    = float(os.environ.get("INTRADAY_MIN_SCORE",  "0.55"))
LOOKBACK_MIN = int(os.environ.get("INTRADAY_LOOKBACK_MIN", "60"))
MAX_TG_RECS  = int(os.environ.get("INTRADAY_MAX_RECS",     "5"))


# ── 텔레그램 설정 (Redis telegram:config 연동) ─────────────────

def _load_tg_config() -> dict:
    """Redis에서 설정 UI 값 조회. REDIS_URL 없거나 실패 시 env 기본값."""
    default = {
        "enabled":  os.environ.get("TELEGRAM_ENABLED", "1") == "1",
        "min_prob": float(os.environ.get("REC_MIN_PROB", "0.22")),
        "max_risk": float(os.environ.get("REC_MAX_RISK", "0.60")),
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
            logger.info(
                f"Redis 설정 로드: enabled={cfg.get('enabled')} "
                f"min_prob={cfg.get('min_prob'):.3f}"
            )
            return cfg
    except Exception as e:
        logger.warning(f"Redis 설정 로드 실패, env 기본값 사용: {e}")
    return default


# ── 메인 로직 전 헬퍼 ──────────────────────────────────────────


# ── 메인 로직 ──────────────────────────────────────────────────

async def run(db: asyncpg.Pool) -> None:
    cfg      = _load_tg_config()
    since    = datetime.now(timezone.utc) - timedelta(minutes=LOOKBACK_MIN)
    tg_min   = float(cfg.get("min_prob", MIN_SCORE))
    tg_enabled = cfg.get("enabled", True)

    # 최근 LOOKBACK_MIN분 내 탐지된 이벤트 중 추천이 없는 것 (종목명 JOIN 포함)
    events = await db.fetch(
        """
        SELECT fe.id, fe.code, COALESCE(s.name, fe.code) AS name,
               fe.event_type, fe.price, fe.signal_score,
               fe.change_rate, fe.detected_at
        FROM   feature_events fe
        LEFT JOIN stocks s ON s.code = fe.code
        LEFT JOIN recommendations r ON r.feature_event_id = fe.id
        WHERE  fe.detected_at >= $1
          AND  fe.signal_score >= $2
          AND  r.id IS NULL
        ORDER BY fe.signal_score DESC
        LIMIT  50
        """,
        since, tg_min,
    )

    if not events:
        logger.info("신규 인트라데이 신호 없음")
        return

    logger.info(f"미처리 신호 {len(events)}건 → 추천 생성")

    inserted = []
    for ev in events:
        price  = ev["price"] or 0
        score  = float(ev["signal_score"] or 0)
        action = "BUY" if score >= 0.60 else "WAIT"

        target     = int(price * 1.06) if price else None   # +6% → RR=2.0
        stop       = int(price * 0.97) if price else None   # -3%
        entry_low  = int(price * 0.99) if price else None
        entry_high = int(price * 1.01) if price else None
        expired_at = datetime.now(timezone.utc) + timedelta(days=1)

        rationale = orjson.dumps({
            "source":       "INTRADAY",
            "event_type":   ev["event_type"],
            "signal_score": score,
        }).decode()

        try:
            row = await db.fetchrow(
                """
                INSERT INTO recommendations
                    (feature_event_id, code, action,
                     entry_price, entry_price_low, entry_price_high,
                     target_price, stop_loss_price,
                     expected_hold_days, success_prob,
                     expected_return, risk_score, risk_reward_ratio,
                     rationale, expired_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14::jsonb,$15)
                RETURNING id
                """,
                ev["id"], ev["code"], action,
                price, entry_low, entry_high,
                target, stop,
                3, round(score, 3),
                5.0, round(1.0 - score, 3), 1.67,
                rationale, expired_at,
            )
            if row:
                inserted.append({
                    "code":              ev["code"],
                    "name":              ev["name"],
                    "event_type":        ev["event_type"],
                    "price":             price,
                    "target":            target or 0,
                    "stop":              stop or 0,
                    "score":             score,
                    "risk_score":        round(1.0 - score, 3),
                    "risk_reward_ratio": round((target - price) / (price - stop), 2) if (price and stop and target and price != stop) else 2.0,
                    "action":            action,
                    "detected_at":       ev["detected_at"],
                })
                logger.info(f"  추천 저장: {ev['code']} {ev['event_type']} score={score:.3f} → {action}")
        except Exception as e:
            logger.warning(f"  추천 저장 실패 [{ev['code']}]: {e}")

    if not inserted:
        return

    # ── Redis ch:signal-generated 발행 → notifier 단일 채널 처리 ──
    redis_url = os.environ.get("REDIS_URL", "")
    if not redis_url:
        logger.info("REDIS_URL 미설정 — Telegram 발행 스킵")
        return

    import redis.asyncio as aioredis
    rc = aioredis.from_url(redis_url)
    buy_signals = [r for r in inserted if r["action"] == "BUY"]
    top = sorted(buy_signals, key=lambda x: -x["score"])[:MAX_TG_RECS]
    logger.info(f"ch:signal-generated 발행: {len(top)}건 / BUY {len(buy_signals)}건")
    now_iso = datetime.now(timezone.utc).isoformat()
    for r in top:
        detected = r["detected_at"]
        try:
            dt_iso = detected.isoformat() if hasattr(detected, "isoformat") else str(detected)
        except Exception:
            dt_iso = now_iso
        payload = json.dumps({
            "code":              r["code"],
            "name":              r["name"],
            "success_prob":      r["score"],
            "risk_score":        r["risk_score"],
            "risk_reward_ratio": r["risk_reward_ratio"],
            "entry_price":       r["price"],
            "target_price":      r["target"],
            "stop_loss_price":   r["stop"],
            "created_at":        dt_iso,
            "rationale":         {"event_type": r["event_type"], "source": "intraday_notify"},
        }, ensure_ascii=False)
        await rc.publish("ch:signal-generated", payload)
        logger.info(f"  발행: {r['code']} ({r['event_type']}) score={r['score']:.3f}")
    await rc.aclose()


async def main() -> None:
    dsn = os.environ.get("POSTGRES_DSN", "")
    if not dsn:
        logger.error("POSTGRES_DSN 환경변수 없음")
        sys.exit(1)
    dsn = dsn.replace("+asyncpg", "")
    ssl_val = "require" if "supabase" in dsn else False
    db = await asyncpg.create_pool(
        dsn=dsn, min_size=1, max_size=3,
        ssl=ssl_val, statement_cache_size=0,
    )
    try:
        await run(db)
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())

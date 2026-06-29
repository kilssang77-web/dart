from fastapi import APIRouter, Depends, Query, HTTPException
import asyncpg
import orjson
import os
import redis.asyncio as redis_lib
from deps import get_db, get_redis

router = APIRouter()

# 외국인/기관 수급 판단 최소 주수 임계값 (주)
_SUPPLY_THRESH = int(os.environ.get("SUPPLY_THRESH_SHARES", "500000"))


@router.get("")
async def list_stocks(
    market: str | None = None,
    sector: str | None = None,
    q: str | None = None,
    limit: int = Query(default=50, le=500),
    db: asyncpg.Pool = Depends(get_db),
):
    # 모든 조건은 asyncpg 파라미터 바인딩($N)으로 처리한다.
    # where 리스트에는 오직 고정 SQL 조각 또는 $N 플레이스홀더만 추가할 것.
    where: list[str] = ["is_active = TRUE"]
    params: list = []

    def _p(val) -> str:
        params.append(val)
        return f"${len(params)}"

    if market:
        where.append(f"market = {_p(market.upper())}")
    if sector:
        where.append(f"sector ILIKE {_p(sector)}")
    if q:
        like = f"%{q}%"
        p_name = _p(like)
        p_code = _p(like)
        where.append(f"(name ILIKE {p_name} OR code ILIKE {p_code})")

    rows = await db.fetch(
        f"SELECT code, name, market, sector, industry FROM stocks "
        f"WHERE {' AND '.join(where)} ORDER BY market, code LIMIT {_p(limit)}",
        *params,
    )
    return [dict(r) for r in rows]


_DEFAULT_ACTIVE = [
    "005930","000660","035420","005380","051910","006400","035720","028260",
    "207940","068270","323410","105560","055550","086790","032830","066570",
    "003550","096770","033780","015760",
]

@router.get("/active")
async def get_active_stocks(
    redis: redis_lib.Redis = Depends(get_redis),
    db: asyncpg.Pool = Depends(get_db),
):
    """Redis active_codes 기반 실시간 구독 중인 종목 목록 + DB 정보."""
    try:
        cached = await redis.get("stocks:active_codes")
        codes = orjson.loads(cached) if cached else _DEFAULT_ACTIVE
    except Exception:
        codes = _DEFAULT_ACTIVE
    if not codes:
        return []
    rows = await db.fetch(
        "SELECT code, name, market, sector FROM stocks WHERE code = ANY($1::varchar[]) ORDER BY market, code",
        codes,
    )
    return [dict(r) for r in rows]


@router.get("/{code}/orderbook")
async def get_orderbook(
    code: str,
    redis: redis_lib.Redis = Depends(get_redis),
):
    """호가 잔량 — Redis 캐시 우선(collector가 30s 갱신), 없으면 빈 응답."""
    try:
        raw = await redis.get(f"orderbook:{code}")
        if raw:
            import orjson as _orjson
            return _orjson.loads(raw)
    except Exception:
        pass
    return {"code": code, "asks": [], "bids": [], "total_ask_qty": 0, "total_bid_qty": 0}


@router.get("/{code}")
async def get_stock(code: str, db: asyncpg.Pool = Depends(get_db)):
    row = await db.fetchrow("SELECT * FROM stocks WHERE code = $1", code)
    if not row:
        raise HTTPException(404, "Stock not found")
    return dict(row)


@router.get("/{code}/daily")
async def get_daily_bars(
    code: str,
    days: int = Query(default=60, le=780),
    db: asyncpg.Pool = Depends(get_db),
):
    rows = await db.fetch(
        """
        SELECT date::TEXT, open, high, low, close, volume, amount,
               change_rate, adj_close, foreign_net_buy, inst_net_buy,
               ma5, ma20, ma60, ma120, rsi14, bb_upper, bb_lower
        FROM daily_bars
        WHERE code = $1
        ORDER BY date DESC
        LIMIT $2
        """,
        code, days,
    )
    return [dict(r) for r in reversed(rows)]  # daily end


@router.get("/{code}/supply")
async def get_supply_demand(
    code: str,
    days: int = Query(default=20, le=60),
    db: asyncpg.Pool = Depends(get_db),
):
    rows = await db.fetch(
        """
        SELECT date::TEXT, foreign_net, inst_net, indiv_net,
               prog_arbitrage_net, foreign_hold_rate
        FROM supply_demand
        WHERE code = $1
        ORDER BY date DESC
        LIMIT $2
        """,
        code, days,
    )
    if not rows:
        # supply_demand 미적재 시 daily_bars 컬럼으로 폴백 (write_supply_demand가 기록한 값)
        rows = await db.fetch(
            """
            SELECT date::TEXT,
                   foreign_net_buy   AS foreign_net,
                   inst_net_buy      AS inst_net,
                   indiv_net_buy     AS indiv_net,
                   prog_net_buy      AS prog_arbitrage_net,
                   NULL::numeric     AS foreign_hold_rate
            FROM daily_bars
            WHERE code = $1
              AND (foreign_net_buy != 0 OR inst_net_buy != 0)
            ORDER BY date DESC
            LIMIT $2
            """,
            code, days,
        )
    return [dict(r) for r in reversed(rows)]


# ── 기술적 분석 헬퍼 ─────────────────────────────────────────────
def _compute_atr(bars: list[dict]) -> float | None:
    if len(bars) < 2:
        return None
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i]["high"], bars[i]["low"], bars[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs) if trs else None


def _round_price(p: float, base: float) -> int:
    if base >= 100_000:
        return round(p / 100) * 100
    elif base >= 10_000:
        return round(p / 50) * 50
    else:
        return round(p / 10) * 10



def _generate_opinion(
    name: str,
    code: str,
    current_price: float,
    tech: dict,
    supply: dict,
    ml_signal: dict | None,
    news_rows: list,
    disc_rows: list,
    purchase_analysis: dict | None = None,
) -> str:
    parts: list[str] = []
    trend       = tech["trend"]
    trend_score = tech["trend_score"]
    rsi         = tech.get("rsi")
    w52_pct     = tech.get("w52_pct", 0.5)
    vol_ratio   = tech.get("vol_ratio", 1.0)
    ma5, ma20, ma60 = tech.get("ma5"), tech.get("ma20"), tech.get("ma60")

    if ma5 and ma20 and ma60:
        if ma5 > ma20 > ma60:
            align = "MA5/MA20/MA60 정배열 구조로 상승 추세가 뚜렷합니다."
        elif ma5 < ma20 < ma60:
            align = "MA5/MA20/MA60 역배열 구조로 하락 압력이 지속되고 있습니다."
        else:
            align = "이동평균선이 혼재되어 방향성이 불확실한 구간입니다."
    else:
        align = "이동평균 데이터가 충분히 쌓이지 않았습니다."
    parts.append(
        f"▸ 주가 흐름: {name}({code}) 현재가 {int(current_price):,}원. "
        f"기술적 추세는 '{trend}'으로 판단됩니다. {align}"
    )

    if rsi is not None:
        if rsi < 30:
            parts.append(f"▸ 기술적 신호: RSI {float(rsi):.1f}로 과매도 구간. 단기 기술적 반등 가능성이 있으나 추세 반전 확인 후 대응이 안전합니다.")
        elif rsi > 70:
            parts.append(f"▸ 기술적 신호: RSI {float(rsi):.1f}로 과매수 구간. 단기 차익 실현 압력에 유의하세요.")
        else:
            parts.append(f"▸ 기술적 신호: RSI {float(rsi):.1f}로 중립 구간에서 안정적입니다.")

    w52_pos = float(w52_pct) * 100
    if w52_pos >= 80:
        parts.append(f"▸ 가격 위치: 52주 범위 상위 {100 - w52_pos:.0f}% 근처 신고가 근접 구간. 돌파 시 추가 상승 가능하나 고점 부담도 존재합니다.")
    elif w52_pos <= 20:
        parts.append(f"▸ 가격 위치: 52주 저가 근처({w52_pos:.0f}% 구간). 가격 메리트는 있으나 하락 추세 지속 여부 확인이 필요합니다.")
    else:
        parts.append(f"▸ 가격 위치: 52주 범위 내 {w52_pos:.0f}% 구간에 위치합니다.")

    if vol_ratio >= 2.0:
        parts.append(f"▸ 거래량: 20일 평균 대비 {float(vol_ratio):.1f}배로 급증. 큰 손의 관심이 집중된 것으로 보입니다.")
    elif vol_ratio >= 1.5:
        parts.append(f"▸ 거래량: 20일 평균 대비 {float(vol_ratio):.1f}배로 증가 추세입니다.")

    f5 = supply.get("foreign_5d", 0)
    i5 = supply.get("inst_5d", 0)
    sup_parts: list[str] = []
    if abs(f5) > _SUPPLY_THRESH:
        sup_parts.append(f"외국인 5일 {'순매수' if f5 > 0 else '순매도'} {abs(f5)/10_000:.0f}만주")
    if abs(i5) > _SUPPLY_THRESH:
        sup_parts.append(f"기관 5일 {'순매수' if i5 > 0 else '순매도'} {abs(i5)/10_000:.0f}만주")
    if sup_parts:
        both_buy  = f5 > _SUPPLY_THRESH  and i5 > _SUPPLY_THRESH
        both_sell = f5 < -_SUPPLY_THRESH and i5 < -_SUPPLY_THRESH
        suffix = " 외국인/기관 동반 매수로 긍정적 수급 흐름입니다." if both_buy \
            else " 외국인/기관 동반 매도로 수급 부담이 존재합니다." if both_sell else ""
        parts.append(f"▸ 수급: {', '.join(sup_parts)}.{suffix}")

    if ml_signal:
        action = ml_signal.get("action")
        prob   = ml_signal.get("prob")
        if action == "BUY" and prob:
            parts.append(f"▸ ML 신호: 매수 신호 발생 (성공 확률 {float(prob)*100:.1f}%). 기술적 분석과 병행해 진입 타이밍을 검토하세요.")
        elif action == "WAIT":
            parts.append("▸ ML 신호: 현재 진입 대기 신호입니다. 추가 데이터 누적 후 재판단이 권장됩니다.")

    if news_rows:
        scores = [float(r["sentiment_score"]) for r in news_rows if r.get("sentiment_score") is not None]
        avg_s = sum(scores) / len(scores) if scores else 0
        sent_desc = "긍정적" if avg_s > 0.1 else "부정적" if avg_s < -0.1 else "중립적"
        headlines = " / ".join(
            (r["title"][:25] + "..." if len(r["title"]) > 25 else r["title"]) for r in news_rows[:2]
        )
        parts.append(f"▸ 최근 뉴스: {len(news_rows)}건 중 평균 감성 '{sent_desc}'. 주요 헤드라인: {headlines}")

    if disc_rows:
        favorable   = [r for r in disc_rows if r.get("category") == "favorable"]
        unfavorable = [r for r in disc_rows if r.get("category") == "unfavorable"]
        if favorable:
            t = favorable[0]["title"][:30]
            parts.append(f"▸ 공시: 최근 호재성 공시 {len(favorable)}건 확인 ('{t}...'). 긍정적 재료가 반영될 수 있습니다.")
        elif unfavorable:
            t = unfavorable[0]["title"][:30]
            parts.append(f"▸ 공시: 최근 악재성 공시 {len(unfavorable)}건 확인 ('{t}...'). 하방 압력 요인에 유의하세요.")
        else:
            parts.append(f"▸ 공시: 최근 중립 공시 {len(disc_rows)}건, 시장 영향은 제한적으로 판단됩니다.")

    conclusion_score = float(trend_score)
    if ml_signal and ml_signal.get("action") == "BUY":
        conclusion_score += 1.0
    if f5 > 1_000_000:
        conclusion_score += 0.5
    if disc_rows and any(r.get("category") == "favorable" for r in disc_rows):
        conclusion_score += 0.5
    if news_rows:
        ns = [float(r["sentiment_score"]) for r in news_rows if r.get("sentiment_score") is not None]
        if ns and sum(ns)/len(ns) > 0.1:
            conclusion_score += 0.3

    if conclusion_score >= 3:
        verdict = "기술적/수급/뉴스 등 복합 지표가 전반적으로 긍정적입니다. 단기 모멘텀을 활용한 분할 매수 전략이 유효해 보입니다. 단, 손절 라인 설정은 필수입니다."
    elif conclusion_score >= 1:
        verdict = "전반적으로 완만한 상승 우위이나 강한 확신은 없습니다. 소량 선진입 후 추세 확인에 따른 추가 매수 방식이 적합합니다."
    elif conclusion_score >= -1:
        verdict = "뚜렷한 방향성 없이 횡보 국면입니다. 명확한 방향성 돌파 확인 전까지 관망을 권장합니다."
    elif conclusion_score >= -3:
        verdict = "하락 압력이 우세한 구간입니다. 보유 중이라면 손절 기준을 엄격히 적용하고, 신규 진입은 추세 반전 확인 후로 미루세요."
    else:
        verdict = "여러 지표가 강한 하락 추세를 지시하고 있습니다. 현 시점 신규 매수는 위험하며, 보유 포지션은 적극적인 손실 관리가 필요합니다."

    parts.append(f"\n★ 종합 의견: {verdict}")
    if purchase_analysis:
        pp            = purchase_analysis["purchase_price"]
        cr            = purchase_analysis["current_return"]
        pnl           = purchase_analysis["pnl"]
        score         = purchase_analysis["sell_score"]
        action_v      = purchase_analysis["action"]
        trailing_stop = purchase_analysis["trailing_stop"]
        atr_mult_ts   = purchase_analysis.get("atr_mult_ts", 2.0)
        fwd           = purchase_analysis.get("forward_targets", [])

        sgn      = "+" if cr >= 0 else ""
        pnl_text = f"({sgn}{int(pnl):,}원, {sgn}{cr:.1f}%)"

        if score >= 50:    score_desc = "강한 보유 신호"
        elif score >= 20:  score_desc = "보유 우세"
        elif score >= 0:   score_desc = "중립 (부분 익절 검토)"
        elif score >= -30: score_desc = "매도 우세"
        else:              score_desc = "강한 매도 신호"

        if action_v == "STOP_LOSS":
            act_text = "⚠ 손절 기준(-5%) 이탈 — 즉시 또는 반등 시 청산 강력 권장"
        elif action_v == "FULL_EXIT":
            act_text = "전량 청산 권장 (ML·뉴스·공시 복합 부정 신호)"
        elif action_v == "PARTIAL_EXIT_LARGE":
            act_text = "50~70% 분할 익절 후 나머지는 트레일링 스탑 적용"
        elif action_v == "PARTIAL_EXIT":
            act_text = "30~50% 분할 익절 후 나머지는 트레일링 스탑 보유"
        else:
            act_text = "트레일링 스탑 적용하며 보유 지속 (긍정 신호 유지)"

        ts_drop_pct = (current_price - trailing_stop) / current_price * 100

        sell_lines = [
            f"\n★ 매도 전략 (매수가 {int(pp):,}원 · 현재 {int(current_price):,}원 · {pnl_text}):",
            f"  • 종합 신호: {score_desc} (점수 {chr(43) if score >= 0 else chr(45)}{score}/100)",
            f"  • 전략 방향: {act_text}",
            f"  • 트레일링 스탑: {int(trailing_stop):,}원 (현재가 -{ts_drop_pct:.1f}% · ATR×{atr_mult_ts:.1f})",
        ]
        for t in fwd:
            sell_lines.append(
                f"  • {t['label']}: {int(t['price']):,}원 (현재가 대비 +{t['ret_pct']:.1f}%)"
            )
        ml_act  = (ml_signal or {}).get("action", "—")
        ml_pb   = (ml_signal or {}).get("probability")
        ml_str  = ml_act + (f" {ml_pb*100:.0f}%" if ml_pb else "")
        fav_n   = sum(1 for n in news_rows if (n.get("category") or n.get("sentiment_category")) == "favorable")
        unfv_n  = sum(1 for n in news_rows if (n.get("category") or n.get("sentiment_category")) == "unfavorable")
        news_str = f"호재 {fav_n}건" if fav_n > unfv_n else (f"악재 {unfv_n}건" if unfv_n > 0 else "중립")
        fav_d   = sum(1 for d in disc_rows if d.get("category") == "favorable")
        unfv_d  = sum(1 for d in disc_rows if d.get("category") == "unfavorable")
        disc_str = f"호재성 {fav_d}건" if fav_d else (f"악재성 {unfv_d}건" if unfv_d else "없음")
        sell_lines.append(
            f"  ▸ 반영 근거: ML={ml_str} · 뉴스={news_str} · 공시={disc_str}"
        )
        sell_section = "\n".join(sell_lines)
        parts.append(sell_section)

    return "\n".join(parts)
@router.get("/{code}/analysis")
async def get_stock_analysis(
    code: str,
    purchase_price: float | None = Query(default=None, description="매수가 (보유 중인 경우)"),
    db: asyncpg.Pool = Depends(get_db),
    redis: redis_lib.Redis = Depends(get_redis),
):
    code = code.upper()

    # purchase_price 없는 기본 조회는 30초 캐싱
    _cache_key = f"cache:analysis:{code}"
    if purchase_price is None:
        try:
            _cached = await redis.get(_cache_key)
            if _cached:
                import orjson as _orjson
                return _orjson.loads(_cached)
        except Exception:
            pass

    stock = await db.fetchrow("SELECT * FROM stocks WHERE code = $1", code)
    if not stock:
        raise HTTPException(404, "Stock not found")

    raw_bars = await db.fetch(
        """
        SELECT date::TEXT, open, high, low, close, volume, amount,
               change_rate, ma5, ma20, ma60, ma120, rsi14, bb_upper, bb_lower,
               foreign_net_buy, inst_net_buy
        FROM daily_bars WHERE code = $1 ORDER BY date DESC LIMIT 120
        """,
        code,
    )
    bars = [dict(b) for b in reversed(raw_bars)]

    rec_row = await db.fetchrow(
        """
        SELECT action, entry_price, target_price, stop_loss_price,
               success_prob, expected_return, risk_reward_ratio, (created_at AT TIME ZONE 'Asia/Seoul')::TEXT AS created_at
        FROM recommendations WHERE code = $1 ORDER BY created_at DESC LIMIT 1
        """,
        code,
    )
    rec = dict(rec_row) if rec_row else None

    current_price: float | None = None
    try:
        cached = await redis.get(f"quote:{code}")
        if cached:
            tick = orjson.loads(cached)
            current_price = tick.get("price")
    except Exception:
        pass

    if not bars:
        return {"code": code, "name": stock["name"], "error": "데이터 없음",
                "current_price": None, "technical": {}, "predictions": {}, "targets": {}}

    latest = bars[-1]
    if not current_price:
        current_price = float(latest["close"])

    ma5      = latest.get("ma5")
    ma20     = latest.get("ma20")
    ma60     = latest.get("ma60")
    rsi      = latest.get("rsi14")
    bb_upper = latest.get("bb_upper")
    bb_lower = latest.get("bb_lower")
    atr_val  = _compute_atr(bars[-15:]) or current_price * 0.025

    year_bars = bars[-min(252, len(bars)):]
    w52_high  = max(b["high"] for b in year_bars)
    w52_low   = min(b["low"]  for b in year_bars)
    w52_pct   = (current_price - w52_low) / (w52_high - w52_low) if w52_high != w52_low else 0.5

    avg_vol_5  = sum(b["volume"] for b in bars[-5:])  / 5  if len(bars) >= 5  else 0
    avg_vol_20 = sum(b["volume"] for b in bars[-20:]) / 20 if len(bars) >= 20 else 1
    vol_ratio  = avg_vol_5 / avg_vol_20 if avg_vol_20 > 0 else 1.0

    trend_score   = 0.0
    trend_reasons: list[str] = []

    if ma5 and ma20:
        if ma5 > ma20:
            trend_score += 2
            trend_reasons.append(f"MA5({int(ma5):,}) > MA20({int(ma20):,}) — 단기 상승추세")
        else:
            trend_score -= 2
            trend_reasons.append(f"MA5({int(ma5):,}) < MA20({int(ma20):,}) — 단기 하락추세")
    if ma20 and ma60:
        if ma20 > ma60:
            trend_score += 2
            trend_reasons.append(f"MA20({int(ma20):,}) > MA60({int(ma60):,}) — 중기 상승추세")
        else:
            trend_score -= 2
            trend_reasons.append(f"MA20({int(ma20):,}) < MA60({int(ma60):,}) — 중기 하락추세")
    if ma5 and ma20 and ma60 and ma5 > ma20 > ma60:
        trend_score += 1
        trend_reasons.append("정배열 (MA5 > MA20 > MA60) — 강한 상승 구조")

    rsi_signal = "normal"
    if rsi is not None:
        if rsi < 30:
            trend_score += 1; rsi_signal = "oversold"
            trend_reasons.append(f"RSI {float(rsi):.1f} — 과매도, 기술적 반등 가능성")
        elif rsi > 70:
            trend_score -= 1; rsi_signal = "overbought"
            trend_reasons.append(f"RSI {float(rsi):.1f} — 과매수, 단기 조정 주의")
        else:
            trend_reasons.append(f"RSI {float(rsi):.1f} — 정상 범위")

    bb_pct: float | None = None
    if bb_upper and bb_lower and bb_upper > bb_lower:
        bb_pct = (current_price - float(bb_lower)) / (float(bb_upper) - float(bb_lower))
        if bb_pct < 0.2:
            trend_score += 0.5
            trend_reasons.append("볼린저 밴드 하단 근접 — 매수 관심 구간")
        elif bb_pct > 0.8:
            trend_score -= 0.5
            trend_reasons.append("볼린저 밴드 상단 근접 — 과열 주의")

    if vol_ratio > 1.5:
        trend_score += 0.5
        trend_reasons.append(f"거래량 급증 (20일 대비 {vol_ratio:.1f}배)")

    supply_rows = await db.fetch(
        """ SELECT foreign_net, inst_net FROM supply_demand WHERE code = $1 ORDER BY date DESC LIMIT 5 """,
        code,
    )
    if supply_rows:
        supply_foreign = sum((r["foreign_net"] or 0) for r in supply_rows)
        supply_inst    = sum((r["inst_net"]    or 0) for r in supply_rows)
    else:
        supply_foreign = sum((b.get("foreign_net_buy") or 0) for b in bars[-5:]) if len(bars) >= 5 else 0
        supply_inst    = sum((b.get("inst_net_buy")    or 0) for b in bars[-5:]) if len(bars) >= 5 else 0
    supply_signal  = None
    supply_reasons: list[str] = []
    _THRESH = 1_000_000  # 100만주 임계값
    def _fmt_shares(v: int) -> str:
        a = abs(v); s = '+' if v >= 0 else '-'
        if a >= 10_000_000: return f'{s}{a/10_000_000:.1f}천만주'
        if a >= 1_000_000:  return f'{s}{a/1_000_000:.1f}백만주'
        if a >= 10_000:     return f'{s}{a/10_000:.1f}만주'
        return f'{s}{a:,}주'
    if supply_foreign > _THRESH:
        trend_score += 0.5; supply_signal = "외국인 순매수"
        supply_reasons.append(f"외국인 5일 순매수 {_fmt_shares(supply_foreign)}")
    elif supply_foreign < -_THRESH:
        trend_score -= 0.5; supply_signal = "외국인 순매도"
        supply_reasons.append(f"외국인 5일 순매도 {_fmt_shares(supply_foreign)}")
    if supply_inst > _THRESH:
        trend_score += 0.3
        supply_reasons.append(f"기관 5일 순매수 {_fmt_shares(supply_inst)}")
    elif supply_inst < -_THRESH:
        trend_score -= 0.3
        supply_reasons.append(f"기관 5일 순매도 {_fmt_shares(supply_inst)}")

    ml_signal = None
    if rec:
        ml_signal = {
            "action":     rec["action"],
            "prob":       float(rec["success_prob"]) if rec.get("success_prob") else None,
            "entry":      rec.get("entry_price"),
            "target":     rec.get("target_price"),
            "stop":       rec.get("stop_loss_price"),
            "created_at": rec.get("created_at"),
        }
        if rec.get("action") == "BUY" and rec.get("success_prob"):
            trend_score += 1
            trend_reasons.append(f"ML 매수 신호 (확률 {float(rec['success_prob'])*100:.1f}%)")

    TREND_MAP = {
        (4, 99):   ("강한 상승",   "strong_up"),
        (2, 4):    ("상승 우위",   "up"),
        (0.5, 2):  ("완만한 상승", "up_mild"),
        (-0.5, 0.5):("중립/횡보",  "sideways"),
        (-2, -0.5):("완만한 하락", "down_mild"),
        (-4, -2):  ("하락 우위",   "down"),
        (-99, -4): ("강한 하락",   "strong_down"),
    }
    trend, trend_dir = "중립/횡보", "sideways"
    for (lo, hi), (lbl, d) in TREND_MAP.items():
        if lo <= trend_score < hi:
            trend, trend_dir = lbl, d
            break

    rp = lambda p: _round_price(p, current_price)

    UP   = ("strong_up", "up", "up_mild")
    DN   = ("strong_down", "down", "down_mild")
    MULT = {"strong_up": (0.5, 1.8, 3.2), "up": (0.7, 1.5, 2.8), "up_mild": (1.0, 1.0, 2.0),
            "sideways": (1.2, 0.0, 1.2), "down_mild": (2.5, -1.0, 0.5),
            "down": (3.0, -2.0, 0.0), "strong_down": (3.5, -2.5, -0.5)}
    lm, mm, hm = MULT.get(trend_dir, (1.0, 0.0, 1.0))
    s_low  = rp(current_price - atr_val * (lm if trend_dir in DN else (1.0 if trend_dir == "sideways" else lm)))
    s_high = rp(current_price + atr_val * hm) if hm >= 0 else rp(current_price - atr_val * abs(hm))
    s_mid  = rp(current_price + atr_val * mm) if mm >= 0 else rp(current_price - atr_val * abs(mm))

    short_conf = min(0.82, 0.45 + abs(trend_score) * 0.06)
    short_reasons = (trend_reasons[:3] + [f"ATR14 ≈ {int(atr_val):,}원 변동성 기반"])[:4]

    MF_MAP = {"strong_up": 0.10, "up": 0.07, "up_mild": 0.04, "sideways": 0.01,
              "down_mild": -0.04, "down": -0.07, "strong_down": -0.10}
    mf = MF_MAP.get(trend_dir, 0.01)
    m_low, m_mid, m_high = rp(current_price*(1+mf-0.04)), rp(current_price*(1+mf)), rp(current_price*(1+mf+0.06))
    mid_reasons = [r for r in trend_reasons if any(k in r for k in ["MA20","MA60","볼린저","외국인","기관"])][:3] or ["이동평균 추세 방향 기반 중기 전망"]
    mid_conf = min(0.72, 0.35 + abs(trend_score) * 0.05)

    if len(bars) >= 60 and bars[-1].get("ma60") and bars[-60].get("ma60"):
        slope  = (float(bars[-1]["ma60"]) - float(bars[-60]["ma60"])) / float(bars[-60]["ma60"])
        annual = max(-0.30, min(0.40, slope * 6))
    else:
        annual = 0.08
    l_low, l_mid, l_high = rp(current_price*(1+annual-0.12)), rp(current_price*(1+annual)), rp(current_price*(1+annual+0.15))
    long_reasons = ["60일 이동평균 기울기 기반 추세 외삽"]
    if ma60:
        rel = "위" if current_price > float(ma60) else "아래"
        long_reasons.append(f"현재가 MA60({int(ma60):,}원) {rel} — 장기 추세 {'지지' if rel=='위' else '압박'}")
    long_conf = min(0.60, 0.28 + abs(trend_score) * 0.04)

    predictions = {
        "short": {"label": "단기 (1–5일)",    "direction": "상승" if trend_dir in UP else ("하락" if trend_dir in DN else "횡보"), "low": s_low, "mid": s_mid, "high": s_high, "confidence": round(short_conf, 2), "reasons": short_reasons},
        "mid":   {"label": "중기 (1–3개월)",  "direction": "상승" if mf > 0.01 else ("하락" if mf < -0.01 else "횡보"),         "low": m_low, "mid": m_mid, "high": m_high, "confidence": round(mid_conf, 2),   "reasons": mid_reasons},
        "long":  {"label": "장기 (3–12개월)", "direction": "상승" if annual > 0.02 else ("하락" if annual < -0.02 else "횡보"),  "low": l_low, "mid": l_mid, "high": l_high, "confidence": round(long_conf, 2),  "reasons": long_reasons},
    }

    targets = {
        "aggressive":   {"label": "공격형", "buy": rp(current_price), "target": rp(current_price*1.15), "stop": rp(current_price*0.93), "rr": round(0.15/0.07, 1), "desc": "목표 +15% / 손절 -7% — 단기 고수익 추구, 변동성 감수"},
        "conservative": {"label": "보수형", "buy": rp(current_price), "target": rp(current_price*1.08), "stop": rp(current_price*0.95), "rr": round(0.08/0.05, 1), "desc": "목표 +8% / 손절 -5% — 수익·위험 균형형"},
        "safe":         {"label": "안전형", "buy": rp(current_price), "target": rp(current_price*1.05), "stop": rp(current_price*0.97), "rr": round(0.05/0.03, 1), "desc": "목표 +5% / 손절 -3% — 손실 최소화 우선"},
    }
    if ml_signal and ml_signal.get("target") and ml_signal["target"] > current_price:
        targets["aggressive"]["target"] = max(targets["aggressive"]["target"], rp(ml_signal["target"]))
    if ml_signal and ml_signal.get("stop") and ml_signal["stop"] < current_price:
        targets["safe"]["stop"] = max(targets["safe"]["stop"], rp(ml_signal["stop"]))

    purchase_analysis = None

    # 뉴스 최근 5건
    news_raw = await db.fetch(
        """
        SELECT n.title, (n.published_at AT TIME ZONE 'Asia/Seoul')::TEXT AS published_at, n.sentiment_score
        FROM news n
        JOIN news_stock_links nsl ON nsl.news_id = n.id
        WHERE nsl.code = $1
        ORDER BY n.published_at DESC
        LIMIT 5
        """,
        code,
    )
    news_recent = [dict(r) for r in news_raw]

    # 공시 최근 5건
    disc_raw = await db.fetch(
        """
        SELECT rcept_no, title, (disclosed_at AT TIME ZONE 'Asia/Seoul')::TEXT AS disclosed_at, category, sentiment_score
        FROM disclosures
        WHERE code = $1
        ORDER BY disclosed_at DESC
        LIMIT 5
        """,
        code,
    )
    disc_recent = [dict(r) for r in disc_raw]

    if purchase_price and purchase_price > 0:
        cur_ret = (current_price - purchase_price) / purchase_price * 100

        # 종합 매도 신호 점수 (-100~+100, 양수=보유 우세)
        sell_score = 0
        ml_action_v = (ml_signal or {}).get("action", "WAIT")
        ml_prob_v   = float((ml_signal or {}).get("prob") or 0.5)
        if ml_action_v == "BUY":    sell_score += 25
        elif ml_action_v == "SKIP": sell_score -= 30
        sell_score += int((ml_prob_v - 0.5) * 40)

        fav_n  = sum(1 for n in news_recent if (n.get("category") or n.get("sentiment_category")) == "favorable")
        unfv_n = sum(1 for n in news_recent if (n.get("category") or n.get("sentiment_category")) == "unfavorable")
        if fav_n > unfv_n:   sell_score += 15
        elif unfv_n > fav_n: sell_score -= 20

        fav_d  = sum(1 for d in disc_recent if d.get("category") == "favorable")
        unfv_d = sum(1 for d in disc_recent if d.get("category") == "unfavorable")
        if fav_d  > 0: sell_score += 10
        if unfv_d > 0: sell_score -= 25

        if len(bars) >= 5:
            p5   = bars[-5]["close"] or current_price
            mom5 = (current_price - p5) / p5 * 100
            if mom5 > 3:    sell_score += 10
            elif mom5 < -3: sell_score -= 15

        sell_score = max(-100, min(100, sell_score))

        # ATR 기반 트레일링 스탑 (수익 규모별 원금 보호)
        atr_mult_ts = 2.0 if sell_score > 20 else (1.5 if sell_score > 0 else 1.2)
        trailing_stop_price = rp(current_price - atr_val * atr_mult_ts)
        if cur_ret > 30:  trailing_stop_price = max(trailing_stop_price, rp(purchase_price))
        if cur_ret > 80:  trailing_stop_price = max(trailing_stop_price, rp(purchase_price * 1.2))
        if cur_ret > 150: trailing_stop_price = max(trailing_stop_price, rp(purchase_price * 1.5))

        # 행동 결정
        if current_price <= purchase_price * 0.95:
            action_v = "STOP_LOSS"
        elif sell_score >= 30:
            action_v = "HOLD_TRAIL"
        elif sell_score >= 0:
            action_v = "PARTIAL_EXIT"
        elif sell_score >= -30:
            action_v = "PARTIAL_EXIT_LARGE"
        else:
            action_v = "FULL_EXIT"

        # 현재가 기준 순방향 목표가 (보유/부분익절 시에만)
        forward_targets = []
        if action_v in ("HOLD_TRAIL", "PARTIAL_EXIT"):
            st_price = rp(current_price + atr_val * 1.5)
            mt_price = rp(current_price + atr_val * 3.0)
            forward_targets = [
                {"label": "단기 목표", "price": st_price,
                 "ret_pct": round((st_price - current_price) / current_price * 100, 1)},
                {"label": "중기 목표", "price": mt_price,
                 "ret_pct": round((mt_price - current_price) / current_price * 100, 1)},
            ]

        purchase_analysis = {
            "purchase_price":  purchase_price,
            "current_price":   current_price,
            "current_return":  round(cur_ret, 2),
            "pnl":             round(current_price - purchase_price),
            "sell_score":      sell_score,
            "action":          action_v,
            "trailing_stop":   trailing_stop_price,
            "atr_mult_ts":     atr_mult_ts,
            "forward_targets": forward_targets,
        }

    tech_for_opinion = {
        "trend": trend, "trend_dir": trend_dir, "trend_score": trend_score,
        "rsi": float(rsi) if rsi else None,
        "w52_pct": w52_pct, "vol_ratio": vol_ratio,
        "ma5": float(ma5) if ma5 else None,
        "ma20": float(ma20) if ma20 else None,
        "ma60": float(ma60) if ma60 else None,
    }
    supply_for_opinion = {"foreign_5d": int(supply_foreign), "inst_5d": int(supply_inst)}
    opinion = _generate_opinion(
        stock["name"], code, current_price,
        tech_for_opinion, supply_for_opinion, ml_signal,
        news_recent, disc_recent,
        purchase_analysis,
    )

    result = {
        "code":     code,
        "name":     stock["name"],
        "market":   stock.get("market"),
        "sector":   stock.get("sector"),
        "industry": stock.get("industry"),
        "current_price": current_price,
        "technical": {
            "trend":       trend,
            "trend_dir":   trend_dir,
            "trend_score": round(trend_score, 1),
            "ma5":         float(ma5)      if ma5      else None,
            "ma20":        float(ma20)     if ma20     else None,
            "ma60":        float(ma60)     if ma60     else None,
            "rsi":         float(rsi)      if rsi      else None,
            "rsi_signal":  rsi_signal,
            "bb_upper":    float(bb_upper) if bb_upper else None,
            "bb_lower":    float(bb_lower) if bb_lower else None,
            "bb_pct":      round(bb_pct, 3) if bb_pct is not None else None,
            "atr":         int(atr_val),
            "vol_ratio":   round(vol_ratio, 2),
            "w52_high":    w52_high,
            "w52_low":     w52_low,
            "w52_pct":     round(w52_pct, 3),
            "reasons":     trend_reasons,
        },
        "predictions":       predictions,
        "targets":           targets,
        "ml_signal":         ml_signal,
        "supply": {
            "foreign_5d": int(supply_foreign),
            "inst_5d":    int(supply_inst),
            "signal":     supply_signal,
            "reasons":    supply_reasons,
        },
        "purchase_analysis": purchase_analysis,
        "news_recent":        news_recent,
        "disclosures_recent": disc_recent,
        "opinion":            opinion,
    }

    # purchase_price 없는 경우 결과 캐싱 (30초)
    if purchase_price is None:
        try:
            import orjson as _orjson
            await redis.set(_cache_key, _orjson.dumps(result), ex=30)
        except Exception:
            pass

    return result


@router.post("/{code}/watch", status_code=200)
async def watch_stock(
    code: str,
    redis: redis_lib.Redis = Depends(get_redis),
):
    """종목 상세 열람 시 호출 — collector가 해당 종목 KIS WebSocket 구독 추가 (TTL 3분)."""
    await redis.set(f"watching:{code}", "1", ex=180)
    return {"watching": code}


# ── 관심종목 서버 사이드 동기화 ─────────────────────────────────

@router.post("/favorites/sync", status_code=200)
async def sync_favorites(
    payload: dict,
    redis: redis_lib.Redis = Depends(get_redis),
):
    """브라우저 관심종목 → Redis 동기화. batch_scanner가 active_codes에 포함시킴."""
    codes = payload.get("codes", [])
    if not isinstance(codes, list):
        codes = []
    codes = [str(c).upper()[:6] for c in codes if c][:100]
    await redis.set("user:favorites", orjson.dumps(codes), ex=90_000)
    # watching TTL도 갱신 (실시간 구독 유지)
    for code in codes:
        await redis.set(f"watching:{code}", "1", ex=600)
    return {"synced": len(codes)}


@router.get("/favorites/list")
async def list_favorites(redis: redis_lib.Redis = Depends(get_redis)):
    """현재 서버에 동기화된 관심종목 코드 목록."""
    raw = await redis.get("user:favorites")
    return orjson.loads(raw) if raw else []


@router.get("/{code}/financials")
async def get_financials(
    code: str,
    limit: int = Query(default=8, le=20),
    db: asyncpg.Pool = Depends(get_db),
):
    """분기별 재무정보 (최근 N분기, 최신 순)."""
    rows = await db.fetch(
        """
        SELECT year, quarter, revenue, operating_profit, net_profit,
               eps, bps, per, pbr, roe, debt_ratio
        FROM financials
        WHERE code = $1
        ORDER BY year DESC, quarter DESC NULLS LAST
        LIMIT $2
        """,
        code, limit,
    )
    return [
        {
            "year":             r["year"],
            "quarter":          r["quarter"],
            "revenue":          int(r["revenue"])          if r["revenue"]          is not None else None,
            "operating_profit": int(r["operating_profit"]) if r["operating_profit"] is not None else None,
            "net_profit":       int(r["net_profit"])       if r["net_profit"]       is not None else None,
            "eps":              r["eps"],
            "bps":              r["bps"],
            "per":              float(r["per"])             if r["per"]              is not None else None,
            "pbr":              float(r["pbr"])             if r["pbr"]              is not None else None,
            "roe":              float(r["roe"])             if r["roe"]              is not None else None,
            "debt_ratio":       float(r["debt_ratio"])     if r["debt_ratio"]       is not None else None,
        }
        for r in rows
    ]


@router.get("/{code}/quote")
async def get_stock_quote(
    code: str,
    db: asyncpg.Pool = Depends(get_db),
    redis: redis_lib.Redis = Depends(get_redis),
):
    """실시간 현재가. Redis 캐시(TTL) → daily_bars 순으로 폴백."""
    cached = await redis.get(f"quote:{code}")
    if cached:
        tick = orjson.loads(cached)
        src = tick.get("source", "realtime")
        return {
            "code":        code,
            "price":       tick.get("price"),
            "prev_close":  tick.get("prev_close"),
            "change":      tick.get("change"),
            "change_rate": tick.get("change_rate"),
            "open":        tick.get("open"),
            "high":        tick.get("high"),
            "low":         tick.get("low"),
            "volume":      tick.get("cum_volume") or tick.get("volume"),
            "amount":      tick.get("cum_amount") or tick.get("amount"),
            "source":      src,
        }

    rows = await db.fetch(
        """
        SELECT close AS price, change_rate, volume, amount, open, high, low
        FROM daily_bars WHERE code = $1 ORDER BY date DESC LIMIT 2
        """,
        code,
    )
    if rows:
        bar = rows[0]
        prev_price = rows[1]["price"] if len(rows) > 1 else None
        price_val  = bar["price"]
        change_val = round(price_val - prev_price) if prev_price else None
        rate_val   = bar["change_rate"]
        if not rate_val and change_val and prev_price:
            rate_val = round(change_val / prev_price * 100, 2)
        return {
            "code":        code,
            "price":       price_val,
            "prev_close":  prev_price,
            "change":      change_val,
            "change_rate": rate_val,
            "open":        bar["open"],
            "high":        bar["high"],
            "low":         bar["low"],
            "volume":      bar["volume"],
            "amount":      bar["amount"],
            "source":      "daily",
        }

    return {
        "code": code, "price": None, "prev_close": None,
        "change": None, "change_rate": None,
        "open": None, "high": None, "low": None,
        "volume": None, "amount": None, "source": "none",
    }

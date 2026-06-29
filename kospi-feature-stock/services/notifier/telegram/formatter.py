from datetime import datetime, timezone, timedelta

_KST = timezone(timedelta(hours=9))


def _fmt_price(price) -> str:
    try:
        return f"{int(price):,}"
    except (TypeError, ValueError):
        return str(price)


def _fmt_pct(a, b) -> str:
    try:
        pct = (float(b) - float(a)) / float(a) * 100
        sign = "+" if pct >= 0 else ""
        return f"{sign}{pct:.1f}%"
    except Exception:
        return "N/A"


def _fmt_dt(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_KST).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso[:16] if iso else ""


def format_buy_signal(msg: dict) -> str:
    code        = msg.get("code", "")
    name        = msg.get("name", "") or code
    entry       = msg.get("entry_price", 0)
    target      = msg.get("target_price", 0)
    stop        = msg.get("stop_loss_price", 0)
    prob        = msg.get("success_prob", 0)
    risk        = msg.get("risk_score", 0)
    created_at  = _fmt_dt(msg.get("created_at", ""))

    # rationale JSON에서 rec_score 추출 (없으면 success_prob 기반 표시)
    rationale   = msg.get("rationale") or {}
    rec_score   = rationale.get("rec_score") if isinstance(rationale, dict) else None

    upside   = _fmt_pct(entry, target)
    downside = _fmt_pct(entry, stop)

    name_line = f"&#128204; 종목: <b>{name}</b>  (<code>{code}</code>)\n" if name != code else f"&#128204; 종목: <b>{code}</b>\n"

    if rec_score is not None:
        score_line = f"&#127919; 추천점수: <b>{int(rec_score)}점</b>  (<code>성공확률 {prob * 100:.0f}%</code>)\n"
    else:
        score_line = f"&#127919; 성공확률: <b>{prob * 100:.0f}%</b>\n"

    return (
        f"<b>&#128640; 매수 추천 알림</b>\n"
        f"\n"
        f"{name_line}"
        f"{score_line}"
        f"\n"
        f"&#128176; 매수가(진입): <b>{_fmt_price(entry)}원</b>\n"
        f"&#127937; 목표가(매도): <b>{_fmt_price(target)}원</b>  (<code>{upside}</code>)\n"
        f"&#128721; 손절가: <b>{_fmt_price(stop)}원</b>  (<code>{downside}</code>)\n"
        f"&#9888;&#65039; 리스크: <b>{risk * 100:.0f}%</b>\n"
        f"\n"
        f"&#128336; {created_at}"
    )


def format_price_alert(msg: dict) -> str:
    """익절가 도달 / 손절가 접근 / 손절가 도달 알림."""
    alert_type  = msg.get("alert_type", "")   # "target_hit" | "stop_approach" | "stop_hit"
    code        = msg.get("code", "")
    name        = msg.get("name", "") or code
    current     = msg.get("current_price", 0)
    entry       = msg.get("entry_price", 0)
    target      = msg.get("target_price", 0)
    stop        = msg.get("stop_loss_price", 0)
    hold_days   = msg.get("hold_days", 0)
    now_str     = datetime.now(_KST).strftime("%m/%d %H:%M")

    pnl_pct = ""
    if entry and current:
        pct  = (float(current) - float(entry)) / float(entry) * 100
        sign = "+" if pct >= 0 else ""
        pnl_pct = f"{sign}{pct:.1f}%"

    if alert_type == "target_hit":
        icon   = "🎯"
        title  = "익절가 도달"
        detail = (
            f"&#127937; 목표가: <b>{_fmt_price(target)}원</b>\n"
            f"&#128200; 현재가: <b>{_fmt_price(current)}원</b>  (<code>{pnl_pct}</code>)\n"
            f"&#9989; <b>익절 검토 권장</b>"
        )
    elif alert_type == "stop_approach":
        icon   = "⚠️"
        title  = "손절가 접근 경고"
        remain_pct = ""
        if stop and current:
            r = (float(stop) - float(current)) / float(current) * 100
            remain_pct = f"  손절까지 <code>-{abs(r):.1f}%</code>"
        detail = (
            f"&#128721; 손절가: <b>{_fmt_price(stop)}원</b>{remain_pct}\n"
            f"&#128200; 현재가: <b>{_fmt_price(current)}원</b>  (<code>{pnl_pct}</code>)\n"
            f"&#9888;&#65039; <b>리스크 관리 점검 필요</b>"
        )
    elif alert_type == "stop_hit":
        icon   = "🛑"
        title  = "손절가 도달"
        detail = (
            f"&#128721; 손절가: <b>{_fmt_price(stop)}원</b>\n"
            f"&#128200; 현재가: <b>{_fmt_price(current)}원</b>  (<code>{pnl_pct}</code>)\n"
            f"&#128679; <b>손절 실행 강력 권장</b>"
        )
    elif alert_type == "trail_stop_hit":
        trail_stop = msg.get("trail_stop_price", stop)
        icon   = "📉"
        title  = "트레일링 스탑 도달"
        detail = (
            f"&#128200; 현재가: <b>{_fmt_price(current)}원</b>  (<code>{pnl_pct}</code>)\n"
            f"&#128038; 트레일링 스탑: <b>{_fmt_price(trail_stop)}원</b>\n"
            f"&#9989; <b>이익 보전 매도 권장</b>"
        )
    else:
        icon   = "📌"
        title  = "가격 알림"
        detail = f"&#128200; 현재가: <b>{_fmt_price(current)}원</b>  (<code>{pnl_pct}</code>)"

    name_line = (
        f"&#128204; 종목: <b>{name}</b>  (<code>{code}</code>)\n"
        if name != code else
        f"&#128204; 종목: <b>{code}</b>\n"
    )
    hold_line = f"&#128336; 보유 <b>{hold_days}일</b>차 · {now_str}" if hold_days else f"&#128336; {now_str}"

    return (
        f"<b>{icon} {title}</b>\n"
        f"\n"
        f"{name_line}"
        f"&#128176; 진입가: <b>{_fmt_price(entry)}원</b>\n"
        f"\n"
        f"{detail}\n"
        f"\n"
        f"{hold_line}"
    )


_CAT_KO = {"favorable": "호재", "unfavorable": "악재", "neutral": "중립"}


def format_disclosure(msg: dict) -> str:
    corp_name       = msg.get("corp_name", "")
    code            = msg.get("code", "")
    title           = msg.get("title", "")
    category        = msg.get("category", "")
    sentiment_score = msg.get("sentiment_score", 0.0)
    disclosed_at    = _fmt_dt(msg.get("disclosed_at", ""))
    keywords        = msg.get("keywords", [])
    sent_at         = datetime.now(_KST).strftime("%m/%d %H:%M")

    cat_ko          = _CAT_KO.get(category, category)
    sentiment_label = "&#128994;" if sentiment_score >= 0.3 else ("&#128308;" if sentiment_score <= -0.3 else "&#128992;")
    score_str       = f"  <code>{sentiment_score:+.2f}</code>" if abs(sentiment_score) >= 0.05 else ""
    kw_text         = "  ".join(f"#{k}" for k in keywords[:5]) if keywords else ""

    return (
        f"<b>&#128226; 공시 알림</b>\n"
        f"\n"
        f"&#127970; 법인: <b>{corp_name}</b>  (<code>{code}</code>)\n"
        f"&#128203; 제목: {title}\n"
        f"&#128202; 분류: {cat_ko}  {sentiment_label}{score_str}\n"
        f"{('&#128273; ' + kw_text + chr(10)) if kw_text else ''}"
        f"\n"
        f"&#128336; 공시일시: {disclosed_at}\n"
        f"&#128228; 발송: {sent_at}"
    )
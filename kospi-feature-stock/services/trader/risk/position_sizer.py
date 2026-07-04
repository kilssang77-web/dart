"""
포지션 사이징 알고리즘
- Kelly Criterion (Quarter-Kelly)
- Fixed-Fraction (자본 대비 고정 %)
- Fixed-Ratio
"""
import logging
import math

logger = logging.getLogger(__name__)

# 최소 주문 금액 (원) — KRX 규정: 최소 1주, 실질적으로 10,000원 이상 권장
_MIN_ORDER_KRW = 10_000


def calc_qty(
    price: int,
    available_cash: int,
    max_invest_per_trade: int,
    sizing_method: str,        # kelly | fixed_fraction | fixed_ratio
    # Kelly / 통계 파라미터
    success_prob: float = 0.5,
    avg_win_pct: float  = 0.08,  # 평균 목표수익률 (소수)
    avg_loss_pct: float = 0.05,  # 평균 손절폭 (소수, 양수)
    kelly_fraction: float = 0.25,
    # Fixed-fraction
    total_capital: int = 0,
    fixed_fraction_pct: float = 10.0,
    **kwargs,
) -> int:
    """
    Returns
    -------
    qty : int  (0이면 투자 불가)
    """
    if price <= 0:
        return 0

    invest = _calc_invest_amount(
        pricing_method=sizing_method,
        price=price,
        available_cash=available_cash,
        max_invest_per_trade=max_invest_per_trade,
        success_prob=success_prob,
        avg_win_pct=avg_win_pct,
        avg_loss_pct=avg_loss_pct,
        kelly_fraction=kelly_fraction,
        total_capital=total_capital,
        fixed_fraction_pct=fixed_fraction_pct,
    )

    if invest < _MIN_ORDER_KRW:
        logger.debug(f"투자금액 미달 ({invest:,}원 < {_MIN_ORDER_KRW:,}원)")
        return 0

    qty = invest // price
    return max(0, qty)


def _calc_invest_amount(
    pricing_method: str,
    price: int,
    available_cash: int,
    max_invest_per_trade: int,
    success_prob: float,
    avg_win_pct: float,
    avg_loss_pct: float,
    kelly_fraction: float,
    total_capital: int,
    fixed_fraction_pct: float,
    **_,
) -> int:
    method = pricing_method.lower()

    if method == "kelly":
        invest = _kelly(
            success_prob, avg_win_pct, avg_loss_pct,
            kelly_fraction, total_capital or available_cash,
        )
    elif method == "fixed_fraction":
        capital = total_capital or available_cash
        invest = int(capital * fixed_fraction_pct / 100.0)
    else:
        # fixed_ratio (기본): max_invest_per_trade 사용
        invest = max_invest_per_trade

    # 최소/최대 제약
    invest = min(invest, max_invest_per_trade)
    invest = min(invest, available_cash)
    invest = max(invest, 0)
    return invest


def _kelly(
    p: float,
    win_pct: float,
    loss_pct: float,
    fraction: float,
    capital: int,
) -> int:
    """
    Kelly Criterion: f* = (p*b - q) / b
    b = 승리 시 수익배수 (win_pct / loss_pct)
    fraction: Quarter-Kelly 등 보수적 비율 적용
    """
    q = 1.0 - p
    b = win_pct / max(loss_pct, 0.001)
    f_star = (p * b - q) / max(b, 0.001)
    f_star = max(0.0, min(1.0, f_star))   # 0~100% 클리핑
    invest = int(capital * f_star * fraction)
    logger.debug(
        f"Kelly: p={p:.2f}, b={b:.2f}, f*={f_star:.3f}, fraction={fraction}, invest={invest:,}원"
    )
    return invest


def describe(
    price: int,
    qty: int,
    success_prob: float,
    method: str,
    max_invest: int,
) -> dict:
    """포지션 사이징 결과 요약 (로그/UI용)."""
    invest = price * qty
    return {
        "method": method,
        "price": price,
        "qty": qty,
        "invest_amount": invest,
        "success_prob": success_prob,
        "max_invest_per_trade": max_invest,
        "invest_ratio_pct": round(invest / max_invest * 100, 1) if max_invest else 0,
    }

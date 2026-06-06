"""
기술 지표(change_rate, RSI14, MACD, 볼린저밴드20, ATR14) 일괄 계산 및 업데이트.
ml container에서 실행 (pandas/numpy 사용).

사용:
  # 전체 종목
  docker compose run --rm ml python /app/scripts/backfill_technical_indicators.py

  # 특정 종목
  docker compose run --rm ml python /app/scripts/backfill_technical_indicators.py --code 005930
"""
import asyncio
import asyncpg
import logging
import os
import sys
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill")


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d     = close.diff()
    gain  = d.clip(lower=0)
    loss  = (-d).clip(lower=0)
    avg_g = gain.ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    avg_l = loss.ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    return 100 - 100 / (1 + avg_g / avg_l.replace(0, np.nan))


def _macd(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    line  = ema12 - ema26
    sig   = line.ewm(span=9, adjust=False).mean()
    return line, sig


def _bb(close: pd.Series, n: int = 20, k: float = 2.0) -> tuple[pd.Series, pd.Series]:
    m = close.rolling(n).mean()
    s = close.rolling(n).std(ddof=0)
    return m + k * s, m - k * s


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    pc = close.shift(1)
    tr = pd.concat(
        [(high - low).abs(), (high - pc).abs(), (low - pc).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / n, min_periods=n, adjust=False).mean()


def _f(v) -> float | None:
    return None if pd.isna(v) else round(float(v), 4)


async def process_code(conn: asyncpg.Connection, code: str) -> int:
    rows = await conn.fetch(
        "SELECT date, high, low, close FROM daily_bars WHERE code=$1 ORDER BY date",
        code,
    )
    if len(rows) < 2:
        return 0

    df = pd.DataFrame([dict(r) for r in rows])
    for col in ("high", "low", "close"):
        df[col] = df[col].astype(float)

    prev_close          = df["close"].shift(1)
    df["change_rate"]   = ((df["close"] - prev_close) / prev_close * 100).round(2)
    df["ma5"]           = df["close"].rolling(5).mean()
    df["ma20"]          = df["close"].rolling(20).mean()
    df["ma60"]          = df["close"].rolling(60).mean()
    df["ma120"]         = df["close"].rolling(120).mean()
    df["rsi14"]         = _rsi(df["close"])
    df["macd_l"], df["macd_s"] = _macd(df["close"])
    df["bb_u"],   df["bb_l"]   = _bb(df["close"])
    df["atr14"]         = _atr(df["high"], df["low"], df["close"])

    updates = [
        (
            _f(row["change_rate"]),
            _f(row["ma5"]),
            _f(row["ma20"]),
            _f(row["ma60"]),
            _f(row["ma120"]),
            _f(row["rsi14"]),
            _f(row["macd_l"]),
            _f(row["macd_s"]),
            _f(row["bb_u"]),
            _f(row["bb_l"]),
            _f(row["atr14"]),
            code,
            row["date"],
        )
        for _, row in df.iterrows()
    ]

    await conn.executemany(
        """
        UPDATE daily_bars
        SET change_rate = $1::NUMERIC,
            ma5         = ROUND($2::NUMERIC,  2),
            ma20        = ROUND($3::NUMERIC,  2),
            ma60        = ROUND($4::NUMERIC,  2),
            ma120       = ROUND($5::NUMERIC,  2),
            rsi14       = ROUND($6::NUMERIC,  2),
            macd        = ROUND($7::NUMERIC,  4),
            macd_signal = ROUND($8::NUMERIC,  4),
            bb_upper    = ROUND($9::NUMERIC,  2),
            bb_lower    = ROUND($10::NUMERIC, 2),
            atr14       = ROUND($11::NUMERIC, 2)
        WHERE code=$12 AND date=$13
        """,
        updates,
    )
    return len(updates)


async def main() -> None:
    dsn       = os.environ["POSTGRES_DSN"].replace("+asyncpg", "")
    only_code = next(
        (sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--code"), None
    )

    db = await asyncpg.create_pool(dsn=dsn, min_size=2, max_size=5)
    if only_code:
        codes = [only_code.upper()]
    else:
        codes = [
            r["code"]
            for r in await db.fetch(
                "SELECT DISTINCT code FROM daily_bars ORDER BY code"
            )
        ]
    logger.info(f"처리 대상: {len(codes)}개 종목")

    total, done = 0, 0
    async with db.acquire() as conn:
        for code in codes:
            n     = await process_code(conn, code)
            total += n
            done  += 1
            if done % 100 == 0:
                logger.info(f"진행: {done}/{len(codes)} ({total:,}행 업데이트)")

    await db.close()
    logger.info(f"완료 | {done}종목 | {total:,}행 업데이트")


if __name__ == "__main__":
    asyncio.run(main())

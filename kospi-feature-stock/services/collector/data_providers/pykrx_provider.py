import asyncio
import logging
from datetime import datetime, timedelta

from .base import DataProvider

logger = logging.getLogger(__name__)


class PyKRXProvider(DataProvider):
    """pykrx 기반 DataProvider — KIS 크리덴셜 없을 때 fallback으로 사용.

    pykrx는 동기 라이브러리이므로 모든 호출은 run_in_executor를 통해 비동기화한다.
    실시간 데이터는 제공하지 않으며, 일봉·종목 리스트·지수·수급 데이터만 지원한다.
    """

    @property
    def is_realtime(self) -> bool:
        return False

    @property
    def name(self) -> str:
        return "pykrx"

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    @staticmethod
    def _today_str() -> str:
        return datetime.now().strftime("%Y%m%d")

    @staticmethod
    def _date_before(days: int) -> str:
        return (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

    async def _run(self, func):
        """동기 callable을 기본 executor에서 실행하여 코루틴으로 반환한다."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func)

    # ------------------------------------------------------------------
    # 공개 메서드
    # ------------------------------------------------------------------

    async def get_daily_bars(self, code: str, days: int) -> list[dict]:
        """종목 코드의 최근 days일 일봉 데이터를 반환한다.

        반환 dict 키: code, date, open, high, low, close, volume, amount, change_rate
        write_daily_bars와 동일한 포맷 — KIS 결과와 호환.
        """
        try:
            from pykrx import stock as krx

            start = self._date_before(days + 10)  # 휴장일 감안해 여유를 둔다
            end = self._today_str()

            def _fetch():
                return krx.get_market_ohlcv_by_date(start, end, code)

            df = await self._run(_fetch)

            if df is None or df.empty:
                logger.warning("pykrx: %s 일봉 데이터 없음 (%s ~ %s)", code, start, end)
                return []

            bars: list[dict] = []
            for idx, row in df.tail(days).iterrows():
                try:
                    change_rate = float(row.get("등락률", row.get("Change", 0.0)) or 0.0)
                    close = int(row.get("종가", row.get("Close", 0)))
                    volume = int(row.get("거래량", row.get("Volume", 0)))
                    # 거래대금(원) — pykrx가 제공하면 사용, 없으면 close×volume 추정
                    raw_amt = row.get("거래대금", row.get("Amount", None))
                    if raw_amt is not None:
                        try:
                            amount = int(raw_amt)
                        except (TypeError, ValueError):
                            amount = close * volume
                    else:
                        amount = close * volume
                    bars.append(
                        {
                            "code": code,
                            "date": idx.strftime("%Y-%m-%d"),
                            "open": int(row.get("시가", row.get("Open", 0))),
                            "high": int(row.get("고가", row.get("High", 0))),
                            "low": int(row.get("저가", row.get("Low", 0))),
                            "close": close,
                            "volume": volume,
                            "amount": amount,
                            "change_rate": round(change_rate, 2),
                        }
                    )
                except Exception as row_err:
                    logger.debug("pykrx: %s 행 변환 오류 — %s", code, row_err)
                    continue

            return bars

        except Exception as exc:
            logger.error("pykrx.get_daily_bars(%s, %d) 오류: %s", code, days, exc)
            return []

    async def get_stock_list(self) -> list[dict]:
        """KOSPI·KOSDAQ 전체 종목 리스트를 반환한다.

        반환 dict 키: code, name, market
        """
        try:
            from pykrx import stock as krx

            today = self._today_str()

            def _fetch_kospi():
                tickers = krx.get_market_ticker_list(today, market="KOSPI")
                return [
                    {
                        "code": t,
                        "name": krx.get_market_ticker_name(t),
                        "market": "KOSPI",
                    }
                    for t in tickers
                ]

            def _fetch_kosdaq():
                tickers = krx.get_market_ticker_list(today, market="KOSDAQ")
                return [
                    {
                        "code": t,
                        "name": krx.get_market_ticker_name(t),
                        "market": "KOSDAQ",
                    }
                    for t in tickers
                ]

            kospi, kosdaq = await asyncio.gather(
                self._run(_fetch_kospi),
                self._run(_fetch_kosdaq),
            )

            result = kospi + kosdaq
            logger.info("pykrx: 종목 리스트 %d개 조회 완료", len(result))
            return result

        except Exception as exc:
            logger.error("pykrx.get_stock_list() 오류: %s", exc)
            return []

    async def get_market_index(self) -> dict:
        """KOSPI·KOSDAQ 당일 지수를 반환한다.

        반환 dict 키: kospi_close, kospi_change_rate, kosdaq_close, kosdaq_change_rate
        """
        try:
            from pykrx import stock as krx

            today = self._today_str()
            start = self._date_before(5)  # 최근 영업일을 찾기 위해 여유를 둔다

            def _fetch_kospi():
                return krx.get_index_ohlcv_by_date(start, today, "1001")

            def _fetch_kosdaq():
                return krx.get_index_ohlcv_by_date(start, today, "2001")

            kospi_df, kosdaq_df = await asyncio.gather(
                self._run(_fetch_kospi),
                self._run(_fetch_kosdaq),
            )

            def _last_row(df):
                if df is None or df.empty:
                    return {}
                row = df.iloc[-1]
                close = float(row.get("종가", row.get("Close", 0.0)) or 0.0)
                change_rate = float(
                    row.get("등락률", row.get("Change", 0.0)) or 0.0
                )
                return {"close": round(close, 2), "change_rate": round(change_rate, 2)}

            kospi = _last_row(kospi_df)
            kosdaq = _last_row(kosdaq_df)

            return {
                "kospi_close": kospi.get("close", 0.0),
                "kospi_change_rate": kospi.get("change_rate", 0.0),
                "kosdaq_close": kosdaq.get("close", 0.0),
                "kosdaq_change_rate": kosdaq.get("change_rate", 0.0),
            }

        except Exception as exc:
            logger.error("pykrx.get_market_index() 오류: %s", exc)
            return {}

    async def get_supply_demand(self, code: str, date: str) -> dict | None:
        """특정 종목·날짜의 투자자별 순매수 데이터를 반환한다.

        date 형식: "YYYY-MM-DD" (내부에서 "YYYYMMDD"로 변환)

        반환 dict 키: date, individual, foreign, institution, etc_finance
        """
        try:
            from pykrx import stock as krx

            date_fmt = date.replace("-", "")

            def _fetch():
                return krx.get_market_net_purchases_of_investors(
                    date_fmt, date_fmt, code
                )

            df = await self._run(_fetch)

            if df is None or df.empty:
                logger.debug("pykrx: %s (%s) 수급 데이터 없음", code, date)
                return None

            row = df.iloc[-1] if len(df) > 0 else None
            if row is None:
                return None

            def _int(val):
                try:
                    return int(val)
                except (TypeError, ValueError):
                    return 0

            return {
                "date": date,
                "individual": _int(row.get("개인", row.get("Individual", 0))),
                "foreign": _int(row.get("외국인", row.get("Foreigner", 0))),
                "institution": _int(row.get("기관합계", row.get("Institution", 0))),
                "etc_finance": _int(row.get("금융투자", row.get("FinanceEtc", 0))),
            }

        except Exception as exc:
            logger.error("pykrx.get_supply_demand(%s, %s) 오류: %s", code, date, exc)
            return None

import asyncio
import logging
import httpx
from datetime import date, datetime
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from .auth import KISAuthManager, KISConfig

logger = logging.getLogger(__name__)


class KISAPIError(Exception):
    """KIS API가 rt_cd != '0' 로 응답한 경우 — 재시도 불필요."""


class KISRestClient:

    def __init__(self, config: KISConfig, auth: KISAuthManager):
        self.config = config
        self.auth = auth
        self._client = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=30,
            limits=httpx.Limits(max_connections=30, max_keepalive_connections=20),
        )
        self._sem = asyncio.Semaphore(15)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException, httpx.HTTPStatusError)),
    )
    async def _get(self, path: str, tr_id: str, params: dict) -> dict:
        async with self._sem:
            token = await self.auth.get_access_token()
            resp = await self._client.get(
                path,
                headers=self.auth.get_headers(token, tr_id),
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("rt_cd") != "0":
                raise KISAPIError(f"[{tr_id}] {data.get('msg1', '')}")
            return data

    async def get_minute_bars(self, code: str) -> list[dict]:
        data = await self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
            "FHKST03010200",
            {
                "FID_ETC_CLS_CODE": "",
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": code,
                "FID_INPUT_HOUR_1": "090000",
                "FID_PW_DATA_INCU_YN": "Y",
            },
        )
        return [
            {
                "code":   code,
                "time":   r.get("stck_bsop_date", "") + r.get("stck_cntg_hour", ""),
                "open":   int(r.get("stck_oprc", 0) or 0),
                "high":   int(r.get("stck_hgpr", 0) or 0),
                "low":    int(r.get("stck_lwpr", 0) or 0),
                "close":  int(r.get("stck_prpr", 0) or 0),
                "volume": int(r.get("cntg_vol", 0) or 0),
                "amount": int(r.get("acml_tr_pbmn", 0) or 0),
            }
            for r in data.get("output2", [])
            if r.get("stck_prpr")
        ]

    async def get_daily_bars(self, code: str, start: str, end: str) -> list[dict]:
        try:
            data = await self._get(
                "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
                "FHKST03010100",
                {
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_INPUT_ISCD": code,
                    "FID_INPUT_DATE_1": start,
                    "FID_INPUT_DATE_2": end,
                    "FID_PERIOD_DIV_CODE": "D",
                    "FID_ORG_ADJ_PRC": "0",
                },
            )
        except KISAPIError as e:
            logger.debug(f"get_daily_bars [{code}] unsupported: {e}")
            return []
        return [
            {
                "code":        code,
                "date":        r.get("stck_bsop_date"),
                "open":        int(r.get("stck_oprc", 0) or 0),
                "high":        int(r.get("stck_hgpr", 0) or 0),
                "low":         int(r.get("stck_lwpr", 0) or 0),
                "close":       int(r.get("stck_clpr", 0) or 0),
                "volume":      int(r.get("acml_vol", 0) or 0),
                "amount":      int(r.get("acml_tr_pbmn", 0) or 0),
                "change_rate": float(r.get("prdy_ctrt", 0) or 0),
            }
            for r in data.get("output2", [])
            if r.get("stck_clpr")
        ]

    async def get_supply_demand(self, code: str, date_str: str) -> dict:
        data = await self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-investor",
            "FHKST01010900",
            {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": code,
                "FID_INPUT_DATE_1": date_str,
                "FID_INPUT_DATE_2": date_str,
                "FID_PERIOD_DIV_CODE": "D",
            },
        )
        rows = data.get("output", [])
        if not rows:
            return {}
        r = rows[0]
        return {
            "code":                 code,
            "date":                 date_str,
            "foreign_net":          int(r.get("frgn_ntby_qty", 0) or 0),
            "inst_net":             int(r.get("orgn_ntby_qty", 0) or 0),
            "indiv_net":            int(r.get("indv_ntby_qty", 0) or 0),
            "prog_arbitrage_net":   int(r.get("pgtr_ntby_qty", 0) or 0),
            "pension_net":          int(r.get("cnfn_ntby_qty", 0) or 0),
        }

    async def get_stock_list(self, market: str = "J") -> list[dict]:
        """전체 종목 리스트 조회 (J=KOSPI, Q=KOSDAQ)"""
        data = await self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
            "FHKST03010100",
            {"FID_COND_MRKT_DIV_CODE": market},
        )
        return data.get("output", [])

    async def get_index_bars(self, market_code: str, start: str, end: str) -> list[dict]:
        """
        KOSPI/KOSDAQ 지수 일봉 조회.
        market_code: "0001" (KOSPI) / "1001" (KOSDAQ)
        start/end: "YYYYMMDD"
        """
        try:
            data = await self._get(
                "/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice",
                "FHKUP03500100",
                {
                    "FID_COND_MRKT_DIV_CODE": "U",
                    "FID_INPUT_ISCD": market_code,
                    "FID_INPUT_DATE_1": start,
                    "FID_INPUT_DATE_2": end,
                    "FID_PERIOD_DIV_CODE": "D",
                },
            )
        except KISAPIError as e:
            logger.debug(f"get_index_bars [{market_code}]: {e}")
            return []
        return [
            {
                "code":        market_code,
                "date":        r.get("stck_bsop_date"),
                "open":        int(float(r.get("bstp_nmix_oprc", 0) or 0)),
                "high":        int(float(r.get("bstp_nmix_hgpr", 0) or 0)),
                "low":         int(float(r.get("bstp_nmix_lwpr", 0) or 0)),
                "close":       int(float(r.get("bstp_nmix_prpr", 0) or 0)),
                "volume":      int(r.get("acml_vol", 0) or 0),
                "amount":      int(r.get("acml_tr_pbmn", 0) or 0) if r.get("acml_tr_pbmn") else 0,
                "change_rate": float(r.get("bstp_nmix_prdy_ctrt", 0) or 0),
            }
            for r in data.get("output2", [])
            if r.get("stck_bsop_date") and r.get("bstp_nmix_prpr")
        ]

    async def get_short_sell(self, code: str, start: str, end: str) -> list[dict]:
        data = await self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-daily-shortsale",
            "FHPST01810000",
            {"FID_INPUT_ISCD": code, "FID_INPUT_DATE_1": start, "FID_INPUT_DATE_2": end},
        )
        return [
            {
                "code":          code,
                "date":          r.get("stck_bsop_date"),
                "short_vol":     int(r.get("shnu_vol", 0) or 0),
                "short_amt":     int(r.get("shnu_tr_pbmn", 0) or 0),
                "short_balance": int(r.get("stln_rmnd_qty", 0) or 0),
            }
            for r in data.get("output", [])
        ]

    async def get_current_price(self, code: str, exchange: str = "KRX") -> dict:
        """주식현재가 시세 (FHKST01010100) — 단건, 당일 OHLCV 누적 포함.
        minute-bar 폴링보다 경량. 전 종목 인트라데이 스캔용.
        exchange: "KRX" → FID_COND_MRKT_DIV_CODE=J, "NXT" → NX
        """
        mrkt_code = "NX" if exchange == "NXT" else "J"
        try:
            data = await self._get(
                "/uapi/domestic-stock/v1/quotations/inquire-price",
                "FHKST01010100",
                {"FID_COND_MRKT_DIV_CODE": mrkt_code, "FID_INPUT_ISCD": code},
            )
            o = data.get("output", {})
            if not o:
                return {}
            price = int(o.get("stck_prpr", 0) or 0)
            if price == 0:
                return {}
            return {
                "code":        code,
                "time":        datetime.now().strftime("%H%M%S"),
                "price":       price,
                "close":       price,
                "prev_close":  int(o.get("stck_sdpr", 0) or 0),
                "change":      int(o.get("prdy_vrss", 0) or 0),
                "change_rate": float(o.get("prdy_ctrt", 0) or 0),
                "open":        int(o.get("stck_oprc", 0) or 0),
                "high":        int(o.get("stck_hgpr", 0) or 0),
                "low":         int(o.get("stck_lwpr", 0) or 0),
                "volume":      int(o.get("acml_vol", 0) or 0),
                "amount":      int(o.get("acml_tr_pbmn", 0) or 0),
            }
        except KISAPIError:
            return {}
        except Exception:
            return {}

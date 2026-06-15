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

    async def get_financial_ratio(self, code: str) -> list[dict]:
        """분기별 재무비율 (FHKST66430300) — EPS/BPS/PER/PBR/ROE/부채비율."""
        try:
            data = await self._get(
                "/uapi/domestic-stock/v1/finance/financial-ratio",
                "FHKST66430300",
                {
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_INPUT_ISCD": code,
                    "FID_DIV_CLS_CODE": "0",  # 0: 분기, 1: 연간
                },
            )
        except KISAPIError as e:
            logger.debug(f"get_financial_ratio [{code}]: {e}")
            return []

        results = []
        for r in data.get("output", []):
            stac_yymm = r.get("stac_yymm", "")
            if not stac_yymm or len(stac_yymm) < 6:
                continue
            year    = int(stac_yymm[:4])
            month   = int(stac_yymm[4:6])
            quarter = (month - 1) // 3 + 1

            def _fi(key):
                v = r.get(key)
                try:
                    return int(float(v)) if v not in (None, "", "-") else None
                except (ValueError, TypeError):
                    return None

            def _ff(key):
                v = r.get(key)
                try:
                    return round(float(v), 2) if v not in (None, "", "-") else None
                except (ValueError, TypeError):
                    return None

            results.append({
                "code": code, "year": year, "quarter": quarter,
                "eps":        _fi("eps"),
                "bps":        _fi("bps"),
                "per":        _ff("per"),
                "pbr":        _ff("pbr"),
                "roe":        _ff("roe"),
                "debt_ratio": _ff("lblt_rate"),
            })
        return results

    async def get_income_statement(self, code: str) -> list[dict]:
        """분기별 손익계산서 (FHKST66430200) — 매출/영업이익/순이익."""
        try:
            data = await self._get(
                "/uapi/domestic-stock/v1/finance/income-statement",
                "FHKST66430200",
                {
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_INPUT_ISCD": code,
                    "FID_DIV_CLS_CODE": "0",
                },
            )
        except KISAPIError as e:
            logger.debug(f"get_income_statement [{code}]: {e}")
            return []

        results = []
        for r in data.get("output", []):
            stac_yymm = r.get("stac_yymm", "")
            if not stac_yymm or len(stac_yymm) < 6:
                continue
            year    = int(stac_yymm[:4])
            month   = int(stac_yymm[4:6])
            quarter = (month - 1) // 3 + 1

            def _bi(key):
                v = r.get(key)
                try:
                    return int(float(v) * 1_000_000) if v not in (None, "", "-") else None
                except (ValueError, TypeError):
                    return None

            results.append({
                "code": code, "year": year, "quarter": quarter,
                "revenue":          _bi("sale_account"),
                "operating_profit": _bi("bsop_prti"),
                "net_profit":       _bi("thtr_ntin"),
            })
        return results

    async def get_orderbook(self, code: str) -> dict:
        """주식 호가 잔량 (FHKST01010200) — 매도/매수 각 10단계."""
        try:
            data = await self._get(
                "/uapi/domestic-stock/v1/quotations/inquire-asking-price-exp-ccn",
                "FHKST01010200",
                {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code},
            )
            o = data.get("output1", {})
            if not o:
                return {}
            asks, bids = [], []
            for i in range(1, 11):
                ap = int(o.get(f"askp{i}", 0) or 0)
                aq = int(o.get(f"askp_rsqn{i}", 0) or 0)
                bp = int(o.get(f"bidp{i}", 0) or 0)
                bq = int(o.get(f"bidp_rsqn{i}", 0) or 0)
                if ap:
                    asks.append({"price": ap, "qty": aq})
                if bp:
                    bids.append({"price": bp, "qty": bq})
            return {
                "code":         code,
                "asks":         asks,           # 매도 (낮은가→높은가)
                "bids":         bids,           # 매수 (높은가→낮은가)
                "total_ask_qty": int(o.get("total_askp_rsqn", 0) or 0),
                "total_bid_qty": int(o.get("total_bidp_rsqn", 0) or 0),
                "ts":           datetime.now().isoformat(),
            }
        except Exception:
            return {}

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

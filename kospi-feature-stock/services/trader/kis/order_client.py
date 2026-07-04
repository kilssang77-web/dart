"""
KIS 주문 API 클라이언트
- 실전: TTTC0802U(매수) / TTTC0801U(매도) / TTTC0803U(취소) / TTTC8434R(잔고) / TTTC8001R(주문조회)
- 모의: VTTC0802U / VTTC0801U / VTTC0803U / VTTC8434R / VTTC8001R
"""
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

import httpx
import redis.asyncio as redis_lib
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

_KIS_BASE_URL = os.getenv("KIS_BASE_URL", "https://openapi.koreainvestment.com:9443")


@dataclass
class KISConfig:
    app_key: str
    app_secret: str
    account_no: str          # 계좌번호 전체 (예: 50123456-01 또는 5012345601)
    account_type: str = "01"
    base_url: str = field(default_factory=lambda: _KIS_BASE_URL)
    is_paper: bool = True    # True=모의투자, False=실전


@dataclass
class OrderResult:
    success: bool
    order_no: str = ""          # ODNO — KIS 주문번호
    error_msg: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class BalanceResult:
    success: bool
    deposit: int = 0            # 주문가능현금 (원)
    total_eval: int = 0         # 총평가금액 (원)
    total_buy: int = 0          # 총매입금액 (원)
    holdings: list = field(default_factory=list)   # [{code, name, qty, avg_price, current_price, eval_pnl_pct}]
    error_msg: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class OpenOrder:
    order_no: str
    code: str
    name: str
    side: str               # BUY | SELL
    order_price: int
    order_qty: int
    filled_qty: int
    status: str             # PENDING | PARTIAL


class KISAuthManager:
    TOKEN_KEY = "kis:access_token"

    def __init__(self, config: KISConfig, redis_client: redis_lib.Redis):
        self.config = config
        self.redis = redis_client
        self._client = httpx.AsyncClient(timeout=30)

    async def get_access_token(self) -> str:
        cached = await self.redis.get(self.TOKEN_KEY)
        if cached:
            return cached.decode()
        data = await self._issue_token()
        ttl = data.get("expires_in", 86400) - 1800
        await self.redis.setex(self.TOKEN_KEY, max(ttl, 300), data["access_token"])
        return data["access_token"]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    )
    async def _issue_token(self) -> dict:
        resp = await self._client.post(
            f"{self.config.base_url}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": self.config.app_key,
                "appsecret": self.config.app_secret,
            },
        )
        resp.raise_for_status()
        return resp.json()

    def get_headers(self, token: str, tr_id: str, hash_key: str = "") -> dict:
        h = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self.config.app_key,
            "appsecret": self.config.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }
        if hash_key:
            h["hashkey"] = hash_key
        return h


class KISOrderClient:

    def __init__(self, config: KISConfig, auth: KISAuthManager):
        self.config = config
        self.auth = auth
        self._client = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=30,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
        self._paper = config.is_paper

    # ── TR_ID 선택 헬퍼 ──────────────────────────────────────────────────────
    def _tr(self, real_id: str, paper_id: str) -> str:
        return paper_id if self._paper else real_id

    def _acct(self) -> tuple[str, str]:
        """계좌번호를 앞8자리 / 뒤2자리로 분리."""
        no = self.config.account_no.replace("-", "")
        return no[:8], no[8:] if len(no) > 8 else self.config.account_type

    # ── HASHKEY 발급 (POST 요청에 필요) ─────────────────────────────────────
    async def _get_hashkey(self, body: dict) -> str:
        try:
            token = await self.auth.get_access_token()
            resp = await self._client.post(
                "/uapi/hashkey",
                headers={
                    "Content-Type": "application/json",
                    "appkey": self.config.app_key,
                    "appsecret": self.config.app_secret,
                },
                json=body,
            )
            resp.raise_for_status()
            return resp.json().get("HASH", "")
        except Exception as e:
            logger.warning(f"hashkey 발급 실패 (무시): {e}")
            return ""

    # ── 현금 매수 ─────────────────────────────────────────────────────────────
    async def place_buy_order(
        self,
        code: str,
        qty: int,
        price: int = 0,             # 0 = 시장가
        order_type: str = "MARKET", # MARKET | LIMIT
    ) -> OrderResult:
        cano, acnt_prdt = self._acct()
        tr_id = self._tr("TTTC0802U", "VTTC0802U")
        ord_dvsn = "01" if order_type == "MARKET" else "00"
        body = {
            "CANO":         cano,
            "ACNT_PRDT_CD": acnt_prdt,
            "PDNO":         code,
            "ORD_DVSN":     ord_dvsn,
            "ORD_QTY":      str(qty),
            "ORD_UNPR":     str(price),
        }
        return await self._post_order(tr_id, body, f"매수[{code}×{qty}]")

    # ── 현금 매도 ─────────────────────────────────────────────────────────────
    async def place_sell_order(
        self,
        code: str,
        qty: int,
        price: int = 0,
        order_type: str = "MARKET",
    ) -> OrderResult:
        cano, acnt_prdt = self._acct()
        tr_id = self._tr("TTTC0801U", "VTTC0801U")
        ord_dvsn = "01" if order_type == "MARKET" else "00"
        body = {
            "CANO":         cano,
            "ACNT_PRDT_CD": acnt_prdt,
            "PDNO":         code,
            "ORD_DVSN":     ord_dvsn,
            "ORD_QTY":      str(qty),
            "ORD_UNPR":     str(price),
        }
        return await self._post_order(tr_id, body, f"매도[{code}×{qty}]")

    # ── 주문 취소 ─────────────────────────────────────────────────────────────
    async def cancel_order(self, order_no: str, code: str, qty: int) -> OrderResult:
        cano, acnt_prdt = self._acct()
        tr_id = self._tr("TTTC0803U", "VTTC0803U")
        body = {
            "CANO":           cano,
            "ACNT_PRDT_CD":   acnt_prdt,
            "KRX_FWDG_ORD_ORGNO": "",
            "ORGN_ODNO":      order_no,
            "ORD_DVSN":       "00",
            "RVSE_CNCL_DVSN_CD": "02",   # 02=취소
            "ORD_QTY":        str(qty),
            "ORD_UNPR":       "0",
            "QTY_ALL_ORD_YN": "Y",
        }
        return await self._post_order(tr_id, body, f"취소[{order_no}]")

    # ── 잔고 조회 ─────────────────────────────────────────────────────────────
    async def get_balance(self) -> BalanceResult:
        cano, acnt_prdt = self._acct()
        tr_id = self._tr("TTTC8434R", "VTTC8434R")
        params = {
            "CANO":                cano,
            "ACNT_PRDT_CD":        acnt_prdt,
            "AFHR_FLPR_YN":        "N",
            "OFL_YN":              "N",
            "INQR_DVSN":           "01",
            "UNPR_DVSN":           "01",
            "FUND_STTL_ICLD_YN":   "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN":           "01",
            "CTX_AREA_FK100":      "",
            "CTX_AREA_NK100":      "",
        }
        try:
            token = await self.auth.get_access_token()
            resp = await self._client.get(
                "/uapi/domestic-stock/v1/trading/inquire-balance",
                headers=self.auth.get_headers(token, tr_id),
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("rt_cd") != "0":
                return BalanceResult(
                    success=False,
                    error_msg=data.get("msg1", "잔고 조회 실패"),
                    raw=data,
                )

            output2 = data.get("output2", [{}])[0] if data.get("output2") else {}
            holdings = []
            for item in data.get("output1", []):
                qty = int(item.get("hldg_qty", 0) or 0)
                if qty <= 0:
                    continue
                avg_p = float(item.get("pchs_avg_pric", 0) or 0)
                cur_p = float(item.get("prpr", 0) or 0)
                pnl_pct = round((cur_p - avg_p) / avg_p * 100, 2) if avg_p > 0 else 0.0
                holdings.append({
                    "code":          item.get("pdno", ""),
                    "name":          item.get("prdt_name", ""),
                    "qty":           qty,
                    "avg_price":     int(avg_p),
                    "current_price": int(cur_p),
                    "eval_amount":   int(item.get("evlu_amt", 0) or 0),
                    "pnl_pct":       pnl_pct,
                    "pnl_amount":    int(item.get("evlu_pfls_amt", 0) or 0),
                })

            return BalanceResult(
                success=True,
                deposit=int(output2.get("ord_psbl_cash", 0) or 0),
                total_eval=int(output2.get("tot_evlu_amt", 0) or 0),
                total_buy=int(output2.get("pchs_amt_smtl_amt", 0) or 0),
                holdings=holdings,
                raw=data,
            )
        except Exception as e:
            logger.error(f"잔고 조회 오류: {e}")
            return BalanceResult(success=False, error_msg=str(e))

    # ── 주문 내역 조회 (당일 미체결 + 체결) ─────────────────────────────────
    async def get_orders(self, inqr_dvsn: str = "01") -> list[OpenOrder]:
        """inqr_dvsn: 01=체결, 02=미체결, 00=전체"""
        cano, acnt_prdt = self._acct()
        tr_id = self._tr("TTTC8001R", "VTTC8001R")
        params = {
            "CANO":           cano,
            "ACNT_PRDT_CD":   acnt_prdt,
            "INQR_STRT_DT":   "",
            "INQR_END_DT":    "",
            "SLL_BUY_DVSN_CD": "00",    # 00=전체 매도/매수
            "INQR_DVSN":      inqr_dvsn,
            "PDNO":           "",
            "ORD_GNO_BRNO":   "",
            "ODNO":           "",
            "INQR_DVSN_3":    "00",
            "INQR_DVSN_1":    "",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        try:
            token = await self.auth.get_access_token()
            resp = await self._client.get(
                "/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
                headers=self.auth.get_headers(token, tr_id),
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("rt_cd") != "0":
                logger.warning(f"주문조회 오류: {data.get('msg1')}")
                return []

            orders = []
            for item in data.get("output1", []):
                filled = int(item.get("tot_ccld_qty", 0) or 0)
                total  = int(item.get("ord_qty",      0) or 0)
                if total <= 0:
                    continue
                side = "BUY" if item.get("sll_buy_dvsn_cd") == "02" else "SELL"
                status = "FILLED" if filled >= total else ("PARTIAL" if filled > 0 else "PENDING")
                orders.append(OpenOrder(
                    order_no=item.get("odno", ""),
                    code=item.get("pdno", ""),
                    name=item.get("prdt_name", ""),
                    side=side,
                    order_price=int(item.get("ord_unpr", 0) or 0),
                    order_qty=total,
                    filled_qty=filled,
                    status=status,
                ))
            return orders
        except Exception as e:
            logger.error(f"주문조회 오류: {e}")
            return []

    # ── 내부: POST 주문 공통 처리 ─────────────────────────────────────────────
    async def _post_order(self, tr_id: str, body: dict, label: str) -> OrderResult:
        try:
            hash_key = await self._get_hashkey(body)
            token = await self.auth.get_access_token()
            resp = await self._client.post(
                "/uapi/domestic-stock/v1/trading/order-cash",
                headers=self.auth.get_headers(token, tr_id, hash_key),
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("rt_cd") != "0":
                msg = data.get("msg1", "주문 실패")
                logger.error(f"[{label}] KIS 오류: {msg}")
                return OrderResult(success=False, error_msg=msg, raw=data)

            order_no = data.get("output", {}).get("ODNO", "")
            logger.info(f"[{label}] 주문 성공 — 주문번호: {order_no}")
            return OrderResult(success=True, order_no=order_no, raw=data)

        except httpx.HTTPStatusError as e:
            msg = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
            logger.error(f"[{label}] {msg}")
            return OrderResult(success=False, error_msg=msg)
        except Exception as e:
            logger.error(f"[{label}] 주문 오류: {e}")
            return OrderResult(success=False, error_msg=str(e))

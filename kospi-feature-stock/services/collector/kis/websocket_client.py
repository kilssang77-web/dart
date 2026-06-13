import asyncio
import json
import logging
from datetime import datetime
from typing import Callable
import websockets
from .auth import KISAuthManager, KISConfig

logger = logging.getLogger(__name__)

# H0STCNT0 / H0NXCNT0 필드 인덱스 — 두 TR 모두 0~21 동일 구조
_TICK_FIELDS = {
    "code": 0, "time": 1, "price": 2, "prev_close": 3,
    "change": 4, "change_rate": 5, "open": 7, "high": 8, "low": 9,
    "cum_volume": 12, "cum_amount": 13, "bid_ask_ratio": 19,
    "is_buy_flag": 21,
}

# 지원하는 실시간 체결 TR_ID
_TICK_TR_IDS = {"H0STCNT0", "H0NXCNT0"}

# VI 에버트 TR_ID (직접 종목 구독 필요 없음 — 거래소 전체 피드)
_VI_TR_IDS = {"H0STVI0", "H0STCVI0"}

# H0STVI0/H0STCVI0 필드 인덱스 (KIS 정의 기준)
# 0=종목코드 1=시간 2=VI유형 3=VI기준가 4=현재가 5=이전단새기준가
_VI_FIELDS = {"code": 0, "time": 1, "vi_type": 2, "ref_price": 3, "price": 4, "prev_ref_price": 5}


class KISWebSocketClient:

    def __init__(self, config: KISConfig, auth: KISAuthManager):
        self.config = config
        self.auth   = auth

    async def subscribe_tick(
        self,
        codes: list[str],
        callback: Callable,
        chunk_size: int = 30,
        include_nxt: bool = False,
    ) -> None:
        """
        include_nxt=True 이면 각 청크마다 KRX(H0STCNT0)와 NXT(H0NXCNT0) 동시 구독.
        하나의 WebSocket 연결에서 두 TR_ID를 모두 구독하므로 연결 수는 동일.
        """
        chunks = [codes[i:i+chunk_size] for i in range(0, len(codes), chunk_size)]
        tasks  = [self._ws_loop(chunk, callback, include_nxt) for chunk in chunks]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def subscribe_vi_events(self, callback: Callable) -> None:
        """정적VI(H0STVI0) 및 동적VI(H0STCVI0) 전체 피드 구독 (단일 WebSocket)."""
        approval_key = await self.auth.get_ws_approval_key()
        backoff = 1
        async for ws in websockets.connect(
            self.config.ws_url,
            ping_interval=20, ping_timeout=30,
            max_size=10 * 1024 * 1024, open_timeout=30,
        ):
            try:
                # VI는 종목코드 각각 구독하는 게 아니라 거래소에 한번만 등록
                await self._subscribe(ws, approval_key, "", "H0STVI0")
                await asyncio.sleep(0.05)
                await self._subscribe(ws, approval_key, "", "H0STCVI0")
                logger.info("VI event feed subscribed (H0STVI0 + H0STCVI0)")
                backoff = 1
                async for raw in ws:
                    parsed = self._parse_vi(raw)
                    if parsed:
                        await callback(parsed)
            except websockets.ConnectionClosed as e:
                logger.warning(f"VI WS closed: {e}. Reconnecting in {backoff}s...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
                approval_key = await self.auth.get_ws_approval_key()
                continue
            except Exception as e:
                logger.error(f"VI WS error: {e}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue

    async def _ws_loop(
        self,
        codes: list[str],
        callback: Callable,
        include_nxt: bool,
    ) -> None:
        approval_key = await self.auth.get_ws_approval_key()
        backoff = 1

        async for ws in websockets.connect(
            self.config.ws_url,
            ping_interval=20,
            ping_timeout=30,
            max_size=10 * 1024 * 1024,
            open_timeout=30,
        ):
            try:
                for code in codes:
                    await self._subscribe(ws, approval_key, code, "H0STCNT0")
                    await asyncio.sleep(0.05)
                    if include_nxt:
                        await self._subscribe(ws, approval_key, code, "H0NXCNT0")
                        await asyncio.sleep(0.05)

                exchange = "KRX+NXT" if include_nxt else "KRX"
                logger.info(f"WS subscribed {len(codes)} stocks [{exchange}]")
                backoff = 1

                async for raw in ws:
                    parsed = self._parse(raw)
                    if parsed:
                        await callback(parsed)

            except websockets.ConnectionClosed as e:
                logger.warning(f"WS closed: {e}. Reconnecting in {backoff}s...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
                approval_key = await self.auth.get_ws_approval_key()
                continue
            except Exception as e:
                logger.error(f"WS error: {e}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue

    async def _subscribe(
        self,
        ws,
        approval_key: str,
        code: str,
        tr_id: str = "H0STCNT0",
    ) -> None:
        await ws.send(json.dumps({
            "header": {
                "approval_key": approval_key,
                "custtype": "P",
                "tr_type": "1",
                "content-type": "utf-8",
            },
            "body": {"input": {"tr_id": tr_id, "tr_key": code}},
        }))

    def _parse(self, raw: str) -> dict | None:
        if raw.startswith("{"):
            data = json.loads(raw)
            if data.get("header", {}).get("tr_id") == "PINGPONG":
                return None
            return None

        parts = raw.split("|")
        if len(parts) < 4:
            return None
        tr_id = parts[1]
        if tr_id not in _TICK_TR_IDS:
            return None
        tick = self._parse_tick(parts[3])
        if tick:
            tick["exchange"] = "NXT" if tr_id == "H0NXCNT0" else "KRX"
        return tick or None

    def _parse_vi(self, raw: str) -> dict | None:
        """H0STVI0/H0STCVI0 메시지 파싱 → VI 이벤트 dict."""
        if raw.startswith("{"):
            return None
        parts = raw.split("|")
        if len(parts) < 4:
            return None
        tr_id = parts[1]
        if tr_id not in _VI_TR_IDS:
            return None
        f = parts[3].split("^")
        if len(f) < 5:
            return {}
        try:
            code = f[_VI_FIELDS["code"]]
            price = int(f[_VI_FIELDS["price"]]) if f[_VI_FIELDS["price"]] else 0
            ref   = int(f[_VI_FIELDS["ref_price"]]) if f[_VI_FIELDS["ref_price"]] else 0
            change_rate = round((price - ref) / ref * 100, 2) if ref > 0 else 0.0
            return {
                "code":        code,
                "time":        f[_VI_FIELDS["time"]],
                "price":       price,
                "prev_close":  ref,
                "change":      price - ref,
                "change_rate": change_rate,
                "volume":      0,
                "is_vi":       True,
                "vi_kind":     "static" if tr_id == "H0STVI0" else "dynamic",
                "ts":          datetime.now().isoformat(),
            }
        except (ValueError, IndexError) as e:
            logger.debug(f"VI parse error: {e}")
            return {}

    def _parse_tick(self, raw: str) -> dict:
        f = raw.split("^")
        if len(f) < 22:
            return {}
        try:
            price  = int(f[2])
            change = int(f[4]) if f[4] else 0
            return {
                "code":         f[0],
                "time":         f[1],
                "price":        price,
                "prev_close":   price - change,
                "change":       change,
                "change_rate":  float(f[5]) if f[5] else 0.0,
                "open":         int(f[7]) if f[7] else 0,
                "high":         int(f[8]) if f[8] else 0,
                "low":          int(f[9]) if f[9] else 0,
                "volume":       int(f[12]) if f[12] else 0,
                "cum_volume":   int(f[13]) if f[13] else 0,
                "cum_amount":   int(f[14]) if f[14] else 0,
                "bid_ask_ratio":float(f[19]) if f[19] else 0.0,
                "is_buy":       f[21] == "1",
                "ts":           datetime.now().isoformat(),
            }
        except (ValueError, IndexError) as e:
            logger.debug(f"Tick parse error: {e}")
            return {}
import asyncio
import json
import logging
from datetime import datetime
from typing import Callable
import websockets
from .auth import KISAuthManager, KISConfig

logger = logging.getLogger(__name__)

# H0STCNT0 필드 인덱스 매핑
_TICK_FIELDS = {
    "code": 0, "time": 1, "price": 2, "prev_close": 3,
    "change": 4, "change_rate": 5, "open": 7, "high": 8, "low": 9,
    "cum_volume": 12, "cum_amount": 13, "bid_ask_ratio": 19,
    "is_buy_flag": 21,
}


class KISWebSocketClient:

    def __init__(self, config: KISConfig, auth: KISAuthManager):
        self.config = config
        self.auth = auth

    async def subscribe_tick(
        self,
        codes: list[str],
        callback: Callable,
        chunk_size: int = 30,
    ) -> None:
        """실시간 체결 구독. codes가 많으면 청크로 나눠 병렬 연결."""
        chunks = [codes[i:i+chunk_size] for i in range(0, len(codes), chunk_size)]
        tasks = [self._ws_loop(chunk, callback) for chunk in chunks]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _ws_loop(self, codes: list[str], callback: Callable) -> None:
        approval_key = await self.auth.get_ws_approval_key()
        backoff = 1

        async for ws in websockets.connect(
            self.config.ws_url,
            ping_interval=20,
            ping_timeout=10,
            max_size=10 * 1024 * 1024,
            open_timeout=30,
        ):
            try:
                for code in codes:
                    await self._subscribe(ws, approval_key, code)
                    await asyncio.sleep(0.05)

                logger.info(f"WS subscribed {len(codes)} stocks")
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

    async def _subscribe(self, ws, approval_key: str, code: str) -> None:
        await ws.send(json.dumps({
            "header": {
                "approval_key": approval_key,
                "custtype": "P",
                "tr_type": "1",
                "content-type": "utf-8",
            },
            "body": {"input": {"tr_id": "H0STCNT0", "tr_key": code}},
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
        if parts[1] != "H0STCNT0":
            return None
        return self._parse_tick(parts[3])

    def _parse_tick(self, raw: str) -> dict:
        f = raw.split("^")
        if len(f) < 22:
            return {}
        try:
            price  = int(f[2])
            change = int(f[4]) if f[4] else 0
            # f[3]은 전일대비 부호코드(1=상한,2=상승,3=보합,4=하한,5=하락), 전일종가 = 현재가 - 전일대비
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

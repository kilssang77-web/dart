"""
금융위원회 공공데이터포털 주식시세 API 클라이언트.

End-Point: https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo
- 업데이트 주기: T+1 (전일 EOD 데이터, T+1 오전 제공)
- 제공 필드: 종가/시가/고가/저가/거래량/거래대금/상장주식수/시가총액
- 초당 최대 30 TPS, numOfRows 최대 10,000
"""
import asyncio
import logging
import os

import httpx

logger = logging.getLogger(__name__)

_API_URL = (
    "https://apis.data.go.kr/1160100/service/"
    "GetStockSecuritiesInfoService/getStockPriceInfo"
)
_API_KEY   = os.environ.get("GOV_DATA_API_KEY", "")
_PAGE_SIZE = 5_000
_TIMEOUT   = 30.0
_RETRY     = 3


async def fetch_stock_prices(bas_dt: str) -> list[dict]:
    """
    지정 일자(YYYYMMDD)의 전 종목 시세 조회.

    반환 예시:
        [{"srtnCd": "005930", "mrktTotAmt": 550_000_000_000,
          "lstgStCnt": 5_969_782_550, "mrktCtg": "KOSPI", ...}, ...]
    결과 없으면 빈 리스트 반환.
    """
    if not _API_KEY:
        raise RuntimeError("GOV_DATA_API_KEY 환경변수가 설정되지 않았습니다.")

    results: list[dict] = []
    page = 1

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        while True:
            params = {
                "serviceKey": _API_KEY,
                "numOfRows":  _PAGE_SIZE,
                "pageNo":     page,
                "resultType": "json",
                "basDt":      bas_dt,
            }
            for attempt in range(_RETRY):
                try:
                    resp = await client.get(_API_URL, params=params)
                    resp.raise_for_status()
                    break
                except httpx.HTTPError as e:
                    if attempt == _RETRY - 1:
                        raise
                    logger.warning(f"[govdata] HTTP 오류 (재시도 {attempt+1}/{_RETRY}): {e}")
                    await asyncio.sleep(2 ** attempt)

            body  = resp.json().get("response", {}).get("body", {})
            total = int(body.get("totalCount", 0))
            raw   = body.get("items", {}).get("item", [])

            # API가 1건이면 dict, 2건 이상이면 list 반환
            if isinstance(raw, dict):
                raw = [raw]
            results.extend(raw)

            if not raw or page * _PAGE_SIZE >= total:
                break
            page += 1
            await asyncio.sleep(0.1)  # 30 TPS 준수

    logger.debug(f"[govdata] {bas_dt} 조회: {len(results)}개 종목")
    return results

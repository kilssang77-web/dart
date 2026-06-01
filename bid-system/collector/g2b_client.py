"""나라장터 Open API 클라이언트 (공사 입찰공고 전용)."""
import asyncio
import random
import logging
from datetime import datetime
from typing import Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

G2B_API_BASE = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService"


class G2BApiClient:

    def __init__(self, service_key: str):
        self._key = service_key
        self._client = httpx.AsyncClient(timeout=30.0)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=15))
    async def _get(self, endpoint: str, params: dict) -> dict:
        params["serviceKey"] = self._key
        params["type"] = "json"
        resp = await self._client.get(f"{G2B_API_BASE}/{endpoint}", params=params)
        resp.raise_for_status()
        return resp.json()

    async def fetch_notices(self, date_from: str, date_to: str) -> list[dict]:
        """공사 입찰 공고 목록 수집."""
        results = []
        page = 1
        while True:
            try:
                data = await self._get("getBidPblancListInfoCnstwk", {
                    "inqryBgnDt": date_from,
                    "inqryEndDt": date_to,
                    "inqryDiv":   1,
                    "numOfRows":  100,
                    "pageNo":     page,
                })
                body  = data.get("response", {}).get("body", {})
                items = body.get("items", [])
                if not items:
                    break
                if isinstance(items, dict):
                    items = [items]
                results.extend(items)
                total = int(body.get("totalCount", 0))
                logger.info(f"공고 수집 페이지 {page} — {len(results)}/{total}건")
                if page * 100 >= total:
                    break
                page += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"G2B API 오류: {e}")
                break
        return results

    async def fetch_result(self, bid_no: str) -> list[dict]:
        """개찰 결과 조회 (공고 공종: 공사)."""
        try:
            data = await self._get("getBidPblancListInfoCnstwk", {
                "bidNtceNo": bid_no,
                "inqryDiv":  1,
                "numOfRows": 100,
                "pageNo":    1,
            })
            items = data.get("response", {}).get("body", {}).get("items", [])
            if isinstance(items, dict):
                return [items]
            return items or []
        except Exception as e:
            logger.debug(f"결과 조회 실패 {bid_no}: {e}")
            return []

    async def close(self):
        await self._client.aclose()


class G2BCrawler:
    """API 미지원 데이터 보완 크롤러 (공사 입찰)."""

    async def fetch_result_html(self, bid_no: str) -> list[dict]:
        """G2B 공사 개찰결과 페이지 크롤링 (Playwright 필요)."""
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                page    = await browser.new_page()
                await page.set_extra_http_headers({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124"
                })
                # 공사(cns) 경로 사용 — goods 경로 아님
                url = f"https://www.g2b.go.kr/pps/cns/prd-modify/open-close-result?bidNo={bid_no}"
                await page.goto(url, wait_until="networkidle", timeout=20_000)
                await asyncio.sleep(random.uniform(1, 2))

                rows = await page.query_selector_all("table tbody tr")
                results = []
                for row in rows:
                    cells = await row.query_selector_all("td")
                    if len(cells) < 4:
                        continue
                    try:
                        rank     = int((await cells[0].inner_text()).strip())
                        company  = (await cells[1].inner_text()).strip()
                        rate_txt = (await cells[3].inner_text()).strip().replace("%", "")
                        rate     = float(rate_txt) / 100
                        winner   = any("낙찰" in (await c.inner_text()) for c in cells)
                        results.append({
                            "rank":      rank,
                            "company":   company,
                            "bid_rate":  rate,
                            "is_winner": winner,
                        })
                    except (ValueError, IndexError):
                        continue
                await browser.close()
                return results
        except Exception as e:
            logger.debug(f"크롤링 실패 {bid_no}: {e}")
            return []

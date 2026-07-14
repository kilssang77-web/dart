import asyncio, sys
sys.path.insert(0, "/app")
from main import G2B_API_KEY, G2B_RESULT_BASE
import httpx

async def test():
    params = {
        "inqryDiv": 1, "inqryBgnDt": "202512010000", "inqryEndDt": "202512312359",
        "numOfRows": 2, "pageNo": 1, "type": "json", "serviceKey": G2B_API_KEY,
    }
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.get(f"{G2B_RESULT_BASE}/getScsbidListSttusCnstwk", params=params)
        body = r.json().get("response", {}).get("body", {})
        items = body.get("items", [])
        if isinstance(items, dict): items = [items]
        if items:
            print("=== 필드 목록 (1번째 항목) ===")
            for k, v in sorted(items[0].items()):
                print(f"  {k}: {repr(v)}")
asyncio.run(test())

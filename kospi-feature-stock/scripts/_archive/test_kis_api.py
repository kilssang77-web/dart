import asyncio, os, httpx, json
import redis as redis_lib

async def test():
    r = redis_lib.from_url(os.environ["REDIS_URL"])
    token = r.get("kis:access_token").decode()
    headers = {
        "authorization": f"Bearer {token}",
        "appkey": os.environ["KIS_APP_KEY"],
        "appsecret": os.environ["KIS_APP_SECRET"],
        "custtype": "P",
    }

    async with httpx.AsyncClient() as c:
        # TR_ID 후보 테스트
        for tr_id in ["FHKST03010100", "FHKST01010400"]:
            resp = await c.get(
                "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
                headers={**headers, "tr_id": tr_id},
                params={
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_INPUT_ISCD": "005930",
                    "FID_INPUT_DATE_1": "20260101",
                    "FID_INPUT_DATE_2": "20260604",
                    "FID_PERIOD_DIV_CODE": "D",
                    "FID_ORG_ADJ_PRC": "0",
                },
            )
            d = resp.json()
            o2 = d.get("output2", [])
            print(f"TR_ID={tr_id} | rt_cd={d.get('rt_cd')} | keys={list(d.keys())} | output2={len(o2)}")
            if o2:
                print(f"  sample: {json.dumps(o2[0], ensure_ascii=False)[:250]}")

        # 별도 경로 시도: inquire-daily-price
        resp3 = await c.get(
            "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-daily-price",
            headers={**headers, "tr_id": "FHKST01010400"},
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": "005930",
                "FID_INPUT_DATE_1": "20260101",
                "FID_INPUT_DATE_2": "20260604",
                "FID_PERIOD_DIV_CODE": "D",
            },
        )
        d3 = resp3.json()
        o = d3.get("output", [])
        print(f"\ninquire-daily-price | rt_cd={d3.get('rt_cd')} | keys={list(d3.keys())} | output={len(o) if isinstance(o, list) else type(o)}")
        if isinstance(o, list) and o:
            print(f"  sample: {json.dumps(o[0], ensure_ascii=False)[:250]}")

asyncio.run(test())

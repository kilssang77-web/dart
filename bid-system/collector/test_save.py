import asyncio, sys
sys.path.insert(0, "/app")
from main import G2B_API_KEY, G2B_RESULT_BASE, MkSession, _parse_amount
from sqlalchemy import text
import httpx

async def test_save():
    params = {"inqryDiv":1,"inqryBgnDt":"202512010000","inqryEndDt":"202512102359","numOfRows":5,"pageNo":1,"type":"json","serviceKey":G2B_API_KEY}
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.get(f"{G2B_RESULT_BASE}/getScsbidListSttusCnstwk", params=params)
        body = r.json().get("response",{}).get("body",{})
        items = body.get("items",[])
        if isinstance(items,dict): items=[items]
        print(f"items={len(items)}")
        for it in items[:2]:
            print(f"  bidNtceNo={it.get('bidNtceNo')} winner={it.get('bidwinnrNm')} rate={it.get('sucsfbidRate')} prtcpt={it.get('prtcptCnum')}")
        
        db = MkSession()
        saved = 0
        try:
            for item in items:
                bid_no = (item.get("bidNtceNo") or "").strip()
                if not bid_no: continue
                row = db.execute(text("SELECT id FROM bids WHERE announcement_no=:no LIMIT 1"),{"no":bid_no}).fetchone()
                if not row: continue
                bid_id = row[0]
                comp_name = (item.get("bidwinnrNm") or "").strip()
                if not comp_name: continue
                try:
                    bid_rate = float(str(item.get("sucsfbidRate") or 0).replace("%","").strip()) / 100
                except: bid_rate = 0.0
                bid_amount = _parse_amount(item.get("sucsfbidAmt")) or 0
                try: participant_count = int(item.get("prtcptCnum") or 0)
                except: participant_count = 0
                comp_row = db.execute(text("INSERT INTO competitors (name) VALUES (:n) ON CONFLICT (name) DO UPDATE SET name=EXCLUDED.name RETURNING id"),{"n":comp_name}).fetchone()
                db.commit()
                comp_id = comp_row[0]
                db.execute(text("INSERT INTO bid_results (bid_id,competitor_id,bid_amount,bid_rate,rank,is_winner) VALUES (:bid,:comp,:amt,:rate,1,true) ON CONFLICT (bid_id,competitor_id) DO UPDATE SET bid_amount=EXCLUDED.bid_amount,bid_rate=EXCLUDED.bid_rate,rank=EXCLUDED.rank,is_winner=EXCLUDED.is_winner"),{"bid":bid_id,"comp":comp_id,"amt":bid_amount,"rate":bid_rate})
                db.execute(text("UPDATE bids SET status='closed', participant_count=CASE WHEN :pc>0 THEN :pc ELSE participant_count END WHERE id=:id"),{"id":bid_id,"pc":participant_count})
                saved += 1
            db.commit()
        finally:
            db.close()
        print(f"saved={saved}")

asyncio.run(test_save())

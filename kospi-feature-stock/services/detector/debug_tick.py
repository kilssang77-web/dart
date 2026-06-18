import asyncio, os, sys, logging
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")
sys.path.insert(0, "/app")
import redis.asyncio as redis_lib
from rules.breakout import BreakoutDetector
from rules.vi_detector import VIDetector

async def run():
    r = redis_lib.from_url(os.environ["REDIS_URL"])
    brk = BreakoutDetector(r)
    vi  = VIDetector(r)

    # Check Redis keys
    h20  = await r.get("stats:005930:high_20d")
    h260 = await r.get("stats:005930:high_260d")
    vi_k = await r.get("vi:005930:triggered")
    print(f"high_20d={h20}  high_260d={h260}  vi_key={vi_k}")

    # Test breakout
    tick_brk = {"code":"005930","price":364105,"change_rate":3.2,"volume":1500000,"amount":5000000000}
    sigs = await brk.detect(tick_brk)
    print(f"Breakout sigs: {sigs}")

    # Delete VI key and test VI
    await r.delete("vi:005930:triggered")
    tick_vi = {"code":"005930","price":90000,"change_rate":12.5,"volume":3000000,"amount":8000000000}
    sig_vi = await vi.detect(tick_vi)
    print(f"VI sig: {sig_vi}")

    await r.aclose()

asyncio.run(run())

import sys, os
sys.path.insert(0, "/app")
os.chdir("/app")
import logging
logging.basicConfig(level=logging.WARNING)

from app.database import SessionLocal
from app.services import HybridRecommendService
from datetime import datetime

db = SessionLocal()

class FakeReq:
    agency_id = 777
    industry_id = 24
    region_id = 0
    base_amount = 500000000
    construction_period = None
    min_bid_rate = 0.87745
    known_competitor_ids = []
    bid_open_date = None

try:
    svc = HybridRecommendService()
    result = svc.recommend_v2(db, FakeReq())
    print("성공:", list(result.keys()))
except Exception as e:
    import traceback
    print("오류:", traceback.format_exc())
db.close()

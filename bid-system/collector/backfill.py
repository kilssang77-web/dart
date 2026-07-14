from main import collect_history
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
import os

DATABASE_URL = os.getenv("DATABASE_URL", "")
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    max_date = conn.execute(text("SELECT MAX(notice_date) FROM bids WHERE source='g2b'")).scalar()

print(f"현재 최신 공고일: {max_date}")

if max_date:
    start = max_date + timedelta(days=1)
    days_needed = (datetime.now().date() - start).days + 1
    print(f"수집 필요 기간: {start} ~ 오늘 ({days_needed}일)")
    if days_needed > 0:
        collect_history(days_needed)
    else:
        print("수집 완료 상태")
else:
    print("데이터 없음, 전체 수집")
    collect_history(180)
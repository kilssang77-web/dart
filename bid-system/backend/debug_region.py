import os
from sqlalchemy import create_engine, text
engine = create_engine(os.environ["DATABASE_URL"])
with engine.connect() as conn:
    rows = conn.execute(text(
        "SELECT id, construction_site, eligible_regions, region_id FROM bids LIMIT 5"
    )).fetchall()
    print("=== 지역 필드 ===")
    for r in rows:
        print(f"id={r[0]}, site={repr(r[1])[:70]}, eligible={repr(r[2])[:70]}, rid={r[3]}")
    regs = conn.execute(text("SELECT id, name, code, parent_id FROM regions ORDER BY id LIMIT 25")).fetchall()
    print("\n=== regions 테이블 ===")
    for r in regs:
        print(f"id={r[0]}, name={r[1]}, code={r[2]}, parent={r[3]}")
    # 기관명에서 지역 패턴
    agencies = conn.execute(text("SELECT id, name FROM agencies ORDER BY id LIMIT 20")).fetchall()
    print("\n=== agencies 샘플 ===")
    for r in agencies:
        print(f"id={r[0]}, name={r[1]}")

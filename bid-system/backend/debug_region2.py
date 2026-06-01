import os
from sqlalchemy import create_engine, text
engine = create_engine(os.environ["DATABASE_URL"])
with engine.connect() as conn:
    # G2B API 수집 데이터에서 지역 관련 필드 확인
    rows = conn.execute(text("""
        SELECT b.id, b.announcement_no, b.title, b.ntce_url,
               a.name AS agency_name, b.region_id, b.construction_site, b.eligible_regions
        FROM bids b LEFT JOIN agencies a ON a.id = b.agency_id
        WHERE b.region_id IS NOT NULL LIMIT 5
    """)).fetchall()
    print("=== region_id 있는 공고 ===")
    for r in rows:
        print(f"id={r[0]}, no={r[1]}, agency={r[4]}, region_id={r[5]}, site={r[6]}, eligible={r[7]}")
    
    # 지역 키워드를 포함한 기관명 분포
    rows2 = conn.execute(text("""
        SELECT 
            COUNT(*) FILTER (WHERE a.name LIKE '%서울%') AS seoul,
            COUNT(*) FILTER (WHERE a.name LIKE '%부산%') AS busan,
            COUNT(*) FILTER (WHERE a.name LIKE '%경기%') AS gyeonggi,
            COUNT(*) FILTER (WHERE a.name LIKE '%경남%' OR a.name LIKE '%경상남도%') AS gyeongnam,
            COUNT(*) FILTER (WHERE a.name LIKE '%경북%' OR a.name LIKE '%경상북도%') AS gyeongbuk,
            COUNT(*) FILTER (WHERE a.name LIKE '%전남%' OR a.name LIKE '%전라남도%') AS jeonnam,
            COUNT(*) FILTER (WHERE a.name LIKE '%전북%' OR a.name LIKE '%전라북도%') AS jeonbuk,
            COUNT(*) FILTER (WHERE a.name LIKE '%충남%' OR a.name LIKE '%충청남도%') AS chungnam,
            COUNT(*) FILTER (WHERE a.name LIKE '%충북%' OR a.name LIKE '%충청북도%') AS chungbuk,
            COUNT(*) FILTER (WHERE a.name LIKE '%강원%') AS gangwon,
            COUNT(*) FILTER (WHERE a.name LIKE '%대구%') AS daegu,
            COUNT(*) FILTER (WHERE a.name LIKE '%인천%') AS incheon,
            COUNT(*) FILTER (WHERE a.name LIKE '%대전%') AS daejeon,
            COUNT(*) FILTER (WHERE a.name LIKE '%광주%') AS gwangju,
            COUNT(*) FILTER (WHERE a.name LIKE '%울산%') AS ulsan,
            COUNT(*) FILTER (WHERE a.name LIKE '%제주%') AS jeju,
            COUNT(*) FILTER (WHERE a.name LIKE '%세종%') AS sejong,
            COUNT(DISTINCT b.id) AS total_bids
        FROM bids b LEFT JOIN agencies a ON a.id = b.agency_id
        WHERE b.source = 'g2b'
    """)).fetchone()
    labels = ['서울','부산','경기','경남','경북','전남','전북','충남','충북','강원','대구','인천','대전','광주','울산','제주','세종','전체']
    print("\n=== 기관명 기반 지역 분포 ===")
    for l, v in zip(labels, rows2):
        print(f"  {l}: {v}")
    
    # 공고번호 패턴 확인 (지역코드 포함 여부)
    sample_nos = conn.execute(text("SELECT announcement_no FROM bids WHERE source='g2b' LIMIT 10")).fetchall()
    print("\n=== 공고번호 샘플 ===")
    for r in sample_nos:
        print(f"  {r[0]}")

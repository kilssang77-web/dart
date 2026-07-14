"""my_bid_records 낙찰 건 → bid_journal 이관 스크립트."""
import os, sys
sys.path.insert(0, "/app")
os.environ.setdefault("DATABASE_URL", "postgresql://biduser:bidpass@localhost:5432/biddb")

from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://biduser:bidpass@bid_postgres:5432/biddb")
engine = create_engine(DATABASE_URL)

with engine.begin() as conn:
    # admin user_id
    admin = conn.execute(text("SELECT id FROM users WHERE role='admin' LIMIT 1")).fetchone()
    admin_id = admin[0] if admin else 1

    # fallback agency
    ag = conn.execute(text("SELECT id FROM agencies WHERE name='미상' LIMIT 1")).fetchone()
    fallback_agency_id = ag[0] if ag else 8533

    # 이관 대상
    rows = conn.execute(text("""
        SELECT id, announcement_no, submitted_rate, actual_winner_rate, title, created_at
        FROM my_bid_records
        WHERE result = 'won'
        ORDER BY id
    """)).fetchall()

    inserted, skipped = 0, 0
    for row in rows:
        mbr_id, ano, sub_rate, win_rate, title, created_at = row

        # 이미 bid_journal에 동일 공고번호 존재하면 skip
        check_ano = ano if ano else f"MANUAL-MBR-{mbr_id}"
        exists = conn.execute(text(
            "SELECT 1 FROM bid_journal WHERE announcement_no = :ano LIMIT 1"
        ), {"ano": check_ano}).fetchone()
        if exists:
            print(f"  SKIP (exists): {check_ano} - {title}")
            skipped += 1
            continue

        # bids 조회 or 스텁 생성
        # 공고번호 없으면 고유 플레이스홀더 생성
        effective_ano = ano if ano else f"MANUAL-MBR-{mbr_id}"

        bid_row = conn.execute(text(
            "SELECT id FROM bids WHERE announcement_no = :ano LIMIT 1"
        ), {"ano": effective_ano}).fetchone()

        if bid_row:
            bid_id = bid_row[0]
        else:
            res = conn.execute(text("""
                INSERT INTO bids (announcement_no, title, agency_id, created_at, updated_at)
                VALUES (:ano, :title, :agency_id, NOW(), NOW())
                RETURNING id
            """), {"ano": effective_ano, "title": title, "agency_id": fallback_agency_id})
            bid_id = res.fetchone()[0]
            print(f"  [stub bid created] id={bid_id}, ano={ano}")

        sub = float(sub_rate)
        win = float(win_rate) if win_rate else sub
        rate_gap = round(win - sub, 6)

        conn.execute(text("""
            INSERT INTO bid_journal (
                user_id, bid_id, announcement_no,
                submitted_rate, result, winner_rate, rate_gap,
                note, submitted_at, created_at, updated_at
            ) VALUES (
                :uid, :bid_id, :ano,
                :sub, '낙찰', :win, :gap,
                :note, :created_at, :created_at, NOW()
            )
        """), {
            "uid": admin_id,
            "bid_id": bid_id,
            "ano": effective_ano,
            "sub": sub,
            "win": win,
            "gap": rate_gap,
            "note": f"[my_bid_records 이관] {title}",
            "created_at": created_at,
        })

        # actual_bid_outcomes 동기화
        conn.execute(text("""
            INSERT INTO actual_bid_outcomes (
                bid_id, user_id, announcement_no,
                submitted_rate, result, winner_rate,
                collected_at
            ) VALUES (
                :bid_id, :uid, :ano,
                :sub, 'WON', :win,
                NOW()
            )
            ON CONFLICT DO NOTHING
        """), {
            "bid_id": bid_id, "uid": admin_id,
            "ano": effective_ano, "sub": sub, "win": win,
        })

        print(f"  INSERT: {effective_ano} - {title} | sub={sub:.4f} win={win:.4f} gap={rate_gap:+.4f}")
        inserted += 1

    print(f"\n완료: 이관={inserted}건, 스킵={skipped}건")

    # 결과 확인
    total = conn.execute(text("SELECT COUNT(*) FROM bid_journal")).scalar()
    wins  = conn.execute(text("SELECT COUNT(*) FROM bid_journal WHERE result='낙찰'")).scalar()
    print(f"bid_journal: 전체={total}, 낙찰={wins}")

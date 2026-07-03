"""KISCON 경쟁사 시공능력평가·실적 수집 서비스

수집 전략:
1. biz_reg_no 있는 경쟁사 중 bid_count 상위 N개 선정
2. KISCON API로 면허 업종·평가금액 수집 (api_key 없으면 스킵)
3. bid_results에서 주력 발주기관·공종·2년 실적 집계
4. competitor_kiscon_profiles upsert
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_STATS_YEARS = 2  # 주력 발주기관·실적 집계 기간 (년)
_TOP_AGENCIES = 5  # 주력 발주기관 top N
_TOP_INDUSTRIES = 3  # 주력 공종 top N


def collect_kiscon_profiles(
    db: Session,
    limit: int = 300,
    force_refresh: bool = False,
    kiscon_api_key: str = "",
) -> dict:
    """
    경쟁사 KISCON 프로필 수집 및 업데이트.

    Returns:
        {"total": int, "kiscon_fetched": int, "stats_updated": int, "elapsed_s": float}
    """
    t0 = datetime.now(timezone.utc)

    # ① 수집 대상 경쟁사 선정
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    condition = "" if force_refresh else "AND (kp.stats_updated_at IS NULL OR kp.stats_updated_at < :cutoff)"
    rows = db.execute(text(f"""
        SELECT c.id, c.biz_reg_no, c.name
        FROM competitors c
        LEFT JOIN competitor_kiscon_profiles kp ON kp.competitor_id = c.id
        WHERE c.biz_reg_no IS NOT NULL
          AND c.biz_reg_no != ''
          {condition}
        ORDER BY (
            SELECT COUNT(*) FROM bid_results br WHERE br.competitor_id = c.id
        ) DESC
        LIMIT :limit
    """), {"cutoff": cutoff, "limit": limit}).fetchall()

    if not rows:
        logger.info("KISCON 수집 대상 없음")
        return {"total": 0, "kiscon_fetched": 0, "stats_updated": 0, "elapsed_s": 0.0}

    logger.info("KISCON 수집 대상: %d개사", len(rows))

    # ② KISCON API 배치 조회 (api_key 있을 때만)
    kiscon_profiles: dict = {}
    kiscon_fetched = 0
    if kiscon_api_key:
        from app.collector.kiscon_client import KisconClient
        client = KisconClient(api_key=kiscon_api_key)
        try:
            biz_reg_nos = [r[1] for r in rows if r[1]]
            kiscon_profiles = client.batch_fetch(biz_reg_nos)
            kiscon_fetched = len(kiscon_profiles)
            logger.info("KISCON API 조회 완료: %d/%d개사", kiscon_fetched, len(biz_reg_nos))
        except Exception as exc:
            logger.error("KISCON API 배치 조회 실패: %s", exc)
        finally:
            client.close()

    # ③ bid_results 집계 + upsert
    stats_updated = 0
    cutoff_2y = datetime.now(timezone.utc) - timedelta(days=365 * _STATS_YEARS)

    for comp_id, biz_reg_no, comp_name in rows:
        try:
            # 주력 발주기관 집계
            agency_rows = db.execute(text("""
                SELECT a.name,
                       COUNT(*) AS bid_cnt,
                       SUM(CASE WHEN br.is_winner THEN 1 ELSE 0 END) AS win_cnt
                FROM bid_results br
                JOIN bids b ON b.id = br.bid_id
                JOIN agencies a ON a.id = b.agency_id
                WHERE br.competitor_id = :cid
                  AND b.bid_open_date >= :cutoff
                GROUP BY a.name
                ORDER BY win_cnt DESC, bid_cnt DESC
                LIMIT :top
            """), {"cid": comp_id, "cutoff": cutoff_2y, "top": _TOP_AGENCIES}).fetchall()

            top_agencies = [r[0] for r in agency_rows]
            top_agency_win_rates = [
                round(r[2] / r[1], 4) if r[1] > 0 else 0.0
                for r in agency_rows
            ]

            # 강점 기관: 낙찰률 30% 초과 기관 (회피 전략 대상)
            risk_agencies = [
                r[0] for r in agency_rows
                if r[1] >= 3 and r[2] / r[1] >= 0.30
            ]

            # 2년 실적 집계
            stat_row = db.execute(text("""
                SELECT COUNT(*) AS bid_cnt,
                       SUM(CASE WHEN br.is_winner THEN 1 ELSE 0 END) AS win_cnt,
                       SUM(CASE WHEN br.is_winner THEN br.bid_amount ELSE 0 END) AS win_amt
                FROM bid_results br
                JOIN bids b ON b.id = br.bid_id
                WHERE br.competitor_id = :cid
                  AND b.bid_open_date >= :cutoff
            """), {"cid": comp_id, "cutoff": cutoff_2y}).fetchone()

            bid_count_2y = int(stat_row[0] or 0)
            win_count_2y = int(stat_row[1] or 0)
            win_amount_2y = int(stat_row[2] or 0)

            # KISCON 프로필 데이터
            kp = kiscon_profiles.get(biz_reg_no)
            now = datetime.now(timezone.utc)

            upsert_data = {
                "competitor_id":     comp_id,
                "biz_reg_no":        biz_reg_no,
                "corp_name":         (kp.corp_name if kp else comp_name),
                "eval_year":         (kp.eval_year if kp else None),
                "license_types":     (kp.license_types if kp else []),
                "license_names":     (kp.license_names if kp else []),
                "capacity_eval_amount": (kp.capacity_eval_amount if kp else None),
                "main_biz_type":     (kp.main_biz_type if kp else None),
                "top_agencies":      top_agencies,
                "top_agency_win_rates": top_agency_win_rates,
                "risk_agencies":     risk_agencies,
                "bid_count_2y":      bid_count_2y,
                "win_count_2y":      win_count_2y,
                "win_amount_2y":     win_amount_2y,
                "stats_updated_at":  now,
                "kiscon_fetched_at": now if kp else None,
            }

            db.execute(text("""
                INSERT INTO competitor_kiscon_profiles (
                    competitor_id, biz_reg_no, corp_name, eval_year,
                    license_types, license_names, capacity_eval_amount, main_biz_type,
                    top_agencies, top_agency_win_rates, risk_agencies,
                    bid_count_2y, win_count_2y, win_amount_2y,
                    stats_updated_at, kiscon_fetched_at
                ) VALUES (
                    :competitor_id, :biz_reg_no, :corp_name, :eval_year,
                    :license_types, :license_names, :capacity_eval_amount, :main_biz_type,
                    :top_agencies, :top_agency_win_rates, :risk_agencies,
                    :bid_count_2y, :win_count_2y, :win_amount_2y,
                    :stats_updated_at, :kiscon_fetched_at
                )
                ON CONFLICT (competitor_id) DO UPDATE SET
                    biz_reg_no           = EXCLUDED.biz_reg_no,
                    corp_name            = EXCLUDED.corp_name,
                    eval_year            = COALESCE(EXCLUDED.eval_year, competitor_kiscon_profiles.eval_year),
                    license_types        = CASE WHEN EXCLUDED.kiscon_fetched_at IS NOT NULL
                                               THEN EXCLUDED.license_types
                                               ELSE competitor_kiscon_profiles.license_types END,
                    license_names        = CASE WHEN EXCLUDED.kiscon_fetched_at IS NOT NULL
                                               THEN EXCLUDED.license_names
                                               ELSE competitor_kiscon_profiles.license_names END,
                    capacity_eval_amount = COALESCE(EXCLUDED.capacity_eval_amount, competitor_kiscon_profiles.capacity_eval_amount),
                    main_biz_type        = COALESCE(EXCLUDED.main_biz_type, competitor_kiscon_profiles.main_biz_type),
                    top_agencies         = EXCLUDED.top_agencies,
                    top_agency_win_rates = EXCLUDED.top_agency_win_rates,
                    risk_agencies        = EXCLUDED.risk_agencies,
                    bid_count_2y         = EXCLUDED.bid_count_2y,
                    win_count_2y         = EXCLUDED.win_count_2y,
                    win_amount_2y        = EXCLUDED.win_amount_2y,
                    stats_updated_at     = EXCLUDED.stats_updated_at,
                    kiscon_fetched_at    = COALESCE(EXCLUDED.kiscon_fetched_at, competitor_kiscon_profiles.kiscon_fetched_at)
            """), upsert_data)

            db.commit()
            stats_updated += 1

        except Exception as exc:
            db.rollback()
            logger.warning("KISCON 프로필 저장 실패 [competitor_id=%d]: %s", comp_id, exc)

    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    result = {
        "total": len(rows),
        "kiscon_fetched": kiscon_fetched,
        "stats_updated": stats_updated,
        "elapsed_s": round(elapsed, 1),
    }
    logger.info("KISCON 프로필 수집 완료: %s", result)
    return result


def get_kiscon_profile(db: Session, competitor_id: int) -> dict | None:
    """단건 경쟁사 KISCON 프로필 조회."""
    row = db.execute(text("""
        SELECT
            kp.competitor_id, kp.biz_reg_no, kp.corp_name, kp.eval_year,
            kp.license_types, kp.license_names, kp.capacity_eval_amount, kp.main_biz_type,
            kp.top_agencies, kp.top_agency_win_rates, kp.risk_agencies,
            kp.bid_count_2y, kp.win_count_2y, kp.win_amount_2y,
            kp.stats_updated_at, kp.kiscon_fetched_at
        FROM competitor_kiscon_profiles kp
        WHERE kp.competitor_id = :cid
    """), {"cid": competitor_id}).fetchone()

    if not row:
        return None

    win_rate_2y = round(row[12] / row[11], 4) if row[11] and row[11] > 0 else 0.0

    return {
        "competitor_id":       row[0],
        "biz_reg_no":          row[1],
        "corp_name":           row[2],
        "eval_year":           row[3],
        "license_types":       row[4] or [],
        "license_names":       row[5] or [],
        "capacity_eval_amount": row[6],
        "capacity_eval_억":     round(row[6] / 1e8, 1) if row[6] else None,
        "main_biz_type":       row[7],
        "top_agencies":        row[8] or [],
        "top_agency_win_rates": row[9] or [],
        "risk_agencies":       row[10] or [],
        "bid_count_2y":        row[11] or 0,
        "win_count_2y":        row[12] or 0,
        "win_rate_2y":         win_rate_2y,
        "win_amount_2y":       row[13] or 0,
        "stats_updated_at":    row[14].isoformat() if row[14] else None,
        "kiscon_fetched_at":   row[15].isoformat() if row[15] else None,
        "has_kiscon_data":     row[15] is not None,
    }

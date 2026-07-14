"""경쟁사 실적 프로필 수집 서비스 (bid_results 자체 집계 기반)

외부 API 없이 이미 수집된 bid_results + bids 데이터를 집계한다.
- 면허 업종: 참여 공고의 industry_id 분포에서 역추론
- 주력 발주기관: 낙찰 건수·낙찰률 상위 기관
- 최근 2년 실적: 투찰/낙찰 건수·금액
- 강점 기관: 낙찰률 30%+ 기관 (회피 전략 대상)
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_STATS_YEARS = 2
_TOP_AGENCIES = 5
_TOP_INDUSTRIES = 5


def collect_kiscon_profiles(
    db: Session,
    limit: int = 300,
    force_refresh: bool = False,
) -> dict:
    """
    경쟁사 실적 프로필 수집 및 업데이트.

    Returns:
        {"total": int, "stats_updated": int, "elapsed_s": float}
    """
    t0 = datetime.now(timezone.utc)
    cutoff_refresh = datetime.now(timezone.utc) - timedelta(days=30)

    condition = "" if force_refresh else (
        "AND (kp.stats_updated_at IS NULL OR kp.stats_updated_at < :cutoff)"
    )
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
    """), {"cutoff": cutoff_refresh, "limit": limit}).fetchall()

    if not rows:
        logger.info("KISCON 수집 대상 없음")
        return {"total": 0, "stats_updated": 0, "elapsed_s": 0.0}

    logger.info("경쟁사 실적 프로필 수집 대상: %d개사", len(rows))

    cutoff_2y = datetime.now(timezone.utc) - timedelta(days=365 * _STATS_YEARS)
    stats_updated = 0

    for comp_id, biz_reg_no, comp_name in rows:
        try:
            # ① 주력 발주기관 (낙찰 우선, bid_count 보조)
            agency_rows = db.execute(text("""
                SELECT a.name,
                       COUNT(*)                                            AS bid_cnt,
                       SUM(CASE WHEN br.is_winner THEN 1 ELSE 0 END)      AS win_cnt
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
            # 낙찰률 30%+ & 최소 3건 = 강점 기관
            risk_agencies = [
                r[0] for r in agency_rows
                if r[1] >= 3 and r[2] / r[1] >= 0.30
            ]

            # ② 면허 업종 역추론 (참여 공고의 industry 분포)
            industry_rows = db.execute(text("""
                SELECT i.code, i.name, COUNT(*) AS bid_cnt
                FROM bid_results br
                JOIN bids b ON b.id = br.bid_id
                JOIN industries i ON i.id = b.industry_id
                WHERE br.competitor_id = :cid
                  AND b.industry_id IS NOT NULL
                GROUP BY i.code, i.name
                ORDER BY bid_cnt DESC
                LIMIT :top
            """), {"cid": comp_id, "top": _TOP_INDUSTRIES}).fetchall()

            license_types = [r[0] for r in industry_rows]   # 업종코드
            license_names = [r[1] for r in industry_rows]   # 업종명
            main_biz_type = license_names[0] if license_names else None

            # ③ 2년 실적 집계
            stat_row = db.execute(text("""
                SELECT COUNT(*),
                       SUM(CASE WHEN br.is_winner THEN 1 ELSE 0 END),
                       SUM(CASE WHEN br.is_winner THEN br.bid_amount ELSE 0 END)
                FROM bid_results br
                JOIN bids b ON b.id = br.bid_id
                WHERE br.competitor_id = :cid
                  AND b.bid_open_date >= :cutoff
            """), {"cid": comp_id, "cutoff": cutoff_2y}).fetchone()

            bid_count_2y  = int(stat_row[0] or 0)
            win_count_2y  = int(stat_row[1] or 0)
            win_amount_2y = int(stat_row[2] or 0)

            now = datetime.now(timezone.utc)

            db.execute(text("""
                INSERT INTO competitor_kiscon_profiles (
                    competitor_id, biz_reg_no, corp_name,
                    license_types, license_names, main_biz_type,
                    top_agencies, top_agency_win_rates, risk_agencies,
                    bid_count_2y, win_count_2y, win_amount_2y,
                    stats_updated_at
                ) VALUES (
                    :competitor_id, :biz_reg_no, :corp_name,
                    :license_types, :license_names, :main_biz_type,
                    :top_agencies, :top_agency_win_rates, :risk_agencies,
                    :bid_count_2y, :win_count_2y, :win_amount_2y,
                    :now
                )
                ON CONFLICT (competitor_id) DO UPDATE SET
                    biz_reg_no           = EXCLUDED.biz_reg_no,
                    corp_name            = EXCLUDED.corp_name,
                    license_types        = EXCLUDED.license_types,
                    license_names        = EXCLUDED.license_names,
                    main_biz_type        = EXCLUDED.main_biz_type,
                    top_agencies         = EXCLUDED.top_agencies,
                    top_agency_win_rates = EXCLUDED.top_agency_win_rates,
                    risk_agencies        = EXCLUDED.risk_agencies,
                    bid_count_2y         = EXCLUDED.bid_count_2y,
                    win_count_2y         = EXCLUDED.win_count_2y,
                    win_amount_2y        = EXCLUDED.win_amount_2y,
                    stats_updated_at     = EXCLUDED.stats_updated_at
            """), {
                "competitor_id":      comp_id,
                "biz_reg_no":         biz_reg_no,
                "corp_name":          comp_name,
                "license_types":      license_types,
                "license_names":      license_names,
                "main_biz_type":      main_biz_type,
                "top_agencies":       top_agencies,
                "top_agency_win_rates": top_agency_win_rates,
                "risk_agencies":      risk_agencies,
                "bid_count_2y":       bid_count_2y,
                "win_count_2y":       win_count_2y,
                "win_amount_2y":      win_amount_2y,
                "now":                now,
            })
            db.commit()
            stats_updated += 1

        except Exception as exc:
            db.rollback()
            logger.warning("실적 프로필 저장 실패 [competitor_id=%d]: %s", comp_id, exc)

    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    result = {
        "total": len(rows),
        "stats_updated": stats_updated,
        "elapsed_s": round(elapsed, 1),
    }
    logger.info("경쟁사 실적 프로필 수집 완료: %s", result)
    return result


def get_kiscon_profile(db: Session, competitor_id: int) -> dict | None:
    """단건 경쟁사 실적 프로필 조회."""
    row = db.execute(text("""
        SELECT competitor_id, biz_reg_no, corp_name,
               license_types, license_names, main_biz_type,
               top_agencies, top_agency_win_rates, risk_agencies,
               bid_count_2y, win_count_2y, win_amount_2y,
               stats_updated_at
        FROM competitor_kiscon_profiles
        WHERE competitor_id = :cid
    """), {"cid": competitor_id}).fetchone()

    if not row:
        return None

    win_rate_2y = round(row[10] / row[9], 4) if row[9] and row[9] > 0 else 0.0

    return {
        "competitor_id":        row[0],
        "biz_reg_no":           row[1],
        "corp_name":            row[2],
        "license_types":        row[3] or [],
        "license_names":        row[4] or [],
        "main_biz_type":        row[5],
        "top_agencies":         row[6] or [],
        "top_agency_win_rates": row[7] or [],
        "risk_agencies":        row[8] or [],
        "bid_count_2y":         row[9] or 0,
        "win_count_2y":         row[10] or 0,
        "win_rate_2y":          win_rate_2y,
        "win_amount_2y":        row[11] or 0,
        "stats_updated_at":     row[12].isoformat() if row[12] else None,
    }

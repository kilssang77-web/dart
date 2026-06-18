"""
경쟁사 서비스
"""
import io
import re
import math
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import text, func, and_, or_, desc

from ..models import (
    Bid, BidResult, Competitor, Agency, Industry, Region,
    FeatureStore, PredictionLog, PredictionLogV2, CompetitorStat, User, AuditLog,
    IndustryFilter, BidBookmark, CollectionLog, MyBidRecord, Notification,
    BidExecution, DefeatAnalysis, AgencyStrategy, RateFrequencyTable, OurCompetitor,
    ActualBidOutcome, ModelPerformanceLog, BidJournal,
)
from ..schemas import (
    BidCreate, BidResultCreate, RecommendRequest, RecommendResponse,
    RateRange, WinProbabilities, Explanation, ExplanationFactor, RiskInfo,
    SimilarCase, BidSummary, BidDetail, BidResultOut, CompetitorDetail
)
from ..ml.engine import build_features, get_engine, FEATURE_LABELS
from ..ml.assessment  import load_srate_stats, predict_srate, compute_market_trend
from ..ml.competition import compute_competition_features, get_competitor_profiles, get_market_competitor_distributions
from ..ml.simulation  import recommend_with_simulation, simulate_yejung_from_real, simulate_yejung, scan_zones_from_dist
from ..ml.rank_model  import get_inpo_raw_rates
from ..ml.personal    import PersonalBiasAnalyzer
from ..ml.prism       import scan_prism_zones
from ..ml.yega        import calc_yega_frequency, get_inpo21c_pattern_direct, load_inpo21c_yega_stats
from ..ml.a_value     import calc_floor_rate

from ._common import get_active_industry_ids, _build_ind_sql, _compute_yega_ml_features

logger = logging.getLogger(__name__)

class CompetitorService:

    def list_competitors(self, db: Session, keyword=None, page=1, size=20, risk_level=None) -> dict:
        active_ids = get_active_industry_ids(db)
        q = db.query(Competitor)
        if keyword:
            q = q.filter(Competitor.name.ilike(f"%{keyword}%"))

        # 활성 공종 기준: 해당 공종 입찰에 참여한 경쟁사만 포함
        if active_ids is not None:
            if not active_ids:
                return {"items": [], "total": 0, "page": page, "size": size}
            ids_str = ",".join(map(str, active_ids))
            sub = db.execute(text(
                f"SELECT DISTINCT competitor_id FROM bid_results r "
                f"JOIN bids b ON b.id = r.bid_id WHERE b.industry_id IN ({ids_str})"
            )).scalars().all()
            q = q.filter(Competitor.id.in_(sub))

        if risk_level and risk_level.upper() in ("HIGH", "MEDIUM", "LOW"):
            all_comps = q.all()
            filtered = []
            for c in all_comps:
                summary = self._summarize(db, c, active_ids)
                if summary["risk_level"] == risk_level.upper():
                    filtered.append(summary)
            total = len(filtered)
            items = filtered[(page-1)*size : page*size]
        else:
            total = q.count()
            comps = q.offset((page-1)*size).limit(size).all()
            items = [self._summarize(db, c, active_ids) for c in comps]

        return {"items": items, "total": total, "page": page, "size": size}

    def get_detail(self, db: Session, competitor_id: int) -> Optional[dict]:
        c = db.query(Competitor).filter(Competitor.id == competitor_id).first()
        if not c:
            return None
        active_ids = get_active_industry_ids(db)
        summary = self._summarize(db, c, active_ids)
        summary["frequent_rivals"] = self._frequent_rivals(db, competitor_id, active_ids=active_ids)
        summary["monthly_trend"]   = self._monthly_trend(db, competitor_id, active_ids=active_ids)
        return summary

    def _summarize(self, db: Session, c: Competitor, active_ids=None) -> dict:
        q = db.query(BidResult).filter(BidResult.competitor_id == c.id)
        if active_ids is not None:
            if not active_ids:
                return {
                    "id": c.id, "name": c.name, "total_bids": 0,
                    "win_count": 0, "win_rate": 0.0, "avg_bid_rate": 0.0,
                    "std_bid_rate": 0.0, "p25_rate": 0.0, "p75_rate": 0.0,
                    "aggression_score": 0.0, "consistency_score": 0.0,
                    "risk_level": "UNKNOWN",
                }
            q = q.join(Bid, Bid.id == BidResult.bid_id).filter(Bid.industry_id.in_(active_ids))
        results = q.all()
        if not results:
            return {
                "id": c.id, "name": c.name, "total_bids": 0,
                "win_count": 0, "win_rate": 0.0, "avg_bid_rate": 0.0,
                "std_bid_rate": 0.0, "p25_rate": 0.0, "p75_rate": 0.0,
                "aggression_score": 0.0, "consistency_score": 0.0,
                "risk_level": "UNKNOWN",
            }
        rates = np.array([float(r.bid_rate) for r in results])
        wins  = [r for r in results if r.is_winner]
        agg   = float(np.mean(rates < 0.88) * 10)
        cv    = (rates.std() / rates.mean() * 100) if rates.mean() > 0 else 10
        cons  = max(0.0, 10.0 - cv)

        risk_score = agg * 0.4 + (len(wins)/len(results)*10) * 0.4 + cons * 0.2
        risk = "LOW" if risk_score < 3 else "MEDIUM" if risk_score < 6 else "HIGH"

        return {
            "id": c.id, "name": c.name,
            "total_bids":        len(results),
            "win_count":         len(wins),
            "win_rate":          round(len(wins)/len(results), 4),
            "avg_bid_rate":      round(float(rates.mean()), 4),
            "std_bid_rate":      round(float(rates.std()), 4),
            "p25_rate":          round(float(np.percentile(rates,25)), 4),
            "p75_rate":          round(float(np.percentile(rates,75)), 4),
            "aggression_score":  round(agg, 2),
            "consistency_score": round(cons, 2),
            "risk_level":        risk,
        }

    def _frequent_rivals(self, db: Session, competitor_id: int, top_k: int = 8, active_ids=None) -> List[dict]:
        ind_sql = _build_ind_sql(active_ids)
        rows = db.execute(text(f"""
            SELECT c2.competitor_id, comp.name, COUNT(*) as co_count
            FROM bid_results c1
            JOIN bid_results c2 ON c1.bid_id = c2.bid_id AND c1.competitor_id != c2.competitor_id
            JOIN competitors comp ON comp.id = c2.competitor_id
            JOIN bids b ON b.id = c1.bid_id
            WHERE c1.competitor_id = :cid {ind_sql}
            GROUP BY c2.competitor_id, comp.name
            ORDER BY co_count DESC
            LIMIT :k
        """), {"cid": competitor_id, "k": top_k}).fetchall()
        return [{"competitor_id": r[0], "name": r[1], "co_occurrence": r[2]} for r in rows]

    def _monthly_trend(self, db: Session, competitor_id: int, months: int = 12, active_ids=None) -> List[dict]:
        cutoff = datetime.now() - timedelta(days=months * 30)
        ind_sql = _build_ind_sql(active_ids)
        rows = db.execute(text(f"""
            SELECT EXTRACT(YEAR FROM b.bid_open_date)::int  AS yr,
                   EXTRACT(MONTH FROM b.bid_open_date)::int AS mo,
                   COUNT(*)           AS bid_count,
                   SUM(r.is_winner::int) AS win_count,
                   AVG(r.bid_rate)    AS avg_rate
            FROM bid_results r
            JOIN bids b ON b.id = r.bid_id
            WHERE r.competitor_id = :cid
              AND b.bid_open_date >= :cutoff {ind_sql}
            GROUP BY yr, mo
            ORDER BY yr, mo
        """), {"cid": competitor_id, "cutoff": cutoff}).fetchall()
        return [
            {"year": r[0], "month": r[1], "bid_count": r[2],
             "win_count": r[3], "avg_rate": round(float(r[4]), 4) if r[4] else None}
            for r in rows
        ]

    def get_win_history(self, db: Session, competitor_id: int, limit: int = 50) -> List[dict]:
        ind_sql = _build_ind_sql(get_active_industry_ids(db))
        rows = db.execute(text(f"""
            SELECT r.id, b.id AS bid_id, b.title, a.name AS agency_name,
                   b.base_amount, b.bid_open_date,
                   r.bid_amount, r.bid_rate, r.rank
            FROM bid_results r
            JOIN bids b ON b.id = r.bid_id
            LEFT JOIN agencies a ON a.id = b.agency_id
            WHERE r.competitor_id = :cid AND r.is_winner = true {ind_sql}
            ORDER BY b.bid_open_date DESC
            LIMIT :lim
        """), {"cid": competitor_id, "lim": limit}).fetchall()
        return [
            {
                "result_id":    r[0],
                "bid_id":       r[1],
                "title":        r[2],
                "agency_name":  r[3] or "",
                "base_amount":  r[4],
                "bid_open_date": r[5].isoformat() if r[5] else None,
                "bid_amount":   r[6],
                "bid_rate":     round(float(r[7]), 4) if r[7] else None,
                "rank":         r[8],
            }
            for r in rows
        ]

# --------------------------------------------------
# 통계 서비스
# --------------------------------------------------

class CompetitorPatternService:
    def __init__(self, db: Session):
        self.db = db

    def get_pattern(self, competitor_id: int) -> dict:
        from fastapi import HTTPException
        from collections import Counter
        competitor = self.db.query(Competitor).filter(Competitor.id == competitor_id).first()
        if not competitor:
            raise HTTPException(status_code=404, detail="경쟁사를 찾을 수 없습니다")

        cutoff = datetime.utcnow() - timedelta(days=365)
        results = self.db.query(BidResult).join(Bid, Bid.id == BidResult.bid_id).filter(
            BidResult.competitor_id == competitor_id,
            Bid.bid_open_date >= cutoff
        ).all()

        if not results:
            radar = {"aggression": 0.0, "consistency": 0.0, "concentration": 0.0, "risk": 0.0, "activity": 0.0}
            return {"radar": radar, "amount_pattern": [], "recent_trend": {"direction": "stable", "change_pct": None}}

        rates = [float(r.bid_rate) for r in results if r.bid_rate]
        aggression = len([r for r in rates if r < 87.0]) / len(rates) * 10 if rates else 0
        std_val = float(np.std(rates)) if len(rates) > 1 else 1.0
        consistency = min(10.0, 2.0 / (std_val + 0.01))

        bid_ids = [r.bid_id for r in results]
        bids_data = self.db.query(Bid).filter(Bid.id.in_(bid_ids)).all()
        agency_ids = [b.agency_id for b in bids_data]
        if agency_ids:
            top_count = Counter(agency_ids).most_common(1)[0][1]
            concentration = min(10.0, top_count / len(agency_ids) * 10)
        else:
            concentration = 0.0

        risk = len([r for r in rates if r < 87.745]) / len(rates) * 10 if rates else 0

        monthly_counts = Counter([
            f"{b.bid_open_date.year}-{b.bid_open_date.month:02d}"
            for b in bids_data if b.bid_open_date
        ])
        activity = min(10.0, sum(monthly_counts.values()) / max(len(monthly_counts), 1) * 2)

        radar = {
            "aggression": round(aggression, 2),
            "consistency": round(consistency, 2),
            "concentration": round(concentration, 2),
            "risk": round(risk, 2),
            "activity": round(activity, 2)
        }

        buckets = [
            ("1억 미만", 0, 100_000_000),
            ("1~3억", 100_000_000, 300_000_000),
            ("3~10억", 300_000_000, 1_000_000_000),
            ("10억 이상", 1_000_000_000, float("inf")),
        ]
        bid_map = {b.id: b for b in bids_data}
        amount_pattern = []
        for label, low, high in buckets:
            bucket_results = [r for r in results if r.bid_id in bid_map and bid_map[r.bid_id].base_amount and low <= bid_map[r.bid_id].base_amount < high]
            b_rates = [float(r.bid_rate) for r in bucket_results if r.bid_rate]
            wins = [r for r in bucket_results if r.is_winner]
            amount_pattern.append({
                "bucket": label,
                "bid_count": len(bucket_results),
                "win_count": len(wins),
                "avg_rate": round(sum(b_rates) / len(b_rates), 4) if b_rates else None,
                "win_rate": round(len(wins) / len(bucket_results), 4) if bucket_results else None
            })

        from datetime import timezone as _tz
        six_months_ago = datetime.now(_tz.utc) - timedelta(days=180)
        def _naive(dt): return dt.replace(tzinfo=None) if dt.tzinfo else dt
        recent_bids = [b for b in bids_data if b.bid_open_date and _naive(b.bid_open_date) >= six_months_ago.replace(tzinfo=None)]
        older_bids = [b for b in bids_data if b.bid_open_date and _naive(b.bid_open_date) < six_months_ago.replace(tzinfo=None)]
        recent_ids = {b.id for b in recent_bids}
        older_ids = {b.id for b in older_bids}
        recent_rates = [float(r.bid_rate) for r in results if r.bid_id in recent_ids and r.bid_rate]
        older_rates = [float(r.bid_rate) for r in results if r.bid_id in older_ids and r.bid_rate]
        direction = "stable"
        change_pct = None
        if recent_rates and older_rates:
            r_mean = sum(recent_rates) / len(recent_rates)
            o_mean = sum(older_rates) / len(older_rates)
            change_pct = round((r_mean - o_mean) / o_mean * 100, 2)
            if change_pct < -0.5:
                direction = "aggressive"
            elif change_pct > 0.5:
                direction = "defensive"

        return {
            "radar": radar,
            "amount_pattern": amount_pattern,
            "recent_trend": {"direction": direction, "change_pct": change_pct}
        }

    def compare(self, ids: list) -> dict:
        from collections import defaultdict
        competitors_data = []
        for cid in ids[:2]:
            competitor = self.db.query(Competitor).filter(Competitor.id == cid).first()
            if not competitor:
                continue
            pattern = self.get_pattern(cid)

            cutoff = datetime.utcnow() - timedelta(days=365)
            results = self.db.query(BidResult).join(Bid).filter(
                BidResult.competitor_id == cid, Bid.bid_open_date >= cutoff
            ).all()
            bid_ids = [r.bid_id for r in results]
            bids_data = self.db.query(Bid).filter(Bid.id.in_(bid_ids)).all()
            monthly = defaultdict(lambda: {"bid_count": 0, "win_count": 0, "rates": []})
            for r in results:
                b = next((b for b in bids_data if b.id == r.bid_id), None)
                if b and b.bid_open_date:
                    key = f"{b.bid_open_date.year}-{b.bid_open_date.month:02d}"
                    monthly[key]["bid_count"] += 1
                    if r.is_winner:
                        monthly[key]["win_count"] += 1
                    if r.bid_rate:
                        monthly[key]["rates"].append(float(r.bid_rate))
            trend = [
                {
                    "year_month": k,
                    "bid_count": v["bid_count"],
                    "win_count": v["win_count"],
                    "avg_rate": round(sum(v["rates"]) / len(v["rates"]), 4) if v["rates"] else None
                }
                for k, v in sorted(monthly.items())
            ]
            competitors_data.append({
                "id": competitor.id,
                "name": competitor.name,
                "radar": pattern["radar"],
                "monthly_trend": trend
            })
        return {"competitors": competitors_data}


# ==================================================
# 북마크 서비스
# ==================================================

class CompetitorZoneService:
    BUCKET_SIZE = 0.005
    ZONE_MIN    = 0.800
    ZONE_MAX    = 0.980

    def get_recent_zones(self, db: Session, competitor_id: int, days: int = 90) -> dict:
        from sqlalchemy import text as sa_text
        competitor = db.query(Competitor).filter(Competitor.id == competitor_id).first()
        if not competitor or not competitor.biz_reg_no:
            return self._empty()

        # inpo21c_participants에 date 컬럼 없으므로 전체 조회 (days 파라미터는 API 호환용)
        rows = db.execute(sa_text("""
            SELECT base_ratio::float
            FROM inpo21c_participants
            WHERE biz_reg_no = :biz_reg_no
              AND base_ratio IS NOT NULL
              AND base_ratio BETWEEN :lo AND :hi
        """), {
            "biz_reg_no": competitor.biz_reg_no,
            "lo": self.ZONE_MIN,
            "hi": self.ZONE_MAX,
        }).fetchall()

        if not rows:
            return self._empty()

        total = len(rows)
        bucket_counts: dict[float, int] = {}
        for (ratio,) in rows:
            key = round(math.floor(ratio / self.BUCKET_SIZE) * self.BUCKET_SIZE, 3)
            bucket_counts[key] = bucket_counts.get(key, 0) + 1

        zones = [
            {
                "range_lo": lo,
                "range_hi": round(lo + self.BUCKET_SIZE, 3),
                "count":    cnt,
                "pct":      round(cnt / total * 100, 1),
            }
            for lo, cnt in sorted(bucket_counts.items())
        ]
        peak_zone = max(zones, key=lambda z: z["count"]) if zones else None

        return {
            "zones":       zones,
            "peak_zone":   peak_zone,
            "total_count": total,
            "last_updated": None,
        }

    def _empty(self) -> dict:
        return {"zones": [], "peak_zone": None, "total_count": 0, "last_updated": None}


# ==================================================
# ⑦-2 경쟁사 행동 예측 서비스
# ==================================================

class CompetitorPredictService:
    """inpo21c 데이터 기반 경쟁사 참여 확률 + 투찰 구간 예측."""

    def predict(self, db: Session, competitor_id: int, bid_id: int) -> dict:
        from fastapi import HTTPException
        from ..ml.competitor_predict import predict_participation, predict_bid_zone

        competitor = db.query(Competitor).filter(Competitor.id == competitor_id).first()
        if not competitor:
            raise HTTPException(status_code=404, detail="경쟁사를 찾을 수 없습니다.")

        bid = db.query(Bid).filter(Bid.id == bid_id).first()
        if not bid:
            raise HTTPException(status_code=404, detail="공고를 찾을 수 없습니다.")

        bid_dict = {
            "agency_id":   bid.agency_id,
            "industry_id": bid.industry_id,
            "base_amount": bid.base_amount,
        }

        participation = predict_participation(competitor_id, bid_dict, db)
        bid_zone      = predict_bid_zone(competitor_id, bid.base_amount, db)

        return {
            "competitor_id":   competitor_id,
            "competitor_name": competitor.name,
            "bid_id":          bid_id,
            "participation":   participation,
            "bid_zone":        bid_zone,
        }


# ==================================================
# ⑧ 공고 자동 평가 점수 서비스
# ==================================================

class OurCompetitorService:
    """자사가 자주 만나는 경쟁사 목록 관리"""

    def __init__(self, db: Session):
        self.db = db

    def list_competitors(self, limit: int = 30) -> list:
        rows = (
            self.db.query(OurCompetitor)
            .order_by(OurCompetitor.co_participation_cnt.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "company_name": r.company_name,
                "biz_reg_no": r.biz_reg_no,
                "co_participation_cnt": r.co_participation_cnt,
                "co_win_cnt": r.co_win_cnt,
                "our_win_when_meet": r.our_win_when_meet,
                "avg_bid_rate": float(r.avg_bid_rate) if r.avg_bid_rate else None,
                "aggression": float(r.aggression) if r.aggression else None,
                "last_seen_at": str(r.last_seen_at) if r.last_seen_at else None,
                "last_seen_agency": r.last_seen_agency,
                "is_primary_rival": r.is_primary_rival,
            }
            for r in rows
        ]


# ==================================================
# 백테스트 엔진
# ==================================================

class RivalRadarService:
    """inpo21c_participants 기반 동반 입찰 경쟁사 레이더."""

    def get(self, db: Session, bid_id: int, top_k: int = 15) -> dict:
        bid = db.query(Bid).filter(Bid.id == bid_id).first()
        if not bid or not bid.announcement_no:
            return {
                "rivals": [], "bid_id": bid_id,
                "total_participants": 0, "winner_company": None,
                "winner_rate": None, "current_participants": [],
            }

        # 이 공고에 참여한 업체들
        participants = db.execute(text("""
            SELECT ip.company_name, ip.biz_reg_no, ip.bid_rate, ip.rank, ip.is_winner
            FROM inpo21c_participants ip
            JOIN inpo21c_bids ib USING (inpo21c_bid_id)
            WHERE ib.announcement_no LIKE :ano
            ORDER BY ip.rank
        """), {"ano": bid.announcement_no + "%"}).fetchall()

        if not participants:
            return {
                "rivals": [], "bid_id": bid_id,
                "announcement_no": bid.announcement_no,
                "total_participants": 0, "winner_company": None,
                "winner_rate": None, "current_participants": [],
            }

        # 같은 업체들이 함께 참여한 다른 공고 수 (동반 빈도)
        biz_nos = [r[1] for r in participants if r[1]]
        if not biz_nos:
            company_names = [r[0] for r in participants if r[0]]
            freq_rows = db.execute(text("""
                SELECT ip2.company_name, COUNT(DISTINCT ib2.inpo21c_bid_id) as co_count,
                       AVG(ip2.bid_rate::numeric) as avg_rate,
                       SUM(CASE WHEN ip2.is_winner THEN 1 ELSE 0 END) as win_count
                FROM inpo21c_participants ip2
                JOIN inpo21c_bids ib2 USING (inpo21c_bid_id)
                WHERE ip2.company_name = ANY(:names)
                  AND ib2.announcement_no NOT LIKE :ano
                  AND ib2.agency_name = :agency
                GROUP BY ip2.company_name
                ORDER BY co_count DESC
                LIMIT :k
            """), {
                "names": company_names,
                "ano": bid.announcement_no + "%",
                "agency": bid.agency.name if bid.agency else "",
                "k": top_k,
            }).fetchall()
        else:
            freq_rows = db.execute(text("""
                SELECT ip2.company_name, COUNT(DISTINCT ib2.inpo21c_bid_id) as co_count,
                       AVG(ip2.bid_rate::numeric) as avg_rate,
                       SUM(CASE WHEN ip2.is_winner THEN 1 ELSE 0 END) as win_count
                FROM inpo21c_participants ip2
                JOIN inpo21c_bids ib2 USING (inpo21c_bid_id)
                WHERE ip2.biz_reg_no = ANY(:nos)
                  AND ib2.announcement_no NOT LIKE :ano
                GROUP BY ip2.company_name
                ORDER BY co_count DESC
                LIMIT :k
            """), {
                "nos": biz_nos,
                "ano": bid.announcement_no + "%",
                "k": top_k,
            }).fetchall()

        rival_names = [r[0] for r in freq_rows if r[0]]
        comp_id_lookup: dict = {}
        if rival_names:
            comp_id_rows = db.execute(text(
                "SELECT name, id FROM competitors WHERE name = ANY(:names)"
            ), {"names": rival_names}).fetchall()
            comp_id_lookup = {row[0]: row[1] for row in comp_id_rows}

        rivals = [
            {
                "company_name":  r[0],
                "co_bid_count":  int(r[1]),
                "avg_bid_rate":  float(r[2]) if r[2] else None,
                "win_count":     int(r[3]),
                "competitor_id": comp_id_lookup.get(r[0]),
            }
            for r in freq_rows
        ]

        winner = next((r for r in participants if r[4]), None)
        return {
            "bid_id": bid_id,
            "announcement_no": bid.announcement_no,
            "total_participants": len(participants),
            "winner_company": winner[0] if winner else None,
            "winner_rate":    float(winner[2]) if winner and winner[2] else None,
            "rivals": rivals,
            "current_participants": [
                {"rank": r[3], "company_name": r[0], "bid_rate": float(r[2]) if r[2] else None, "is_winner": bool(r[4])}
                for r in participants[:20]
            ],
        }


# ==================================================
# 실측 낙찰 구간 서비스 — inpo21c 기반 실측 분포
# ==================================================

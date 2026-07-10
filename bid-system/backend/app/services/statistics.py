"""
통계 서비스
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

class StatisticsService:

    def overview(self, db: Session, months: int = 12) -> dict:
        from ..common.cache import get_redis, cache_get, cache_set

        active_ids = get_active_industry_ids(db)
        if active_ids is not None and not active_ids:
            return {"total_bids": 0, "total_competitors": 0, "avg_win_rate": 0, "avg_bid_rate": 0, "avg_competitor_count": 0, "monthly_trend": [],
                    "win_rate_change_pct": None, "bid_count_change_pct": None, "avg_competitors_change": None}

        ids_key = "all" if active_ids is None else "_".join(str(i) for i in sorted(active_ids))
        rc = get_redis()
        cache_key = f"stats:overview:{months}:{ids_key}"
        cached = cache_get(rc, cache_key)
        if cached is not None:
            return cached

        cutoff = datetime.now() - timedelta(days=months * 30)
        ind_sql = _build_ind_sql(active_ids)

        bids_q = db.query(func.count(Bid.id)).filter(Bid.bid_open_date >= cutoff)
        if active_ids is not None:
            bids_q = bids_q.filter(Bid.industry_id.in_(active_ids))
        total_bids = bids_q.scalar() or 0
        total_comps = db.query(func.count(Competitor.id)).scalar() or 0

        avg_rate_row = db.execute(text(f"""
            SELECT AVG(r.bid_rate)
            FROM bid_results r
            JOIN bids b ON b.id = r.bid_id
            WHERE r.is_winner = true AND b.bid_open_date >= :cutoff {ind_sql}
        """), {"cutoff": cutoff}).fetchone()
        avg_win_rate = float(avg_rate_row[0]) if avg_rate_row and avg_rate_row[0] else 0.0

        all_rate_row = db.execute(text(f"""
            SELECT AVG(r.bid_rate)
            FROM bid_results r
            JOIN bids b ON b.id = r.bid_id
            WHERE b.bid_open_date >= :cutoff {ind_sql}
        """), {"cutoff": cutoff}).fetchone()
        avg_bid_rate = float(all_rate_row[0]) if all_rate_row and all_rate_row[0] else 0.0

        comp_cnt_row = db.execute(text(f"""
            SELECT AVG(cnt)
            FROM (SELECT bid_id, COUNT(*) as cnt FROM bid_results
                  JOIN bids b ON b.id = bid_results.bid_id
                  WHERE b.bid_open_date >= :cutoff {ind_sql}
                  GROUP BY bid_id) sub
        """), {"cutoff": cutoff}).fetchone()
        avg_comp_count = float(comp_cnt_row[0]) if comp_cnt_row and comp_cnt_row[0] else 0.0

        trend = self._monthly_trend(db, cutoff, ind_sql)

        # ── 전월 대비 변화율 계산 ──
        now = datetime.now()
        this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_end = this_month_start - timedelta(seconds=1)
        last_month_start = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        def _get_month_stats(start, end):
            bids_m_q = db.query(func.count(Bid.id)).filter(
                Bid.bid_open_date >= start, Bid.bid_open_date <= end
            )
            if active_ids is not None and active_ids:
                bids_m_q = bids_m_q.filter(Bid.industry_id.in_(active_ids))
            bid_count = bids_m_q.scalar() or 0

            wr_row = db.execute(text(f"""
                SELECT AVG(r.bid_rate)
                FROM bid_results r JOIN bids b ON b.id = r.bid_id
                WHERE r.is_winner = true AND b.bid_open_date >= :s AND b.bid_open_date <= :e {ind_sql}
            """), {"s": start, "e": end}).fetchone()
            win_rate = float(wr_row[0]) if wr_row and wr_row[0] else None

            cc_row = db.execute(text(f"""
                SELECT AVG(cnt) FROM (
                    SELECT bid_id, COUNT(*) as cnt FROM bid_results
                    JOIN bids b ON b.id = bid_results.bid_id
                    WHERE b.bid_open_date >= :s AND b.bid_open_date <= :e {ind_sql}
                    GROUP BY bid_id
                ) sub
            """), {"s": start, "e": end}).fetchone()
            avg_comp = float(cc_row[0]) if cc_row and cc_row[0] else None

            return {"bid_count": bid_count, "win_rate": win_rate, "avg_comp": avg_comp}

        this_m = _get_month_stats(this_month_start, now)
        last_m = _get_month_stats(last_month_start, last_month_end)

        def _pct_change(curr, prev):
            if curr is None or prev is None or prev == 0:
                return None
            return round((curr - prev) / prev * 100, 2)

        win_rate_change_pct = _pct_change(this_m["win_rate"], last_m["win_rate"])
        bid_count_change_pct = _pct_change(this_m["bid_count"], last_m["bid_count"])
        avg_competitors_change = (
            round(this_m["avg_comp"] - last_m["avg_comp"], 2)
            if this_m["avg_comp"] is not None and last_m["avg_comp"] is not None
            else None
        )

        result = {
            "total_bids": total_bids,
            "total_competitors": total_comps,
            "avg_win_rate": round(avg_win_rate, 4),
            "avg_bid_rate": round(avg_bid_rate, 4),
            "avg_competitor_count": round(avg_comp_count, 1),
            "monthly_trend": trend,
            "win_rate_change_pct": win_rate_change_pct,
            "bid_count_change_pct": bid_count_change_pct,
            "avg_competitors_change": avg_competitors_change,
        }
        cache_set(rc, cache_key, result, ttl=300)
        return result

    def _monthly_trend(self, db: Session, cutoff, ind_sql: str = "") -> List[dict]:
        rows = db.execute(text(f"""
            SELECT EXTRACT(YEAR FROM b.bid_open_date)::int  AS yr,
                   EXTRACT(MONTH FROM b.bid_open_date)::int AS mo,
                   COUNT(DISTINCT b.id)          AS bid_count,
                   AVG(r.bid_rate)               AS avg_rate
            FROM bids b
            LEFT JOIN bid_results r ON r.bid_id = b.id AND r.is_winner = true
            WHERE b.bid_open_date >= :cutoff {ind_sql}
            GROUP BY yr, mo
            ORDER BY yr, mo
        """), {"cutoff": cutoff}).fetchall()
        return [
            {"year": r[0], "month": r[1], "bid_count": r[2],
             "avg_rate": round(float(r[3]), 4) if r[3] else None}
            for r in rows
        ]

    def agency_stats(self, db: Session, months: int = 12) -> List[dict]:
        cutoff = datetime.now() - timedelta(days=months * 30)
        ind_sql = _build_ind_sql(get_active_industry_ids(db))
        rows = db.execute(text(f"""
            SELECT a.id, a.name,
                   COUNT(DISTINCT b.id) AS bid_count,
                   AVG(r.bid_rate)      AS avg_rate,
                   AVG(cnt_sub.cnt)     AS avg_comp
            FROM agencies a
            JOIN bids b ON b.agency_id = a.id
            LEFT JOIN bid_results r ON r.bid_id = b.id AND r.is_winner = true
            LEFT JOIN (
                SELECT bid_id, COUNT(*) as cnt
                FROM bid_results GROUP BY bid_id
            ) cnt_sub ON cnt_sub.bid_id = b.id
            WHERE b.bid_open_date >= :cutoff {ind_sql}
            GROUP BY a.id, a.name
            ORDER BY bid_count DESC
            LIMIT 20
        """), {"cutoff": cutoff}).fetchall()
        return [
            {"agency_id": r[0], "agency_name": r[1],
             "bid_count": r[2],
             "avg_rate":  round(float(r[3]), 4) if r[3] else None,
             "avg_competitor_count": round(float(r[4]), 1) if r[4] else None}
            for r in rows
        ]

    def rate_distribution(self, db: Session, industry_id: int = None, months: int = 12) -> List[dict]:
        cutoff = datetime.now() - timedelta(days=months * 30)
        q_filter = "AND b.industry_id = :iid" if industry_id else _build_ind_sql(get_active_industry_ids(db))
        rows = db.execute(text(f"""
            SELECT FLOOR(r.bid_rate * 1000) / 10 AS rate_pct, COUNT(*) as cnt
            FROM bid_results r
            JOIN bids b ON b.id = r.bid_id
            WHERE b.bid_open_date >= :cutoff {q_filter}
            GROUP BY rate_pct
            ORDER BY rate_pct
        """), {"cutoff": cutoff, "iid": industry_id or 0}).fetchall()
        return [{"rate_pct": float(r[0]), "count": r[1]} for r in rows]

    def heatmap(self, db: Session, months: int = 24) -> List[dict]:
        cutoff = datetime.now() - timedelta(days=months * 30)
        ind_sql = _build_ind_sql(get_active_industry_ids(db))
        rows = db.execute(text(f"""
            SELECT EXTRACT(MONTH FROM b.bid_open_date)::int AS mo,
                   ind.name,
                   AVG(r.bid_rate) AS avg_rate,
                   COUNT(*)        AS cnt
            FROM bids b
            JOIN industries ind ON ind.id = b.industry_id
            JOIN bid_results r  ON r.bid_id = b.id AND r.is_winner = true
            WHERE b.bid_open_date >= :cutoff {ind_sql}
            GROUP BY mo, ind.name
        """), {"cutoff": cutoff}).fetchall()
        return [
            {"month": r[0], "industry": r[1],
             "avg_rate": round(float(r[2]), 4) if r[2] else None,
             "count": r[3]}
            for r in rows
        ]

    def region_stats(self, db: Session, months: int = 12) -> List[dict]:
        cutoff = datetime.now() - timedelta(days=months * 30)
        ind_sql = _build_ind_sql(get_active_industry_ids(db))
        rows = db.execute(text(f"""
            SELECT r.id, r.name,
                   COUNT(DISTINCT b.id)   AS bid_count,
                   AVG(res.bid_rate)      AS avg_rate,
                   SUM(b.base_amount)     AS total_amount
            FROM regions r
            JOIN bids b ON b.region_id = r.id
            LEFT JOIN bid_results res ON res.bid_id = b.id AND res.is_winner = true
            WHERE b.bid_open_date >= :cutoff AND r.parent_id IS NULL {ind_sql}
            GROUP BY r.id, r.name
            ORDER BY bid_count DESC
        """), {"cutoff": cutoff}).fetchall()
        return [
            {
                "region_id":   r[0], "region_name": r[1],
                "bid_count":   r[2],
                "avg_rate":    round(float(r[3]), 4) if r[3] else None,
                "total_amount": int(r[4]) if r[4] else 0,
            }
            for r in rows
        ]

    def industry_stats(self, db: Session, months: int = 12) -> List[dict]:
        cutoff = datetime.now() - timedelta(days=months * 30)
        ind_sql = _build_ind_sql(get_active_industry_ids(db), alias="b")
        rows = db.execute(text(f"""
            SELECT ind.id, ind.name,
                   COUNT(DISTINCT b.id)   AS bid_count,
                   AVG(res.bid_rate)      AS avg_rate,
                   AVG(cnt_sub.cnt)       AS avg_comp,
                   SUM(b.base_amount)     AS total_amount
            FROM industries ind
            JOIN bids b ON b.industry_id = ind.id
            LEFT JOIN bid_results res ON res.bid_id = b.id AND res.is_winner = true
            LEFT JOIN (
                SELECT bid_id, COUNT(*) AS cnt FROM bid_results GROUP BY bid_id
            ) cnt_sub ON cnt_sub.bid_id = b.id
            WHERE b.bid_open_date >= :cutoff {ind_sql}
            GROUP BY ind.id, ind.name
            ORDER BY bid_count DESC
            LIMIT 30
        """), {"cutoff": cutoff}).fetchall()
        return [
            {
                "industry_id":   r[0], "industry_name": r[1],
                "bid_count":     r[2],
                "avg_rate":      round(float(r[3]), 4) if r[3] else None,
                "avg_competitor_count": round(float(r[4]), 1) if r[4] else None,
                "total_amount":  int(r[5]) if r[5] else 0,
            }
            for r in rows
        ]

    def cluster_analysis(self, db: Session, industry_id=None, months: int = 24, k: int = 4) -> dict:
        """유사 입찰 클러스터링 (K-Means)."""
        try:
            from sklearn.cluster import KMeans
            from sklearn.preprocessing import StandardScaler
            from sklearn.impute import SimpleImputer
        except ImportError:
            return {"error": "scikit-learn not available", "clusters": []}

        cutoff = datetime.now() - timedelta(days=months * 30)
        q_filter = "AND b.industry_id = :iid" if industry_id else _build_ind_sql(get_active_industry_ids(db))
        rows = db.execute(text(f"""
            SELECT b.id, b.base_amount, b.industry_id,
                   ind.name AS ind_name,
                   AVG(res.bid_rate)  AS avg_rate,
                   COUNT(res.id)      AS comp_cnt
            FROM bids b
            LEFT JOIN industries ind ON ind.id = b.industry_id
            LEFT JOIN bid_results res ON res.bid_id = b.id
            WHERE b.bid_open_date >= :cutoff AND b.base_amount > 0 {q_filter}
            GROUP BY b.id, b.base_amount, b.industry_id, ind.name
            HAVING COUNT(res.id) > 0
            LIMIT 500
        """), {"cutoff": cutoff, "iid": industry_id or 0}).fetchall()

        if len(rows) < k * 5:
            return {"error": "분석 데이터 부족", "clusters": [], "count": len(rows)}

        X = np.array([
            [math.log10(max(r[1], 1)), float(r[4] or 0.88), float(r[5])]
            for r in rows
        ])
        imp = SimpleImputer(strategy="median")
        X_imp = imp.fit_transform(X)
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_imp)

        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = km.fit_predict(X_scaled)

        clusters = []
        for cid in range(k):
            mask = labels == cid
            cluster_rows = [rows[i] for i in range(len(rows)) if mask[i]]
            amounts = [r[1] for r in cluster_rows]
            rates   = [float(r[4]) for r in cluster_rows if r[4]]
            comps   = [float(r[5]) for r in cluster_rows]
            inds    = {}
            for r in cluster_rows:
                name = r[3] or "기타"
                inds[name] = inds.get(name, 0) + 1
            top_ind = max(inds, key=inds.get) if inds else "기타"
            clusters.append({
                "cluster_id":   cid,
                "count":        int(mask.sum()),
                "avg_amount":   int(np.mean(amounts)),
                "avg_rate":     round(float(np.mean(rates)), 4) if rates else None,
                "avg_comp":     round(float(np.mean(comps)), 1),
                "top_industry": top_ind,
                "amount_range": [int(min(amounts)), int(max(amounts))],
            })
        clusters.sort(key=lambda x: x["avg_amount"])
        if len(clusters) == 4 and all(c["avg_rate"] is not None for c in clusters):
            sorted_by_rate = sorted(range(len(clusters)), key=lambda i: clusters[i]["avg_rate"])
            cluster_labels = [""] * len(clusters)
            cluster_labels[sorted_by_rate[0]]  = "공격형"
            cluster_labels[sorted_by_rate[-1]] = "보수형"
            mid_a, mid_b = sorted_by_rate[1], sorted_by_rate[2]
            if (clusters[mid_a]["avg_comp"] or 0) >= (clusters[mid_b]["avg_comp"] or 0):
                cluster_labels[mid_a] = "중앙집중형"
                cluster_labels[mid_b] = "랜덤형"
            else:
                cluster_labels[mid_b] = "중앙집중형"
                cluster_labels[mid_a] = "랜덤형"
            for i, c in enumerate(clusters):
                c["label"] = cluster_labels[i]
        return {"clusters": clusters, "total_count": len(rows)}

    def srate_distribution_detail(self, db: Session, agency_id=None, industry_id=None, months=24) -> dict:
        from sqlalchemy import func as sqlfunc, cast, Float
        cutoff = datetime.now() - timedelta(days=30 * months)

        # ── 1. assessment_rate_stats 기반 발주처/공종별 통계 (우선)
        agency_stats = industry_stats = global_stats = None
        if agency_id:
            row = db.execute(text("""
                SELECT srate_mean::float, srate_std::float, sample_count,
                       srate_p10::float, srate_p25::float, srate_p50::float,
                       srate_p75::float, srate_p90::float
                FROM assessment_rate_stats
                WHERE group_type='agency' AND group_id=:aid
                ORDER BY updated_at DESC LIMIT 1
            """), {"aid": agency_id}).fetchone()
            if row:
                agency_stats = {
                    "mean": round(row[0], 4), "std": round(row[1], 4),
                    "sample_count": row[2],
                    "p10": round(row[3], 4), "p25": round(row[4], 4),
                    "p50": round(row[5], 4), "p75": round(row[6], 4),
                    "p90": round(row[7], 4),
                }
        if industry_id:
            row = db.execute(text("""
                SELECT srate_mean::float, srate_std::float, sample_count,
                       srate_p25::float, srate_p50::float, srate_p75::float
                FROM assessment_rate_stats
                WHERE group_type='industry' AND group_id=:iid
                ORDER BY updated_at DESC LIMIT 1
            """), {"iid": industry_id}).fetchone()
            if row:
                industry_stats = {
                    "mean": round(row[0], 4), "std": round(row[1], 4),
                    "sample_count": row[2],
                    "p25": round(row[3], 4), "p50": round(row[4], 4), "p75": round(row[5], 4),
                }
        row = db.execute(text("""
            SELECT srate_mean::float, srate_std::float, sample_count,
                   srate_p25::float, srate_p50::float, srate_p75::float
            FROM assessment_rate_stats WHERE group_type='global'
            ORDER BY updated_at DESC LIMIT 1
        """)).fetchone()
        if row:
            global_stats = {
                "mean": round(row[0], 4), "std": round(row[1], 4),
                "sample_count": row[2],
                "p25": round(row[3], 4), "p50": round(row[4], 4), "p75": round(row[5], 4),
            }

        # ── 2. bids.estimated_price 기반 히스토그램 (상세 분포)
        query = db.execute(text("""
            SELECT b.estimated_price::float8 / b.base_amount::float8 AS srate
            FROM bids b
            WHERE b.estimated_price IS NOT NULL
              AND b.base_amount > 0
              AND b.bid_open_date >= :cutoff
              -- 부가세 제외 고정비율(base×10/11≈0.9091) 공고 제거
              AND ABS(b.estimated_price::numeric / NULLIF(b.base_amount,0) - (10.0/11.0)) > 0.002
              AND (:agency_id  IS NULL OR b.agency_id   = :agency_id)
              AND (:industry_id IS NULL OR b.industry_id = :industry_id)
        """), {"cutoff": cutoff, "agency_id": agency_id, "industry_id": industry_id})
        rows = query.fetchall()
        values = [float(r[0]) for r in rows if r[0] and 0.80 <= float(r[0]) <= 1.05]

        # 히스토그램 데이터 생성 (bids 데이터 또는 stats 기반 합성)
        if values:
            arr = np.array(values)
            src_mean = float(np.mean(arr))
            src_std  = float(np.std(arr))
            src_n    = len(values)
        elif agency_stats:
            # bids.estimated_price 없으면 assessment_rate_stats 기반 정규 분포 합성
            src_mean = agency_stats["mean"]
            src_std  = agency_stats["std"]
            src_n    = min(agency_stats["sample_count"], 200)
            rng = np.random.default_rng(42)
            arr = rng.normal(src_mean, max(src_std, 0.005), src_n)
            arr = arr[(arr >= 0.80) & (arr <= 1.10)]
            values = arr.tolist()
        elif global_stats:
            src_mean = global_stats["mean"]
            src_std  = global_stats["std"]
            src_n    = 0
            arr = np.array([src_mean])
            values = [src_mean]
        else:
            return {
                "bins": [], "mode": None, "mean": None, "std": None, "sample_count": 0,
                "p25": None, "p50": None, "p75": None,
                "agency_stats": None, "industry_stats": None, "global_stats": global_stats,
            }

        arr = np.array(values)
        bins_range = np.arange(0.800, 1.101, 0.001)
        counts, edges = np.histogram(arr, bins=bins_range)
        bins = [{"rate_pct": round(float(edges[i]), 4), "count": int(counts[i])} for i in range(len(counts))]
        mode_idx = int(np.argmax(counts))
        return {
            "bins": bins,
            "mode": round(float(edges[mode_idx]), 4) if counts[mode_idx] > 0 else None,
            "mean": round(float(np.mean(arr)), 4),
            "std":  round(float(np.std(arr)),  4),
            "p25":  round(float(np.percentile(arr, 25)), 4),
            "p50":  round(float(np.percentile(arr, 50)), 4),
            "p75":  round(float(np.percentile(arr, 75)), 4),
            "sample_count": len(values),
            # 발주처별 세분화 통계
            "agency_stats":   agency_stats,
            "industry_stats": industry_stats,
            "global_stats":   global_stats,
        }

    def model_info(self, db: Session, months: int = 12) -> dict:
        import json, os
        from pathlib import Path
        MODEL_DIR = Path(os.getenv("ML_MODELS_PATH", "/app/ml_models"))
        meta_path = MODEL_DIR / "meta.json"
        if meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)
        else:
            meta = None

        total_results = db.execute(text("SELECT COUNT(*) FROM bid_results")).scalar() or 0
        winner_results = db.execute(text("SELECT COUNT(*) FROM bid_results WHERE is_winner=true")).scalar() or 0
        recent_preds = db.execute(text(
            "SELECT COUNT(*) FROM prediction_logs WHERE created_at >= NOW() - INTERVAL '30 days'"
        )).scalar() or 0

        cutoff = datetime.now() - timedelta(days=months * 30)
        period_results = db.execute(text(
            "SELECT COUNT(*) FROM bid_results r JOIN bids b ON b.id = r.bid_id WHERE b.bid_open_date >= :cutoff"
        ), {"cutoff": cutoff}).scalar() or 0
        period_winners = db.execute(text(
            "SELECT COUNT(*) FROM bid_results r JOIN bids b ON b.id = r.bid_id WHERE r.is_winner=true AND b.bid_open_date >= :cutoff"
        ), {"cutoff": cutoff}).scalar() or 0
        period_preds = db.execute(text(
            "SELECT COUNT(*) FROM prediction_logs WHERE created_at >= :cutoff"
        ), {"cutoff": cutoff}).scalar() or 0

        return {
            "model": meta or {"version": "rule-based-v1", "train_size": 0, "winner_size": 0},
            "data_availability": {
                "total_results":  total_results,
                "winner_results": winner_results,
                "ready_for_ml":   winner_results >= 20,
            },
            "period_data": {
                "results": period_results,
                "winners": period_winners,
                "months":  months,
            },
            "usage": {
                "predictions_30d":    recent_preds,
                "predictions_period": period_preds,
            },
        }

# ==================================================
# 사정율 트렌드 서비스
# ==================================================

class SrateTrendService:
    """발주처×공종 최근 3개월 vs 이전 3개월 사정율 트렌드 분석."""

    THRESHOLD = 0.002  # ±0.2%p 이상이면 상승/하락

    def get_trend(self, db: Session, agency_id: Optional[int], industry_id: Optional[int]) -> dict:
        rows = self._from_assessment_stats(db, agency_id, industry_id)
        if not rows:
            rows = self._from_bid_results(db, agency_id, industry_id)
        return self._build_result(rows, datetime.now())

    def get_top_trends(self, db: Session, limit: int = 3) -> list:
        sql_rows = db.execute(text("""
            SELECT ars.group_id, a.name,
                   ars.period_year, ars.period_month,
                   ars.srate_mean::float, ars.sample_count
            FROM assessment_rate_stats ars
            JOIN agencies a ON a.id = ars.group_id
            WHERE ars.group_type = 'agency' AND ars.period_month IS NOT NULL
              AND make_date(ars.period_year::int, ars.period_month::int, 1) >= NOW() - INTERVAL '12 months'
            ORDER BY ars.group_id, ars.period_year, ars.period_month
        """)).fetchall()

        agency_data: dict = {}
        for r in sql_rows:
            gid = r[0]
            if gid not in agency_data:
                agency_data[gid] = {"agency_id": gid, "agency_name": r[1], "rows": []}
            agency_data[gid]["rows"].append({
                "period_year": r[2], "period_month": r[3],
                "srate_mean": r[4], "sample_count": r[5] or 0,
            })

        now = datetime.now()
        results = []
        for gid, info in agency_data.items():
            trend = self._build_result(info["rows"], now)
            if trend["direction"] != "stable":
                results.append({"agency_id": gid, "agency_name": info["agency_name"], **trend})

        results.sort(key=lambda x: abs(x["delta"]), reverse=True)
        return results[:limit]

    def _from_assessment_stats(self, db: Session, agency_id: Optional[int], industry_id: Optional[int]) -> list:
        if agency_id:
            group_type, gid = "agency", agency_id
        elif industry_id:
            group_type, gid = "industry", industry_id
        else:
            group_type, gid = "global", None

        if gid is not None:
            rows = db.execute(text("""
                SELECT period_year, period_month, srate_mean::float, sample_count
                FROM assessment_rate_stats
                WHERE group_type = :gt AND group_id = :gid AND period_month IS NOT NULL
                  AND make_date(period_year::int, period_month::int, 1) >= NOW() - INTERVAL '12 months'
                ORDER BY period_year, period_month
            """), {"gt": group_type, "gid": gid}).fetchall()
        else:
            rows = db.execute(text("""
                SELECT period_year, period_month, srate_mean::float, sample_count
                FROM assessment_rate_stats
                WHERE group_type = 'global' AND period_month IS NOT NULL
                  AND make_date(period_year::int, period_month::int, 1) >= NOW() - INTERVAL '12 months'
                ORDER BY period_year, period_month
            """)).fetchall()

        return [
            {"period_year": r[0], "period_month": r[1], "srate_mean": r[2], "sample_count": r[3] or 0}
            for r in rows
        ]

    def _from_bid_results(self, db: Session, agency_id: Optional[int], industry_id: Optional[int]) -> list:
        rows = db.execute(text("""
            SELECT
                EXTRACT(YEAR FROM b.bid_open_date)::int,
                EXTRACT(MONTH FROM b.bid_open_date)::int,
                AVG(r.assessment_rate)::float,
                COUNT(*)::int
            FROM bid_results r
            JOIN bids b ON b.id = r.bid_id
            WHERE r.assessment_rate IS NOT NULL
              AND b.bid_open_date >= NOW() - INTERVAL '12 months'
              AND (:agency_id IS NULL OR b.agency_id = :agency_id)
              AND (:industry_id IS NULL OR b.industry_id = :industry_id)
            GROUP BY 1, 2
            ORDER BY 1, 2
        """), {"agency_id": agency_id, "industry_id": industry_id}).fetchall()
        return [
            {"period_year": r[0], "period_month": r[1], "srate_mean": r[2], "sample_count": r[3]}
            for r in rows
        ]

    def _build_result(self, rows: list, now: datetime) -> dict:
        if not rows:
            return {
                "direction": "stable", "delta": 0.0,
                "recent_mean": 0.0, "prev_mean": None,
                "sample_count": 0, "signal": "데이터 부족으로 트렌드 분석 불가",
            }

        recent, prev = [], []
        for row in rows:
            months_ago = (now.year - row["period_year"]) * 12 + (now.month - row["period_month"])
            if months_ago < 6:
                recent.append(row)
            elif months_ago < 12:
                prev.append(row)

        if not recent:
            # fallback: 데이터 분포 기반 전반/후반 분할
            all_rows = sorted(rows, key=lambda r: (r["period_year"], r["period_month"]))
            if len(all_rows) >= 2:
                mid = len(all_rows) // 2
                prev = all_rows[:mid]
                recent = all_rows[mid:]
            else:
                return {
                    "direction": "stable", "delta": 0.0,
                    "recent_mean": 0.0, "prev_mean": None,
                    "sample_count": 0, "signal": "최근 데이터 없음",
                }

        total_recent = sum(r["sample_count"] for r in recent)
        if total_recent > 0:
            recent_mean = sum(r["srate_mean"] * r["sample_count"] for r in recent) / total_recent
        else:
            recent_mean = sum(r["srate_mean"] for r in recent) / len(recent)
        sample_count = total_recent or len(recent)

        if not prev:
            return {
                "direction": "stable", "delta": 0.0,
                "recent_mean": round(recent_mean, 4), "prev_mean": None,
                "sample_count": sample_count, "signal": "이전 기간 데이터 부족",
            }

        total_prev = sum(r["sample_count"] for r in prev)
        if total_prev > 0:
            prev_mean = sum(r["srate_mean"] * r["sample_count"] for r in prev) / total_prev
        else:
            prev_mean = sum(r["srate_mean"] for r in prev) / len(prev)

        delta = recent_mean - prev_mean

        if delta > self.THRESHOLD:
            direction = "up"
            signal = f"최근 3개월 사정율 +{delta*100:.2f}%p 상승 중 → 균형형 이상 추천"
        elif delta < -self.THRESHOLD:
            direction = "down"
            signal = f"최근 3개월 사정율 {delta*100:.2f}%p 하락 중 → 안정형 또는 낮게 입찰 추천"
        else:
            direction = "stable"
            signal = f"사정율 변화 미미 ({delta*100:+.2f}%p) → 균형형 전략 유지"

        return {
            "direction": direction,
            "delta": round(delta, 6),
            "recent_mean": round(recent_mean, 4),
            "prev_mean": round(prev_mean, 4),
            "sample_count": sample_count,
            "signal": signal,
        }


# ==================================================
# 하이브리드 추천 서비스 (v2)
# ==================================================

class KpiService:
    """E8: KPI 집계 + 경영진 대시보드"""

    def get_dashboard(self, db: Session, user_id: int, period_type: str = "MONTHLY") -> dict:
        from ..models import CompanyProfile, ActualBidOutcome, BidDecision, KpiSnapshot
        from ..ml.feedback import build_kpi_snapshot, should_alert

        today = datetime.utcnow().date()

        # 캐시된 스냅샷 조회
        cached = db.query(KpiSnapshot).filter(
            KpiSnapshot.snapshot_date == today,
            KpiSnapshot.user_id == user_id,
            KpiSnapshot.period_type == period_type,
        ).first()

        # 스냅샷 재계산
        kpi = build_kpi_snapshot(db, user_id, today, period_type)
        if not kpi:
            kpi = {
                "total_bids": 0, "total_wins": 0, "win_rate": 0.0,
                "qualify_pass_rate": None, "avg_rank_at_loss": None,
                "srate_mae": None, "win_prob_calibration": None,
                "go_rate": None, "no_go_saved": 0,
            }

        profile    = db.query(CompanyProfile).first()
        monthly_target = profile.monthly_win_target if profile else 3

        alerts = should_alert(kpi)

        # 최근 6개월 트렌드
        trend = []
        for i in range(5, -1, -1):
            d = today.replace(day=1)
            if i > 0:
                m = d.month - i
                y = d.year
                while m <= 0:
                    m += 12
                    y -= 1
                d = d.replace(year=y, month=m)
            snap = db.query(KpiSnapshot).filter(
                KpiSnapshot.snapshot_date == d,
                KpiSnapshot.user_id == user_id,
                KpiSnapshot.period_type == "MONTHLY",
            ).first()
            trend.append({
                "month":     d.strftime("%Y-%m"),
                "win_rate":  float(snap.win_rate) if snap and snap.win_rate else 0.0,
                "total_bids": snap.total_bids if snap else 0,
                "total_wins": snap.total_wins if snap else 0,
            })

        wins = kpi.get("total_wins", 0)
        return {
            "period_type":          period_type,
            "snapshot_date":        today.isoformat(),
            "total_bids":           kpi.get("total_bids", 0),
            "total_wins":           wins,
            "win_rate":             kpi.get("win_rate", 0.0),
            "monthly_target":       monthly_target,
            "target_achievement":   round(wins / monthly_target, 4) if monthly_target else 0.0,
            "qualify_pass_rate":    kpi.get("qualify_pass_rate"),
            "avg_rank_at_loss":     kpi.get("avg_rank_at_loss"),
            "srate_mae":            kpi.get("srate_mae"),
            "win_prob_calibration": kpi.get("win_prob_calibration"),
            "go_rate":              kpi.get("go_rate"),
            "no_go_saved":          kpi.get("no_go_saved", 0),
            "alerts":               alerts,
            "monthly_trend":        trend,
        }

    def upsert_snapshot(self, db: Session, kpi: dict):
        from ..models import KpiSnapshot
        from datetime import date as date_type
        snap_date = kpi.get("snapshot_date", datetime.utcnow().date())
        if isinstance(snap_date, str):
            snap_date = date_type.fromisoformat(snap_date)

        existing = db.query(KpiSnapshot).filter(
            KpiSnapshot.snapshot_date == snap_date,
            KpiSnapshot.user_id == kpi.get("user_id"),
            KpiSnapshot.period_type == kpi.get("period_type", "MONTHLY"),
        ).first()

        fields = {
            "total_bids":           kpi.get("total_bids", 0),
            "total_wins":           kpi.get("total_wins", 0),
            "win_rate":             kpi.get("win_rate"),
            "qualify_pass_rate":    kpi.get("qualify_pass_rate"),
            "avg_rank_at_loss":     kpi.get("avg_rank_at_loss"),
            "srate_mae":            kpi.get("srate_mae"),
            "win_prob_calibration": kpi.get("win_prob_calibration"),
            "go_rate":              kpi.get("go_rate"),
            "no_go_saved":          kpi.get("no_go_saved", 0),
        }

        if existing:
            for k, v in fields.items():
                setattr(existing, k, v)
        else:
            snap = KpiSnapshot(
                snapshot_date=snap_date,
                user_id=kpi.get("user_id"),
                period_type=kpi.get("period_type", "MONTHLY"),
                **fields,
            )
            db.add(snap)
        db.commit()

class PortfolioService:
    """E7: 포트폴리오 최적화 서비스"""

    def optimize(self, db: Session, user_id: int, bid_ids: list) -> dict:
        from ..models import Bid, BidDecision, CompanyProfile, PortfolioState
        from ..ml.portfolio import PortfolioBidItem, PortfolioConstraints, optimize, compute_portfolio_stats

        profile    = db.query(CompanyProfile).first()
        from .agency import CompanyProfileService
        bond_svc   = CompanyProfileService()
        bond       = bond_svc.get_remaining_bond(db)
        active_cnt = db.query(func.count(PortfolioState.id)).filter(
            PortfolioState.status == "ACTIVE",
        ).scalar() or 0

        constraints = PortfolioConstraints(
            remaining_bond=bond["remaining"],
            max_concurrent_bids=profile.max_concurrent_bids if profile else 5,
            active_bid_count=active_cnt,
            weekly_prep_hours=40.0,
            monthly_target=profile.monthly_win_target if profile else 3,
            current_month_wins=0,
        )

        items: list[PortfolioBidItem] = []
        from .recommend import BidSelectionService
        sel_svc = BidSelectionService()

        for bid_id in bid_ids:
            bid = db.query(Bid).filter(Bid.id == bid_id).first()
            if not bid:
                continue

            # 최신 선별 결과 조회 (없으면 즉시 평가)
            dec = db.query(BidDecision).filter(
                BidDecision.bid_id == bid_id,
                BidDecision.user_id == user_id,
            ).order_by(BidDecision.created_at.desc()).first()

            if not dec:
                try:
                    sel_svc.evaluate_bid(db, bid_id, user_id)
                    dec = db.query(BidDecision).filter(
                        BidDecision.bid_id == bid_id,
                        BidDecision.user_id == user_id,
                    ).order_by(BidDecision.created_at.desc()).first()
                except Exception:
                    pass

            verdict       = dec.verdict if dec else "WATCH"
            sel_score     = float(dec.selection_score or 5.0) if dec else 5.0
            ev_score      = dec.ev_score or 0 if dec else 0
            if dec and dec.qualify_prob:
                qualify_prob = float(dec.qualify_prob)
            else:
                from ..ml.qualification import get_empirical_qualify_rate
                _bucket = (1 if bid.base_amount < 1e8 else 2 if bid.base_amount < 3e8
                           else 3 if bid.base_amount < 1e9 else 4 if bid.base_amount < 5e9 else 5)
                qualify_prob = get_empirical_qualify_rate(db, user_id, bid.agency_id, _bucket)
            win_prob      = float(dec.win_prob_best or 0.3) if dec else 0.3
            rec_rate      = float(dec.recommended_rate or 0.0) if dec else 0.0
            bond_exposure = int(bid.base_amount * 0.1)  # 기초금액의 10% 보증 근사

            items.append(PortfolioBidItem(
                bid_id=bid_id,
                title=bid.title,
                base_amount=bid.base_amount,
                bid_date=bid.bid_open_date.date().isoformat() if bid.bid_open_date else "unknown",
                verdict=verdict,
                selection_score=sel_score,
                ev_score=ev_score,
                qualify_prob=qualify_prob,
                win_prob=win_prob,
                bond_exposure=bond_exposure,
                recommended_rate=rec_rate,
            ))

        plan = optimize(items, constraints)
        stats = compute_portfolio_stats(plan)

        def _fmt(item: PortfolioBidItem) -> dict:
            return {
                "bid_id":           item.bid_id,
                "title":            item.title,
                "base_amount":      item.base_amount,
                "bid_date":         item.bid_date,
                "verdict":          item.verdict,
                "selection_score":  item.selection_score,
                "ev_score":         item.ev_score,
                "qualify_prob":     item.qualify_prob,
                "win_prob":         item.win_prob,
                "recommended_rate": item.recommended_rate,
            }

        return {
            "selected":             [_fmt(i) for i in plan.selected],
            "not_selected":         [_fmt(i) for i in plan.not_selected],
            "no_go_list":           [_fmt(i) for i in plan.no_go_list],
            "expected_wins":        plan.expected_wins,
            "expected_win_amount":  plan.expected_win_amount,
            "total_ev":             plan.total_ev,
            "bond_usage":           plan.bond_usage,
            "remaining_bond_after": plan.remaining_bond_after,
            "alerts":               plan.alerts,
            "schedule":             plan.schedule,
            "stats":                stats,
        }


# ==================================================
# 경쟁사 투찰성향 분석 서비스
# ==================================================

class BacktestService:
    """
    과거 투찰 이력(my_bid_records / bid_executions)과
    실제 낙찰 결과(bid_results)를 비교해 수주율 개선 추정.

    핵심 질문:
      "우리 시스템의 추천율로 투찰했다면 얼마나 더 낙찰됐을까?"
    """

    def __init__(self, db: Session):
        self.db = db

    def run(self, user_id: int, months: int = 60) -> dict:
        # 1) 결과가 확정된 내 투찰 기록
        my_records = self.db.execute(text("""
            SELECT
                e.id,
                e.title,
                e.agency_name,
                e.base_amount,
                e.submitted_rate,
                e.recommended_rate,
                e.winner_rate,
                e.floor_rate,
                e.status,
                e.result_rank,
                e.total_bidders,
                e.opened_at
            FROM bid_executions e
            WHERE e.user_id = :uid
              AND e.status IN ('낙찰', '패찰')
              AND e.submitted_rate IS NOT NULL
              AND e.winner_rate IS NOT NULL
              AND (e.opened_at IS NULL OR e.opened_at >= NOW() - INTERVAL :months_str)
            ORDER BY e.created_at DESC
            LIMIT 500
        """), {"uid": user_id, "months_str": f"{months} months"}).fetchall()

        if not my_records:
            # my_bid_records 폴백
            my_records = self.db.execute(text("""
                SELECT
                    m.id,
                    m.title,
                    m.agency_name,
                    m.base_amount,
                    m.submitted_rate,
                    m.recommendation_rate AS recommended_rate,
                    m.actual_winner_rate  AS winner_rate,
                    NULL AS floor_rate,
                    m.result AS status,
                    NULL AS result_rank,
                    NULL AS total_bidders,
                    m.bid_date AS opened_at
                FROM my_bid_records m
                WHERE m.user_id = :uid
                  AND m.result IN ('won', 'lost', '낙찰', '패찰')
                  AND m.submitted_rate IS NOT NULL
                  AND m.actual_winner_rate IS NOT NULL
                ORDER BY m.bid_date DESC
                LIMIT 500
            """), {"uid": user_id}).fetchall()

        if not my_records:
            return self._empty_result()

        cols = ["id", "title", "agency_name", "base_amount", "submitted_rate",
                "recommended_rate", "winner_rate", "floor_rate", "status",
                "result_rank", "total_bidders", "opened_at"]
        records = [dict(zip(cols, r)) for r in my_records]

        total = len(records)
        actual_wins = sum(1 for r in records if r["status"] in ("낙찰", "won"))
        actual_win_rate = round(actual_wins / total * 100, 1) if total else 0

        # 2) 추천율로 투찰했을 때 낙찰 시뮬레이션
        #    기준: submitted_rate <= winner_rate 이면 낙찰 가능 (하한율 이상)
        sim_wins = 0
        sim_won_list, sim_miss_list = [], []

        for r in records:
            winner = float(r["winner_rate"])
            floor = float(r["floor_rate"]) if r["floor_rate"] else 0.87745
            rec = float(r["recommended_rate"]) if r["recommended_rate"] else None
            actual = float(r["submitted_rate"])
            actual_won = r["status"] in ("낙찰", "won")

            if rec is None:
                sim_wins += 1 if actual_won else 0
                continue

            # 추천율이 하한율 이상이고 낙찰율 이하면 낙찰로 가정
            would_win = floor <= rec <= winner + 0.002  # 2bp 여유

            if would_win:
                sim_wins += 1
                if not actual_won:
                    sim_won_list.append({
                        "title": (r["title"] or "")[:40],
                        "agency": r["agency_name"] or "",
                        "actual_rate": round(actual * 100, 4),
                        "recommended_rate": round(rec * 100, 4),
                        "winner_rate": round(winner * 100, 4),
                        "gap_improvement": round((rec - actual) * 100, 4),
                    })

            if actual_won and not would_win:
                sim_miss_list.append({
                    "title": (r["title"] or "")[:40],
                    "agency": r["agency_name"] or "",
                    "actual_rate": round(actual * 100, 4),
                    "recommended_rate": round(rec * 100, 4),
                    "winner_rate": round(winner * 100, 4),
                })

        sim_win_rate = round(sim_wins / total * 100, 1) if total else 0
        improvement = round(sim_win_rate - actual_win_rate, 1)

        # 3) 패찰 원인 분포
        cause_dist: dict = {}
        for r in records:
            if r["status"] not in ("패찰", "lost"):
                continue
            winner = float(r["winner_rate"])
            actual = float(r["submitted_rate"])
            gap = actual - winner
            if gap > 0.005:
                cause = "투찰률과도"
            elif gap > 0.001:
                cause = "투찰률과도(미세)"
            elif r["total_bidders"] and r["total_bidders"] >= 15:
                cause = "경쟁과다"
            else:
                cause = "기타"
            cause_dist[cause] = cause_dist.get(cause, 0) + 1

        # 4) 월별 추이 (최근 12개월)
        monthly: dict = {}
        for r in records:
            dt = r["opened_at"]
            if dt is None:
                continue
            if hasattr(dt, "strftime"):
                key = dt.strftime("%Y-%m")
            else:
                try:
                    key = str(dt)[:7]
                except Exception:
                    continue
            if key not in monthly:
                monthly[key] = {"total": 0, "actual_win": 0, "sim_win": 0}
            monthly[key]["total"] += 1
            if r["status"] in ("낙찰", "won"):
                monthly[key]["actual_win"] += 1

        monthly_trend = [
            {
                "month": k,
                "total": v["total"],
                "actual_win": v["actual_win"],
                "actual_rate": round(v["actual_win"] / v["total"] * 100, 1) if v["total"] else 0,
            }
            for k, v in sorted(monthly.items())[-12:]
        ]

        return {
            "period_months": months,
            "total_bids": total,
            "actual_wins": actual_wins,
            "actual_win_rate": actual_win_rate,
            "simulated_wins": sim_wins,
            "simulated_win_rate": sim_win_rate,
            "improvement_pct": improvement,
            "cause_distribution": [
                {"cause": k, "count": v} for k, v in sorted(cause_dist.items(), key=lambda x: -x[1])
            ],
            "monthly_trend": monthly_trend,
            "sample_improvements": sim_won_list[:10],
            "sample_regressions": sim_miss_list[:5],
            "data_source": "bid_executions" if my_records else "my_bid_records",
        }

    def _empty_result(self) -> dict:
        return {
            "period_months": 0,
            "total_bids": 0,
            "actual_wins": 0,
            "actual_win_rate": 0,
            "simulated_wins": 0,
            "simulated_win_rate": 0,
            "improvement_pct": 0,
            "cause_distribution": [],
            "monthly_trend": [],
            "sample_improvements": [],
            "sample_regressions": [],
            "data_source": "none",
            "message": "SUCVIEW 파일을 업로드하거나 투찰 실행 관리에 결과를 입력해주세요.",
        }

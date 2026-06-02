"""
비즈니스 로직 서비스 레이어.
Controller(API) -> Service -> Repository(DB) 방향 준수.
"""
import math
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import text, func, and_, or_, desc

from .models import (
    Bid, BidResult, Competitor, Agency, Industry, Region,
    FeatureStore, PredictionLog, PredictionLogV2, CompetitorStat, User, AuditLog,
    IndustryFilter, BidBookmark, CollectionLog, MyBidRecord,
)
from .schemas import (
    BidCreate, BidResultCreate, RecommendRequest, RecommendResponse,
    RateRange, WinProbabilities, Explanation, ExplanationFactor, RiskInfo,
    SimilarCase, BidSummary, BidDetail, BidResultOut, CompetitorDetail
)
from .ml.engine import build_features, get_engine, FEATURE_LABELS
from .ml.assessment  import load_srate_stats, predict_srate, compute_market_trend
from .ml.competition import compute_competition_features, get_competitor_profiles, get_market_competitor_distributions
from .ml.simulation  import recommend_with_simulation

logger = logging.getLogger(__name__)

# --------------------------------------------------
# 공통 헬퍼
# --------------------------------------------------

def get_active_industry_ids(db: Session):
    """활성화된 공종 ID 목록 반환.
    industry_filters 테이블이 비어있으면 None(전체 허용) 반환.
    설정이 있으면 is_active=True인 ID 목록만 반환."""
    filters = db.query(IndustryFilter).all()
    if not filters:
        return None  # 필터 미설정 = 전체 허용
    return [f.industry_id for f in filters if f.is_active]


def _build_ind_sql(active_ids, alias: str = "b") -> str:
    """활성 공종 SQL WHERE 조건 문자열 생성."""
    if active_ids is None:
        return ""
    if not active_ids:
        return "AND 1=0"
    ids_str = ",".join(map(str, active_ids))
    return f"AND {alias}.industry_id IN ({ids_str})"


# --------------------------------------------------
# 입찰 서비스
# --------------------------------------------------

class BidService:

    def list_bids(
        self, db: Session,
        agency_id=None, industry_id=None, region_id=None,
        status=None, date_from=None, date_to=None,
        keyword=None, page=1, size=20,
        sort_by='notice_date',
    ) -> dict:
        q = db.query(Bid)
        if agency_id:   q = q.filter(Bid.agency_id == agency_id)
        if industry_id: q = q.filter(Bid.industry_id == industry_id)
        if region_id:   q = q.filter(Bid.region_id == region_id)
        if status:      q = q.filter(Bid.status == status)
        if date_from:   q = q.filter(Bid.bid_open_date >= date_from)
        if date_to:     q = q.filter(Bid.bid_open_date < datetime.combine(date_to + timedelta(days=1), datetime.min.time()))
        if keyword:
            q = q.filter(Bid.title.ilike(f"%{keyword}%"))

        # 활성 공종 필터 — 사용자가 특정 공종을 지정하지 않은 경우에만 전역 필터 적용
        if not industry_id:
            active_ids = get_active_industry_ids(db)
            if active_ids is not None:
                if not active_ids:
                    return {"items": [], "total": 0, "page": page, "size": size}
                q = q.filter(Bid.industry_id.in_(active_ids))

        total = q.count()

        if sort_by == 'bid_open_date':
            q = q.order_by(desc(Bid.bid_open_date).nullslast(), desc(Bid.created_at))
        else:
            q = q.order_by(desc(Bid.notice_date).nullslast(), desc(Bid.created_at))

        bids = q.offset((page-1)*size).limit(size).all()

        items = []
        for b in bids:
            winner = next((r for r in b.results if r.is_winner), None)
            items.append({
                "id": b.id, "announcement_no": b.announcement_no,
                "title": b.title,
                "agency_name":   b.agency.name if b.agency else "",
                "industry_name": b.industry.name if b.industry else "",
                "region_name":   b.region.name if b.region else "",
                "base_amount":   b.base_amount,
                "notice_date":   b.notice_date,
                "bid_open_date": b.bid_open_date,
                "status":        b.status,
                "source":        b.source,
                "winner_rate":   float(winner.bid_rate) if winner else None,
                "competitor_count": len(b.results),
            })
        return {"items": items, "total": total, "page": page, "size": size}

    def get_bid_detail(self, db: Session, bid_id: int) -> Optional[dict]:
        b = db.query(Bid).filter(Bid.id == bid_id).first()
        if not b:
            return None
        winner = next((r for r in b.results if r.is_winner), None)
        results = [
            {
                "id": r.id,
                "competitor_id":   r.competitor_id,
                "competitor_name": r.competitor.name if r.competitor else "",
                "bid_amount":      r.bid_amount,
                "bid_rate":        float(r.bid_rate),
                "rank":            r.rank,
                "is_winner":       r.is_winner,
                "assessment_rate": float(r.assessment_rate) if r.assessment_rate else None,
            }
            for r in sorted(b.results, key=lambda x: x.rank)
        ]
        return {
            "id": b.id, "announcement_no": b.announcement_no,
            "title": b.title,
            "agency_name":         b.agency.name if b.agency else "",
            "industry_name":       b.industry.name if b.industry else "",
            "region_name":         b.region.name if b.region else "",
            "base_amount":         b.base_amount,
            "estimated_price":     b.estimated_price,
            "a_value":             b.a_value,
            "min_bid_rate":        float(b.min_bid_rate) if b.min_bid_rate else None,
            "notice_date":         b.notice_date,
            "bid_open_date":       b.bid_open_date,
            "construction_period": b.construction_period,
            "region_restriction":  b.region_restriction,
            "status":              b.status,
            "source":              b.source,
            "ntce_url":            b.ntce_url,
            "winner_rate":         float(winner.bid_rate) if winner else None,
            "competitor_count":    len(b.results),
            "construction_site":   b.construction_site,
            "contract_method":     b.contract_method,
            "bid_method":          b.bid_method,
            "eligible_regions":    b.eligible_regions,
            "industry_limit":      b.industry_limit,
            "bid_close_date":      b.bid_close_date,
            "contact_name":        b.contact_name,
            "contact_tel":         b.contact_tel,
            "results":             results,
        }

    def create_bid(self, db: Session, data: BidCreate, results: List[BidResultCreate] = None) -> Bid:
        bid = Bid(
            announcement_no=data.announcement_no,
            title=data.title,
            agency_id=data.agency_id,
            industry_id=data.industry_id,
            region_id=data.region_id,
            base_amount=data.base_amount,
            min_bid_rate=data.min_bid_rate,
            a_value=data.a_value,
            bid_open_date=data.bid_open_date,
            construction_period=data.construction_period,
            region_restriction=data.region_restriction,
            source="manual",
            status="closed",
        )
        db.add(bid)
        db.flush()

        if results:
            for r in results:
                comp = db.query(Competitor).filter(Competitor.name == r.competitor_name).first()
                if not comp:
                    comp = Competitor(name=r.competitor_name)
                    db.add(comp)
                    db.flush()
                br = BidResult(
                    bid_id=bid.id,
                    competitor_id=comp.id,
                    bid_amount=r.bid_amount,
                    bid_rate=r.bid_rate,
                    rank=r.rank,
                    is_winner=r.is_winner,
                )
                db.add(br)
        db.commit()
        return bid

    def find_similar_bids(self, db: Session, bid_id: int, top_k: int = 8) -> List[dict]:
        bid = db.query(Bid).filter(Bid.id == bid_id).first()
        if not bid:
            return []
        rows = db.query(Bid).filter(
            Bid.industry_id == bid.industry_id,
            Bid.region_id == bid.region_id,
            Bid.base_amount.between(int(bid.base_amount * 0.6), int(bid.base_amount * 1.4)),
            Bid.id != bid_id,
            Bid.status == "closed",
        ).order_by(desc(Bid.bid_open_date)).limit(top_k).all()

        results = []
        for b in rows:
            winner = next((r for r in b.results if r.is_winner), None)
            amt_diff = abs(b.base_amount - bid.base_amount) / bid.base_amount
            sim_score = round(1.0 - amt_diff, 3)
            results.append({
                "bid_id": b.id, "title": b.title,
                "agency_name":     b.agency.name if b.agency else "",
                "base_amount":     b.base_amount,
                "bid_open_date":   b.bid_open_date,
                "winner_rate":     float(winner.bid_rate) if winner else None,
                "competitor_count": len(b.results),
                "similarity_score": sim_score,
            })
        return results

    def get_keyword_matches(self, db: Session) -> list:
        """활성 키워드별 매칭 공고 수 + 최근 공고 5건 반환."""
        from .models import WatchKeyword as KW
        keywords = db.query(KW).filter(KW.is_active == True).order_by(KW.created_at.desc()).all()
        result = []
        cutoff_7d = datetime.now() - timedelta(days=7)
        active_ids = get_active_industry_ids(db)
        for kw in keywords:
            if kw.kw_type == "agency":
                q = (db.query(Bid)
                     .join(Agency, Agency.id == Bid.agency_id)
                     .filter(Agency.name.ilike(f"%{kw.keyword}%")))
            else:
                q = db.query(Bid).filter(Bid.title.ilike(f"%{kw.keyword}%"))
            if active_ids is not None and active_ids:
                q = q.filter(Bid.industry_id.in_(active_ids))
            total = q.count()
            new_7d = q.filter(Bid.created_at >= cutoff_7d).count()
            recent = q.order_by(desc(Bid.notice_date)).limit(5).all()
            result.append({
                "keyword_id":  kw.id,
                "keyword":     kw.keyword,
                "kw_type":     kw.kw_type,
                "note":        kw.note,
                "match_count": total,
                "new_7d":      new_7d,
                "recent_bids": [
                    {
                        "id":          b.id,
                        "title":       b.title,
                        "agency_name": db.query(Agency).filter(Agency.id == b.agency_id).with_entities(Agency.name).scalar() or "",
                        "base_amount": b.base_amount,
                        "notice_date": b.notice_date.isoformat() if b.notice_date else None,
                        "status":      b.status,
                    }
                    for b in recent
                ],
            })
        return result

# --------------------------------------------------
# 추천 서비스
# --------------------------------------------------

class RecommendationService:

    def recommend(self, db: Session, req: RecommendRequest, user_id: int = None) -> dict:
        history_df = self._load_history(db, months=24)
        agency    = db.query(Agency).filter(Agency.id == req.agency_id).first()
        industry  = db.query(Industry).filter(Industry.id == req.industry_id).first()
        region    = db.query(Region).filter(Region.id == req.region_id).first()

        features = build_features(
            agency_id=req.agency_id,
            industry_id=req.industry_id,
            region_id=req.region_id,
            base_amount=req.base_amount,
            construction_period=req.construction_period,
            region_restriction=False,
            bid_open_date=datetime.now(),
            historical_df=history_df,
        )

        if req.known_competitor_ids:
            features["expected_competitor_count"] = max(
                features.get("expected_competitor_count", 10),
                len(req.known_competitor_ids)
            )
            features["competitor_strength_score"] = self._calc_competitor_strength(
                db, req.known_competitor_ids
            )

        engine = get_engine()
        result = engine.recommend(features)
        similar = self._find_similar(db, req, top_k=5)
        risk = self._assess_risk(features, result)
        top_factors = self._build_factors(result.get("shap_values", {}), features)
        self._save_log(db, req, result, risk, user_id, features)

        data_count = int(features.get("similar_bid_count", 0)) + int(features.get("agency_bid_count_12m", 0))
        base_rate_val = features.get("agency_avg_rate_12m") or features.get("similar_avg_rate") or 0.879

        return {
            "rate_range": result["rate_range"],
            "win_probabilities": result["win_probabilities"],
            "risk": risk,
            "explanation": {
                "top_factors": top_factors,
                "narrative_ko": result["narrative_ko"],
                "base_rate": round(float(base_rate_val), 4),
                "model_version": result["model_version"],
                "data_count": data_count,
            },
            "similar_cases": similar,
        }

    def _load_history(self, db: Session, months: int = 24) -> pd.DataFrame:
        cutoff = datetime.now() - timedelta(days=months * 30)
        rows = db.execute(text("""
            SELECT b.id, b.agency_id, b.industry_id, b.region_id,
                   b.base_amount, b.bid_open_date,
                   r.bid_rate as winner_rate,
                   (SELECT COUNT(*) FROM bid_results r2 WHERE r2.bid_id = b.id) as competitor_count
            FROM bids b
            LEFT JOIN bid_results r ON r.bid_id = b.id AND r.is_winner = true
            WHERE b.bid_open_date >= :cutoff AND b.status = 'closed'
        """), {"cutoff": cutoff}).fetchall()

        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=[
            "id","agency_id","industry_id","region_id",
            "base_amount","bid_open_date","winner_rate","competitor_count"
        ])
        df["winner_rate"]      = df["winner_rate"].astype(float)
        df["base_amount"]      = df["base_amount"].astype(float)
        df["competitor_count"] = df["competitor_count"].astype(float)
        return df

    def _calc_competitor_strength(self, db: Session, ids: List[int]) -> float:
        if not ids:
            return 5.0
        rows = db.query(CompetitorStat).filter(
            CompetitorStat.competitor_id.in_(ids),
            CompetitorStat.period_month == None
        ).order_by(desc(CompetitorStat.period_year)).all()
        if not rows:
            return 5.0
        scores = []
        for r in rows:
            ag = float(r.aggression_score or 5)
            wr = float(r.win_rate or 0) * 10
            sc = ag * 0.5 + wr * 0.5
            scores.append(sc)
        return round(float(np.mean(scores)), 2)

    def _find_similar(self, db: Session, req: RecommendRequest, top_k: int) -> List[dict]:
        rows = db.query(Bid).filter(
            Bid.industry_id == req.industry_id,
            Bid.region_id   == req.region_id,
            Bid.base_amount.between(int(req.base_amount * 0.6), int(req.base_amount * 1.4)),
            Bid.status == "closed",
        ).order_by(desc(Bid.bid_open_date)).limit(top_k).all()

        results = []
        for b in rows:
            winner = next((r for r in b.results if r.is_winner), None)
            amt_diff = abs(b.base_amount - req.base_amount) / req.base_amount
            results.append({
                "bid_id": b.id, "title": b.title,
                "agency_name":     b.agency.name if b.agency else "",
                "base_amount":     b.base_amount,
                "bid_open_date":   b.bid_open_date,
                "winner_rate":     float(winner.bid_rate) if winner else None,
                "competitor_count": len(b.results),
                "similarity_score": round(1.0 - amt_diff, 3),
            })
        return results

    def _assess_risk(self, features: dict, result: dict) -> dict:
        score = 0
        factors = []
        cnt = features.get("expected_competitor_count", 10)
        if cnt > 20:
            factors.append(f"높은 경쟁강도 (예상 {cnt}개사)")
            score += 2
        elif cnt > 15:
            score += 1

        rr = result["rate_range"]
        spread = rr["safe_upper"] - rr["safe_lower"]
        if spread > 0.03:
            factors.append(f"투찰률 분산 큼 (범위 {spread:.2%})")
            score += 2
        elif spread > 0.02:
            score += 1

        wp = result["win_probabilities"].get("at_center")
        if wp is not None and wp < 0.1:
            factors.append(f"낮은 낙찰 기대확률 ({wp:.1%})")
            score += 2

        sim_cnt = features.get("similar_bid_count", 0) or 0
        if sim_cnt < 5:
            factors.append("유사 입찰 사례 부족 (신뢰도 낮음)")
            score += 1

        if "rule-based" in result.get("model_version",""):
            factors.append("데이터 축적 중 - 규칙 기반 추천")

        level = "LOW" if score <= 1 else "MEDIUM" if score <= 3 else "HIGH"
        return {"level": level, "factors": factors, "score": float(score)}

    def _build_factors(self, shap_vals: dict, features: dict) -> List[dict]:
        if not shap_vals:
            return []
        sorted_items = sorted(shap_vals.items(), key=lambda x: abs(x[1]), reverse=True)[:5]
        factors = []
        for feat, sv in sorted_items:
            fval = features.get(feat)
            factors.append({
                "feature": feat,
                "label":   FEATURE_LABELS.get(feat, feat),
                "value":   round(float(fval), 4) if fval is not None else None,
                "shap_value": round(sv, 6),
                "direction": "positive" if sv > 0 else "negative",
            })
        return factors

    def _save_log(self, db: Session, req, result, risk, user_id, features):
        try:
            rr = result["rate_range"]
            wp = result["win_probabilities"]
            log = PredictionLog(
                bid_id=None, user_id=user_id,
                model_version=result["model_version"],
                input_features={
                    "agency_id": req.agency_id, "industry_id": req.industry_id,
                    "region_id": req.region_id, "base_amount": req.base_amount,
                    "features": {k: float(v) if isinstance(v,(int,float)) else v
                                 for k,v in features.items() if v is not None},
                },
                rate_safe_lower=rr["safe_lower"], rate_lower=rr["lower"],
                rate_center=rr["center"],         rate_upper=rr["upper"],
                rate_safe_upper=rr["safe_upper"],
                win_prob_center=wp.get("at_center"),
                risk_level=risk["level"],
                shap_values=result.get("shap_values") or {},
                explanation_text=result["narrative_ko"],
            )
            db.add(log)
            db.commit()
        except Exception as e:
            logger.debug(f"추천 로그 저장 실패: {e}")
            db.rollback()

# --------------------------------------------------
# 경쟁사 서비스
# --------------------------------------------------


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

class StatisticsService:

    def overview(self, db: Session, months: int = 12) -> dict:
        cutoff = datetime.now() - timedelta(days=months * 30)
        active_ids = get_active_industry_ids(db)
        ind_sql = _build_ind_sql(active_ids)

        bids_q = db.query(func.count(Bid.id)).filter(Bid.bid_open_date >= cutoff)
        if active_ids is not None:
            if not active_ids:
                return {"total_bids": 0, "total_competitors": 0, "avg_win_rate": 0, "avg_bid_rate": 0, "avg_competitor_count": 0, "monthly_trend": [],
                        "win_rate_change_pct": None, "bid_count_change_pct": None, "avg_competitors_change": None}
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

        return {
            "total_bids": total_bids,
            "total_competitors": total_comps,
            "avg_win_rate": round(avg_win_rate, 4),
            "avg_bid_rate": round(avg_win_rate, 4),
            "avg_competitor_count": round(avg_comp_count, 1),
            "monthly_trend": trend,
            "win_rate_change_pct": win_rate_change_pct,
            "bid_count_change_pct": bid_count_change_pct,
            "avg_competitors_change": avg_competitors_change,
        }

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
        ind_sql = _build_ind_sql(get_active_industry_ids(db), alias="ind")
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
        # estimated_price / base_amount 로 사정율 직접 계산 (BidResult.assessment_rate는 미수집)
        query = db.query(
            (cast(Bid.estimated_price, Float) / cast(Bid.base_amount, Float)).label('srate')
        ).filter(
            Bid.estimated_price.isnot(None),
            Bid.base_amount > 0,
            Bid.bid_open_date >= cutoff,
        )
        if agency_id:
            query = query.filter(Bid.agency_id == agency_id)
        if industry_id:
            query = query.filter(Bid.industry_id == industry_id)
        rows = query.all()
        # 이상치 제거: 사정율 0.8 ~ 1.05 범위만 유효
        values = [float(r.srate) for r in rows if r.srate and 0.80 <= float(r.srate) <= 1.05]
        if not values:
            return {"bins": [], "mode": None, "p25": None, "p50": None, "p75": None, "mean": None, "std": None, "sample_count": 0}
        arr = np.array(values)
        # bins: 80.0% ~ 105.0%, 0.1% 간격 (소수점 3자리)
        bins_range = np.arange(0.800, 1.051, 0.001)
        counts, edges = np.histogram(arr, bins=bins_range)
        bins = [{"rate_pct": round(float(edges[i]), 4), "count": int(counts[i])} for i in range(len(counts))]
        mode_idx = int(np.argmax(counts))
        return {
            "bins": bins,
            "mode": round(float(edges[mode_idx]), 4) if counts[mode_idx] > 0 else None,
            "p25": round(float(np.percentile(arr, 25)), 4),
            "p50": round(float(np.percentile(arr, 50)), 4),
            "p75": round(float(np.percentile(arr, 75)), 4),
            "mean": round(float(np.mean(arr)), 4),
            "std": round(float(np.std(arr)), 4),
            "sample_count": len(values)
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
# 하이브리드 추천 서비스 (v2)
# ==================================================

class HybridRecommendService:
    """
    4개 엔진 앙상블:
      A: 사정율 예측 (LightGBM Quantile)
      B: 역사 패턴 낙찰률 예측 (기존 XGBoost)
      C: 동적 경쟁강도 분석
      D: 시장 변동성/추세 분석
    """

    def recommend_v2(self, db: Session, req, user_id: int = None) -> dict:

        bid_date = getattr(req, "bid_open_date", None) or datetime.now()
        min_bid_rate = getattr(req, "min_bid_rate", 0.87745)

        # ── Step 1: 역사 데이터 로드 (Engine B용)
        history_df = self._load_history(db, months=24)

        # ── Step 2: Engine A+D 피처 생성
        features_a = load_srate_stats(
            db, req.agency_id, req.industry_id, req.region_id,
            req.base_amount, bid_date
        )

        # ── Step 3: Engine B 피처 생성 (기존)
        features_b = build_features(
            agency_id=req.agency_id,
            industry_id=req.industry_id,
            region_id=req.region_id,
            base_amount=req.base_amount,
            construction_period=getattr(req,"construction_period",None),
            region_restriction=False,
            bid_open_date=bid_date,
            historical_df=history_df,
        )

        # ── Step 4: Engine C 동적 경쟁강도
        features_c = compute_competition_features(
            db, req.agency_id, req.industry_id, req.base_amount,
            bid_date, req.known_competitor_ids or []
        )
        # Engine C 결과를 B 피처에 주입 (기존 고정값 대체)
        features_b["expected_competitor_count"] = features_c["expected_competitor_count"]
        features_b["competitor_strength_score"] = features_c["competitor_strength_score"]

        # ── Step 5: Engine D 시장 변동성
        features_d = compute_market_trend(db, req.agency_id, req.industry_id, bid_date)

        # ── Step 6: Engine A 사정율 예측
        ep_result = predict_srate(features_a, req.base_amount)
        srate_c   = ep_result["srate_range"]["center"]
        ep_conf   = ep_result["confidence"]

        # 사정율 예측 결과를 B 피처에 주입
        features_b["srate_pred_center"] = srate_c

        # ── Step 7: Engine B 역사 패턴 예측
        engine = get_engine()
        b_result = engine.recommend(features_b)
        b_center = b_result["rate_range"]["center"]
        b_lower  = b_result["rate_range"]["lower"]
        b_upper  = b_result["rate_range"]["upper"]

        # ── Step 8: 앙상블 결합
        w_a = min(0.40, ep_conf * 0.45)
        w_b = 1.0 - w_a

        pressure  = features_c.get("market_pressure_index", 0.4)
        comp_adj  = -(pressure - 0.5) * 0.003
        trend_adj = features_d.get("trend_adjustment", 0.0)

        srate_lo = ep_result["srate_range"]["lower"]
        srate_hi = ep_result["srate_range"]["upper"]

        ens_center = (srate_c * w_a + b_center * w_b) + comp_adj + trend_adj
        ens_lower  = (srate_lo * w_a + b_lower  * w_b) + comp_adj + trend_adj
        ens_upper  = (srate_hi * w_a + b_upper  * w_b) + comp_adj + trend_adj

        # 낙찰하한율 이상 강제
        hard_floor = max(features_c["expected_floor_rate"], min_bid_rate)
        ens_lower  = max(ens_lower,  hard_floor + 0.0005)
        ens_center = max(ens_center, ens_lower  + 0.0005)
        ens_upper  = max(ens_upper,  ens_center + 0.0005)

        # ── Step 9-pre: 경쟁사 프로파일 (시뮬레이션 입력용)
        comp_profiles = get_competitor_profiles(
            db, req.known_competitor_ids or [],
            req.agency_id, req.industry_id, bid_date
        )

        # ── Step 9: 복수예가 Monte Carlo 시뮬레이션 기반 4전략
        industry_name = self._get_industry_name(db, req.industry_id)
        srate_std_val = features_a.get("agency_srate_std") or 0.012
        if comp_profiles:
            comp_means = [p["avg_rate"] for p in comp_profiles]
            comp_stds  = [max(p["std_rate"], 0.003) for p in comp_profiles]
        else:
            comp_means, comp_stds = get_market_competitor_distributions(
                db, req.agency_id, req.industry_id, bid_date
            )
        sim_result = recommend_with_simulation(
            base_amount=req.base_amount,
            industry_name=industry_name,
            srate_center=srate_c,
            srate_std=srate_std_val,
            competitor_means=comp_means,
            competitor_stds=comp_stds,
            hard_floor=hard_floor,
            ens_center=ens_center,
            ens_upper=ens_upper,
        )
        strategies = sim_result["strategies"]

        # ── Step 10: 리스크 평가
        hhi       = features_c.get("hhi_score", 0.1)
        agg_ratio = features_c.get("aggressive_comp_ratio", 0.2)
        risk      = self._compute_risk_v2(ep_conf, pressure, hhi, agg_ratio, b_result)

        # ── Step 11: 낙찰 확률 (Monte Carlo)
        win_probs = sim_result["win_probabilities"]

        # ── Step 12: 유사 사례
        similar = self._find_similar(db, req)

        # ── Step 14: SHAP 통합 설명
        explanation = self._build_explanation_v2(
            features_a, features_b, features_c, features_d,
            b_result, ep_result, w_a, w_b
        )

        # ── Step 15: 로그 저장
        self._save_log_v2(db, req, ens_center, ens_lower, ens_upper,
                          ep_result, features_c, risk, explanation, user_id, w_a, w_b)

        return {
            "rate_range": {
                "safe_lower": round(ens_lower  - 0.003, 4),
                "lower":      round(ens_lower,   4),
                "center":     round(ens_center,  4),
                "upper":      round(ens_upper,   4),
                "safe_upper": round(ens_upper  + 0.003, 4),
            },
            "strategies":    strategies,
            "estimated_price": ep_result,
            "win_probabilities": win_probs,
            "risk":          risk,
            "competition": {
                "score":                round(features_c["competitor_strength_score"], 2),
                "pressure":             round(pressure, 4),
                "hhi":                  round(hhi, 4),
                "expected_competitors": features_c["expected_competitor_count"],
                "floor_rate":           round(hard_floor, 4),
                "aggressive_ratio":     round(agg_ratio, 4),
                "recent_winner_min":    round(features_c.get("recent_winner_min_rate", hard_floor), 4),
                "profiles":             comp_profiles,
            },
            "ensemble_weights": {"engine_a": round(w_a, 3), "engine_b": round(w_b, 3)},
            "explanation":   explanation,
            "similar_cases": similar,
            "market_trend":  features_d,
            "simulation":    sim_result["simulation"],
        }

    # ──────────────────────────────────────────
    # 내부 메서드
    # ──────────────────────────────────────────

    def _get_industry_name(self, db: Session, industry_id: int) -> str:
        from .models import Industry
        ind = db.query(Industry).filter(Industry.id == industry_id).first()
        return ind.name if ind else ""

    def _load_history(self, db: Session, months: int = 24) -> "pd.DataFrame":
        import pandas as pd
        cutoff = datetime.now() - timedelta(days=months * 30)
        rows = db.execute(text("""
            SELECT b.id, b.agency_id, b.industry_id, b.region_id,
                   b.base_amount, b.bid_open_date,
                   r.bid_rate AS winner_rate,
                   (SELECT COUNT(*) FROM bid_results r2 WHERE r2.bid_id = b.id) AS competitor_count
            FROM bids b
            LEFT JOIN bid_results r ON r.bid_id = b.id AND r.is_winner = true
            WHERE b.bid_open_date >= :cutoff AND b.status = 'closed'
        """), {"cutoff": cutoff}).fetchall()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=[
            "id","agency_id","industry_id","region_id",
            "base_amount","bid_open_date","winner_rate","competitor_count"
        ])
        df["winner_rate"]      = pd.to_numeric(df["winner_rate"],      errors="coerce")
        df["base_amount"]      = pd.to_numeric(df["base_amount"],      errors="coerce")
        df["competitor_count"] = pd.to_numeric(df["competitor_count"], errors="coerce")
        return df

    def _compute_risk_v2(self, ep_conf, pressure, hhi, agg_ratio, b_result) -> dict:
        score = (
            (1.0 - ep_conf)  * 2.5 +
            pressure         * 2.5 +
            hhi              * 2.5 +
            agg_ratio        * 2.5
        )
        level = "LOW" if score < 3 else "MEDIUM" if score < 6 else "HIGH"
        factors = []
        if ep_conf < 0.4:   factors.append(f"사정율 예측 신뢰도 낮음({ep_conf:.0%}) — 기관 데이터 부족")
        if pressure > 0.6:  factors.append(f"시장 압박 지수 높음({pressure:.2f}) — 공격적 경쟁사 다수")
        if hhi > 0.30:      factors.append(f"낙찰 집중도 높음(HHI={hhi:.3f}) — 특정 업체 우세")
        if agg_ratio > 0.4: factors.append(f"공격적 업체 비율 {agg_ratio:.0%} — 저가 투찰 경쟁 심화")
        # 기존 Engine B 리스크도 참고
        spread = b_result["rate_range"]["safe_upper"] - b_result["rate_range"]["safe_lower"]
        if spread > 0.03:   factors.append(f"낙찰률 분산 큼(범위 {spread:.2%}) — 예측 불확실성 높음")
        return {"level": level, "score": round(score, 2), "factors": factors}

    def _find_similar(self, db: Session, req) -> List[dict]:
        rows = db.query(Bid).filter(
            Bid.industry_id == req.industry_id,
            Bid.region_id   == req.region_id,
            Bid.base_amount.between(int(req.base_amount * 0.6), int(req.base_amount * 1.4)),
            Bid.status == "closed",
        ).order_by(desc(Bid.bid_open_date)).limit(5).all()
        result = []
        for b in rows:
            winner = next((r for r in b.results if r.is_winner), None)
            amt_diff = abs(b.base_amount - req.base_amount) / max(req.base_amount, 1)
            result.append({
                "bid_id": b.id, "title": b.title,
                "agency_name":     b.agency.name if b.agency else "",
                "base_amount":     b.base_amount,
                "bid_open_date":   b.bid_open_date,
                "winner_rate":     float(winner.bid_rate) if winner else None,
                "competitor_count": len(b.results),
                "similarity_score": round(max(0, 1.0 - amt_diff), 3),
            })
        return result

    def _build_explanation_v2(self, fa, fb, fc, fd, b_result, ep_result, w_a, w_b) -> dict:
        from .ml.engine import FEATURE_LABELS
        shap_b = b_result.get("shap_values", {})
        top_factors = []
        for feat, val in sorted(shap_b.items(), key=lambda x: abs(x[1]), reverse=True)[:5]:
            top_factors.append({
                "feature":    feat,
                "label":      FEATURE_LABELS.get(feat, feat),
                "shap_value": round(val, 6),
                "direction":  "positive" if val > 0 else "negative",
                "value":      round(float(fb.get(feat)), 4) if fb.get(feat) is not None else None,
            })

        parts = []
        srate_c = ep_result["srate_range"]["center"]
        ep_conf = ep_result["confidence"]
        if fa.get("agency_srate_mean"):
            parts.append(
                f"이 기관의 과거 사정율 평균은 {fa['agency_srate_mean']:.4f}이며, "
                f"예정가격은 기초금액의 약 {srate_c*100:.1f}% 수준으로 예상됩니다."
            )
        if ep_conf < 0.4:
            parts.append("사정율 예측 데이터가 부족하여 역사 패턴 비중을 높였습니다.")
        elif ep_conf > 0.7:
            parts.append(f"사정율 신뢰도 {ep_conf:.0%} — Engine A 가중치를 높여 적용했습니다.")

        pressure = fc.get("market_pressure_index", 0.4)
        if pressure > 0.6:
            parts.append(f"경쟁 압박 지수 {pressure:.2f} — 최근 공격적 투찰 업체 비율이 높습니다.")
        elif pressure < 0.3:
            parts.append(f"경쟁 압박 지수 낮음({pressure:.2f}) — 비교적 여유 있는 경쟁 환경입니다.")

        if fd.get("has_recent_data") and abs(fd.get("srate_4w_change", 0)) > 0.001:
            chg = fd["srate_4w_change"]
            direction = "상승" if chg > 0 else "하락"
            parts.append(f"최근 4주 사정율 {direction} 추세({chg:+.4f}) 반영.")

        for f in top_factors[:3]:
            direction = "높이는" if f["shap_value"] > 0 else "낮추는"
            parts.append(f"'{f['label']}'이(가) 추천 투찰률을 {direction} 주요 요인입니다.")

        base_rate_val = fb.get("agency_avg_rate_12m") or fb.get("similar_avg_rate") or 0.879
        data_count = int(fb.get("agency_bid_count_12m") or 0) + int(fb.get("similar_bid_count") or 0)

        return {
            "top_factors":   top_factors,
            "narrative_ko":  " ".join(parts) if parts else "유사 입찰 이력 기반 앙상블 추천.",
            "model_version": b_result.get("model_version", "rule-based"),
            "data_count":    data_count,
            "base_rate":     round(float(base_rate_val), 4),
        }

    def _save_log_v2(self, db, req, center, lower, upper,
                     ep_result, fc, risk, explanation, user_id, w_a, w_b):
        try:
            from .models import PredictionLogV2
            log = PredictionLogV2(
                user_id=user_id,
                engine_weights={"engine_a": w_a, "engine_b": w_b},
                input_features={
                    "agency_id":   req.agency_id,
                    "industry_id": req.industry_id,
                    "region_id":   req.region_id,
                    "base_amount": req.base_amount,
                },
                srate_pred_center = ep_result["srate_range"]["center"],
                ep_confidence     = ep_result["confidence"],
                rate_aggressive   = lower,
                rate_balanced     = center,
                rate_conservative = upper,
                rate_center       = center,
                risk_level        = risk["level"],
                risk_score        = risk["score"],
                competition_score = fc.get("competitor_strength_score"),
                hhi_score         = fc.get("hhi_score"),
                explanation_text  = explanation.get("narrative_ko",""),
            )
            db.add(log)
            db.commit()
        except Exception as e:
            logger.debug(f"v2 로그 저장 실패: {e}")
            db.rollback()


# ==================================================
# 기관 분석 서비스
# ==================================================

class AgencyAnalysisService:
    def __init__(self, db: Session):
        self.db = db

    def list_agencies(self, q: str = None, page: int = 1, size: int = 20) -> dict:
        from sqlalchemy import func as sqlfunc
        query = self.db.query(
            Agency,
            sqlfunc.count(Bid.id).label("bid_count")
        ).outerjoin(Bid, Bid.agency_id == Agency.id).group_by(Agency.id)
        if q:
            query = query.filter(Agency.name.ilike(f"%{q}%"))
        total = query.count()
        rows = query.order_by(sqlfunc.count(Bid.id).desc()).offset((page - 1) * size).limit(size).all()
        items = []
        for agency, bid_count in rows:
            region_name = None
            if agency.region_id:
                r = self.db.query(Region).filter(Region.id == agency.region_id).first()
                if r:
                    region_name = r.name
            items.append({
                "id": agency.id,
                "name": agency.name,
                "type": agency.type,
                "region_name": region_name,
                "bid_count": bid_count or 0
            })
        return {"items": items, "total": total}

    def analyze(self, agency_id: int) -> dict:
        from fastapi import HTTPException
        agency = self.db.query(Agency).filter(Agency.id == agency_id).first()
        if not agency:
            raise HTTPException(status_code=404, detail="기관을 찾을 수 없습니다")

        cutoff = datetime.utcnow() - timedelta(days=730)  # 24개월
        bids = self.db.query(Bid).filter(
            Bid.agency_id == agency_id,
            Bid.bid_open_date >= cutoff
        ).all()

        total_bids = len(bids)
        bid_ids = [b.id for b in bids]

        results = self.db.query(BidResult).filter(
            BidResult.bid_id.in_(bid_ids),
            BidResult.is_winner == True
        ).all() if bid_ids else []
        avg_win_rate = float(sum(float(r.bid_rate) for r in results) / len(results)) if results else None

        srates = [float(r.assessment_rate) for r in results if r.assessment_rate is not None]
        avg_srate = float(sum(srates) / len(srates)) if srates else None

        from collections import Counter
        industry_ids = [b.industry_id for b in bids if b.industry_id]
        dominant_industry = None
        if industry_ids:
            most_common_id = Counter(industry_ids).most_common(1)[0][0]
            ind = self.db.query(Industry).filter(Industry.id == most_common_id).first()
            dominant_industry = ind.name if ind else None

        summary = {
            "name": agency.name,
            "total_bids": total_bids,
            "avg_win_rate": avg_win_rate,
            "avg_srate": avg_srate,
            "dominant_industry": dominant_industry
        }

        # monthly_trend (24개월)
        monthly_trend = []
        for i in range(24):
            target = datetime.utcnow() - timedelta(days=30 * i)
            y, m = target.year, target.month
            month_bids = [b for b in bids if b.bid_open_date and b.bid_open_date.year == y and b.bid_open_date.month == m]
            month_bid_ids = [b.id for b in month_bids]
            month_winners = self.db.query(BidResult).filter(
                BidResult.bid_id.in_(month_bid_ids), BidResult.is_winner == True
            ).all() if month_bid_ids else []
            win_rates = [float(r.bid_rate) for r in month_winners if r.bid_rate]
            srates_m = [float(r.assessment_rate) for r in month_winners if r.assessment_rate]
            monthly_trend.append({
                "year_month": f"{y}-{m:02d}",
                "bid_count": len(month_bids),
                "win_rate": sum(win_rates) / len(win_rates) if win_rates else None,
                "avg_srate": sum(srates_m) / len(srates_m) if srates_m else None
            })
        monthly_trend.reverse()

        # srate_distribution
        all_results = self.db.query(BidResult).filter(
            BidResult.bid_id.in_(bid_ids),
            BidResult.assessment_rate.isnot(None)
        ).all() if bid_ids else []
        srate_vals = [float(r.assessment_rate) for r in all_results]
        srate_dist = self._make_distribution(srate_vals, 80, 110, 0.5)

        # top_winners
        from sqlalchemy import func as sqlfunc
        if bid_ids:
            winner_query = self.db.query(
                Competitor.name,
                sqlfunc.count(BidResult.id).label("win_count"),
                sqlfunc.avg(BidResult.bid_rate).label("avg_rate")
            ).join(BidResult, BidResult.competitor_id == Competitor.id).filter(
                BidResult.bid_id.in_(bid_ids),
                BidResult.is_winner == True
            ).group_by(Competitor.name).order_by(sqlfunc.count(BidResult.id).desc()).limit(10).all()
            top_winners = [{"competitor_name": r.name, "win_count": r.win_count, "avg_bid_rate": float(r.avg_rate) if r.avg_rate else None} for r in winner_query]
        else:
            top_winners = []

        # amount_distribution
        buckets = [
            ("1억 미만", 0, 100_000_000),
            ("1~3억", 100_000_000, 300_000_000),
            ("3~10억", 300_000_000, 1_000_000_000),
            ("10억 이상", 1_000_000_000, float("inf")),
        ]
        amount_dist = []
        for label, low, high in buckets:
            bucket_bids = [b for b in bids if b.base_amount and low <= b.base_amount < high]
            bucket_ids = [b.id for b in bucket_bids]
            bucket_winners = self.db.query(BidResult).filter(
                BidResult.bid_id.in_(bucket_ids), BidResult.is_winner == True
            ).all() if bucket_ids else []
            wrs = [float(r.bid_rate) for r in bucket_winners if r.bid_rate]
            amount_dist.append({
                "bucket_label": label,
                "count": len(bucket_bids),
                "avg_win_rate": sum(wrs) / len(wrs) if wrs else None
            })

        return {
            "summary": summary,
            "monthly_trend": monthly_trend,
            "srate_distribution": srate_dist,
            "top_winners": top_winners,
            "amount_distribution": amount_dist
        }

    def _make_distribution(self, values: list, low: float, high: float, step: float) -> dict:
        if not values:
            return {"bins": [], "mode": None, "p25": None, "p50": None, "p75": None, "mean": None, "std": None}
        arr = np.array(values)
        bins_range = np.arange(low, high + step, step)
        counts, edges = np.histogram(arr, bins=bins_range)
        bins = [{"rate_pct": float(edges[i]), "count": int(counts[i])} for i in range(len(counts))]
        mode_idx = int(np.argmax(counts))
        mode_val = float(edges[mode_idx]) if counts[mode_idx] > 0 else None
        return {
            "bins": bins,
            "mode": mode_val,
            "p25": float(np.percentile(arr, 25)),
            "p50": float(np.percentile(arr, 50)),
            "p75": float(np.percentile(arr, 75)),
            "mean": float(np.mean(arr)),
            "std": float(np.std(arr)),
            "sample_count": len(values)
        }


# ==================================================
# 경쟁사 투찰성향 분석 서비스
# ==================================================

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

class BookmarkService:
    def __init__(self, db: Session):
        self.db = db

    def add(self, bid_id: int, user_id: int, note: str = None) -> BidBookmark:
        existing = self.db.query(BidBookmark).filter(
            BidBookmark.user_id == user_id, BidBookmark.bid_id == bid_id
        ).first()
        if existing:
            return existing
        bookmark = BidBookmark(bid_id=bid_id, user_id=user_id, note=note)
        self.db.add(bookmark)
        self.db.commit()
        self.db.refresh(bookmark)
        return bookmark

    def remove(self, bid_id: int, user_id: int):
        bookmark = self.db.query(BidBookmark).filter(
            BidBookmark.user_id == user_id, BidBookmark.bid_id == bid_id
        ).first()
        if bookmark:
            self.db.delete(bookmark)
            self.db.commit()

    def list_bookmarks(self, user_id: int, page: int = 1, size: int = 20) -> dict:
        query = self.db.query(BidBookmark).filter(BidBookmark.user_id == user_id)
        total = query.count()
        items = query.order_by(BidBookmark.created_at.desc()).offset((page - 1) * size).limit(size).all()
        return {"items": items, "total": total}

    def get_bookmarked_ids(self, user_id: int, bid_ids: list) -> set:
        rows = self.db.query(BidBookmark.bid_id).filter(
            BidBookmark.user_id == user_id,
            BidBookmark.bid_id.in_(bid_ids)
        ).all()
        return {r.bid_id for r in rows}


# ==================================================
# 투찰 정확도 분석 서비스
# ==================================================

class MyBidAnalysisService:
    def __init__(self, db: Session):
        self.db = db

    def analyze(self, user_id: int) -> dict:
        from collections import defaultdict
        records = self.db.query(MyBidRecord).filter(
            MyBidRecord.user_id == user_id,
            MyBidRecord.result.in_(["won", "lost"])
        ).order_by(MyBidRecord.bid_date).all()

        if not records:
            return {
                "accuracy_stats": {"avg_error": None, "median_error": None, "accuracy_1pct": None, "accuracy_3pct": None, "total_records": 0},
                "rate_scatter": [],
                "monthly_accuracy": []
            }

        errors = []
        scatter = []
        for r in records:
            if r.submitted_rate and r.recommendation_rate:
                err = abs(float(r.submitted_rate) - float(r.recommendation_rate))
                errors.append(err)
            scatter.append({
                "submitted_rate": float(r.submitted_rate) if r.submitted_rate else 0.0,
                "recommendation_rate": float(r.recommendation_rate) if r.recommendation_rate else None,
                "result": r.result,
                "bid_date": r.bid_date.strftime("%Y-%m-%d") if r.bid_date else ""
            })

        arr = np.array(errors) if errors else np.array([])
        accuracy_stats = {
            "avg_error": float(np.mean(arr)) if len(arr) > 0 else None,
            "median_error": float(np.median(arr)) if len(arr) > 0 else None,
            "accuracy_1pct": float(np.mean(arr <= 1.0)) if len(arr) > 0 else None,
            "accuracy_3pct": float(np.mean(arr <= 3.0)) if len(arr) > 0 else None,
            "total_records": len(records)
        }

        monthly = defaultdict(lambda: {"errors": [], "win_count": 0, "total": 0})
        for r in records:
            if r.bid_date:
                key = r.bid_date.strftime("%Y-%m")
                monthly[key]["total"] += 1
                if r.result == "won":
                    monthly[key]["win_count"] += 1
                if r.submitted_rate and r.recommendation_rate:
                    monthly[key]["errors"].append(abs(float(r.submitted_rate) - float(r.recommendation_rate)))

        monthly_accuracy = [
            {
                "year_month": k,
                "mae": round(float(np.mean(v["errors"])), 4) if v["errors"] else None,
                "win_count": v["win_count"],
                "total": v["total"]
            }
            for k, v in sorted(monthly.items())
        ]

        return {
            "accuracy_stats": accuracy_stats,
            "rate_scatter": scatter,
            "monthly_accuracy": monthly_accuracy
        }

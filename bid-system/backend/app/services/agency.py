"""
기관 분석 서비스
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

    def srate_histogram(self, agency_id: int, months: int = 12) -> dict:
        from fastapi import HTTPException
        agency = self.db.query(Agency).filter(Agency.id == agency_id).first()
        if not agency:
            raise HTTPException(status_code=404, detail="기관을 찾을 수 없습니다")

        cutoff = datetime.utcnow() - timedelta(days=30 * months)
        bid_ids = [b.id for b in self.db.query(Bid).filter(
            Bid.agency_id == agency_id,
            Bid.bid_open_date >= cutoff,
        ).all()]

        results = self.db.query(BidResult).filter(
            BidResult.bid_id.in_(bid_ids),
            BidResult.is_winner == True,
            BidResult.assessment_rate.isnot(None),
        ).all() if bid_ids else []

        srate_vals = sorted([float(r.assessment_rate) for r in results])
        n = len(srate_vals)

        mean = float(np.mean(srate_vals)) if n > 0 else None
        std = float(np.std(srate_vals)) if n > 0 else None

        lo, hi, width = 0.860, 0.960, 0.005
        bins = []
        b = lo
        while b < hi - 1e-9:
            cnt = sum(1 for v in srate_vals if b <= v < b + width)
            pct = round(cnt / n * 100, 1) if n > 0 else 0.0
            bins.append({
                "range_lo": round(b, 3),
                "range_hi": round(b + width, 3),
                "count": cnt,
                "pct": pct,
            })
            b = round(b + width, 3)

        def _pct(p):
            return float(np.percentile(srate_vals, p)) if srate_vals else None

        percentiles = {
            "p10": _pct(10), "p25": _pct(25), "p50": _pct(50),
            "p75": _pct(75), "p90": _pct(90),
        }

        return {
            "agency_id": agency_id,
            "agency_name": agency.name,
            "months": months,
            "sample_count": n,
            "mean": mean,
            "std": std,
            "bins": bins,
            "percentiles": percentiles,
        }

    def recent_results(self, agency_id: int, limit: int = 20) -> dict:
        from fastapi import HTTPException
        from sqlalchemy import func as sqlfunc
        agency = self.db.query(Agency).filter(Agency.id == agency_id).first()
        if not agency:
            raise HTTPException(status_code=404, detail="기관을 찾을 수 없습니다")

        bids = self.db.query(Bid).filter(
            Bid.agency_id == agency_id,
            Bid.bid_open_date.isnot(None),
        ).order_by(Bid.bid_open_date.desc()).limit(limit * 3).all()

        items = []
        for bid in bids:
            if len(items) >= limit:
                break
            winner = self.db.query(BidResult).filter(
                BidResult.bid_id == bid.id,
                BidResult.is_winner == True,
            ).first()
            comp_count = self.db.query(sqlfunc.count(BidResult.id)).filter(
                BidResult.bid_id == bid.id,
            ).scalar() or 0
            items.append({
                "bid_id": bid.id,
                "title": bid.title,
                "base_amount": float(bid.base_amount) if bid.base_amount else 0.0,
                "bid_open_date": bid.bid_open_date.isoformat() if bid.bid_open_date else None,
                "assessment_rate": float(winner.assessment_rate) if winner and winner.assessment_rate else None,
                "competitor_count": comp_count,
            })

        return {"items": items, "total": len(items)}

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


# ============================================================
# 수주율 최적화 서비스 레이어
# ============================================================

class CompanyProfileService:
    """회사 프로파일 CRUD + 역량 조회"""

    def get_profile(self, db: Session, user_id: int):
        from ..models import CompanyProfile
        return db.query(CompanyProfile).first()

    def upsert_profile(self, db: Session, data: dict) -> "CompanyProfile":
        from ..models import CompanyProfile
        profile = db.query(CompanyProfile).first()
        if profile is None:
            profile = CompanyProfile(**data)
            db.add(profile)
        else:
            for k, v in data.items():
                setattr(profile, k, v)
        db.commit()
        db.refresh(profile)
        return profile

    def get_remaining_bond(self, db: Session) -> dict:
        from ..models import CompanyProfile, PortfolioState
        profile = db.query(CompanyProfile).first()
        if not profile:
            return {"total": 0, "used": 0, "remaining": 0, "usage_rate": 0.0}

        # 현재 ACTIVE 상태 포트폴리오 보증 소요액 합산
        active_bond = db.query(func.sum(PortfolioState.bond_exposure)).filter(
            PortfolioState.status == "ACTIVE"
        ).scalar() or 0

        total   = profile.bond_limit_total or 0
        used    = int(active_bond)
        remaining = max(0, total - used)
        rate    = used / total if total > 0 else 0.0
        return {"total": total, "used": used, "remaining": remaining, "usage_rate": round(rate, 4)}

class QualificationService:
    """E2: 적격심사 엔진 서비스"""

    def check(
        self,
        db: Session,
        bid_id: int,
        user_id: int,
        our_share_rate: float = 1.0,
        our_experience: int = 0,
        reputation_score: float = 0.0,
        contract_law: str = "local",
    ) -> dict:
        from ..models import Bid, QualificationCheck, CompanyProfile
        from ..ml.qualification import check_qualification, QualificationResult
        from ..ml.assessment import predict_srate, load_srate_stats

        bid = db.query(Bid).filter(Bid.id == bid_id).first()
        if not bid:
            from fastapi import HTTPException
            raise HTTPException(404, "공고를 찾을 수 없습니다")

        profile = db.query(CompanyProfile).first()

        # 사정율 예측 (중앙값 + 표준편차)
        features_a   = load_srate_stats(db, bid.agency_id, bid.industry_id, bid.region_id, bid.base_amount)
        srate_result = predict_srate(features_a, bid.base_amount)
        _rng         = srate_result["srate_range"]
        srate_center = _rng["center"]
        srate_std    = (_rng["upper"] - _rng["lower"]) / 2

        result: QualificationResult = check_qualification(
            base_amount=bid.base_amount,
            estimated_price_center=srate_center,
            estimated_price_std=srate_std,
            our_experience=our_experience or (profile.performance_records.get("total", 0) if profile else 0),
            annual_revenue=profile.annual_revenue if profile else 0,
            workforce_count=profile.workforce_count if profile else 0,
            share_rate=our_share_rate,
            reputation_score=reputation_score,
            contract_law=contract_law,
        )

        # DB 저장
        check = QualificationCheck(
            bid_id=bid_id,
            user_id=user_id,
            our_share_rate=our_share_rate,
            our_experience=our_experience,
            pass_prob=result.pass_prob,
            min_pass_amount=result.min_pass_amount,
            max_pass_amount=result.max_pass_amount,
            score_breakdown=result.score_breakdown,
            verdict=result.verdict,
            fail_reason=result.fail_reason,
        )
        db.add(check)
        db.commit()

        return {
            "bid_id":          bid_id,
            "verdict":         result.verdict,
            "pass_prob":       result.pass_prob,
            "min_pass_amount": result.min_pass_amount,
            "max_pass_amount": result.max_pass_amount,
            "score_breakdown": result.score_breakdown,
            "fail_reason":     result.fail_reason,
            "criteria_type":   result.criteria_type,
        }

class AgencyYegaService:
    """발주처 특화 예가 번호 빈도 패턴 분석."""

    def __init__(self, db: Session):
        self.db = db

    def get_pattern(self, agency_id: int, industry_id: Optional[int] = None, months: int = 12) -> dict:
        from ..ml.yega import get_agency_yega_pattern

        # inpo21c 실측 데이터 우선 (역산 방식보다 정확)
        try:
            direct = get_inpo21c_pattern_direct(self.db, agency_id)
            if direct.get("sample_count", 0) >= 3:
                return {**direct, "source": "inpo21c_direct"}
        except Exception:
            pass

        cutoff = datetime.utcnow() - timedelta(days=months * 30)

        query = (
            self.db.query(
                BidResult.assessment_rate,
                Bid.base_amount,
                Bid.a_value,
            )
            .join(Bid, BidResult.bid_id == Bid.id)
            .filter(
                Bid.agency_id == agency_id,
                BidResult.assessment_rate.isnot(None),
                Bid.bid_open_date >= cutoff,
            )
        )

        if industry_id:
            query = query.filter(Bid.industry_id == industry_id)

        rows = query.limit(500).all()

        bid_data = [
            {
                "assessment_rate": float(r.assessment_rate),
                "base_amount":     int(r.base_amount),
                "a_value":         int(r.a_value) if r.a_value else None,
            }
            for r in rows
        ]

        result = get_agency_yega_pattern(bid_data)
        return {**result, "source": "reverse_calc"}


# ==================================================
# 공동도급 적격심사 매칭 서비스
# ==================================================

class JointQualService:
    """공동도급 파트너 적격심사 AI 매칭.
    경쟁사 DB 기반으로 협정 가능 업체를 탐색하고 적격 여부를 추정한다.
    실제 실적 데이터 없이 낙찰 이력을 프록시로 사용하는 간소화 모델.
    """

    _MIN_PARTNER_RATE = 0.30  # 부계약자 최소 참여지분율 (건설산업기본법)

    def __init__(self, db: Session):
        self.db = db

    def find_matching_partners(
        self,
        bid_id: int,
        user_track_amount: float,
        participation_rate: float = 0.6,
    ) -> dict:
        from fastapi import HTTPException
        from sqlalchemy import func as sqlfunc

        bid = self.db.query(Bid).filter(Bid.id == bid_id).first()
        if not bid:
            raise HTTPException(status_code=404, detail="공고를 찾을 수 없습니다")

        base_amount = bid.base_amount or 0
        min_bid_rate = float(bid.min_bid_rate or 0.87745)
        partner_rate = max(1.0 - participation_rate, self._MIN_PARTNER_RATE)
        min_bid_amount = int(base_amount * min_bid_rate * participation_rate)

        threshold_note = (
            f"기초금액 {base_amount:,}원 기준 — "
            f"파트너 최소 지분 {partner_rate:.0%}, "
            f"귀사 최소 투찰금액 약 {min_bid_amount:,}원"
        )

        # 최근 24개월 CompetitorStat 집계
        cutoff_year = (datetime.now() - timedelta(days=730)).year
        stats_subq = (
            self.db.query(
                CompetitorStat.competitor_id,
                sqlfunc.sum(CompetitorStat.total_bid_count).label("total_bids"),
                sqlfunc.sum(CompetitorStat.win_count).label("win_count"),
                sqlfunc.avg(CompetitorStat.avg_bid_rate).label("avg_rate"),
            )
            .filter(CompetitorStat.period_year >= cutoff_year)
            .group_by(CompetitorStat.competitor_id)
            .subquery()
        )

        rows = (
            self.db.query(Competitor, stats_subq.c.total_bids, stats_subq.c.win_count, stats_subq.c.avg_rate)
            .outerjoin(stats_subq, Competitor.id == stats_subq.c.competitor_id)
            .limit(500)
            .all()
        )

        partners = []
        for competitor, _tb, _wc, _ar in rows:
            total_bids = int(_tb or 0) if _tb is not None else 0
            win_count  = int(_wc or 0) if _wc is not None else 0
            avg_rate   = float(_ar or 0) if _ar is not None else 0.0
            win_rate = win_count / total_bids if total_bids > 0 else 0.0

            # 적격심사 통과 예상: 낙찰 이력 존재 + 최소 입찰 건수 기준
            qualification_ok = win_count >= 1 and total_bids >= 3

            # 궁합 점수 (안정성·실적·활동성)
            stability  = 40.0 if qualification_ok else 8.0
            perf       = min(win_rate / 0.3, 1.0) * 25
            activity   = min(total_bids / 50, 1.0) * 15
            compat     = round(stability + perf + activity, 1)

            partners.append({
                "competitor_id":    competitor.id,
                "name":             competitor.name,
                "biz_reg_no":       competitor.biz_reg_no,
                "joint_min_rate":   round(partner_rate, 2),
                "qualification_ok": qualification_ok,
                "win_rate":         round(win_rate, 4),
                "total_bids":       total_bids,
                "avg_bid_rate":     round(avg_rate, 4) if avg_rate else None,
                "compat_score":     compat,
            })

        # 적격 업체 우선, 궁합 점수 내림차순 정렬
        partners.sort(key=lambda x: (-int(x["qualification_ok"]), -x["compat_score"]))
        partners = partners[:50]

        return {
            "partners":       partners,
            "bid_title":      bid.title,
            "base_amount":    base_amount,
            "threshold_note": threshold_note,
        }


# ==================================================
# 공동도급 적격심사 시뮬레이터
# ==================================================

class JointSimulateService:
    """공동도급 파트너 구성 + 지분율 조합으로 심사통과 여부 및 최저 투찰가 계산."""

    # 기초금액 구간별 적격심사 기준점수 (간소화 모델)
    _THRESHOLD_TABLE = [
        (300_000_000,    12.0),   # 3억 미만
        (3_000_000_000,  14.0),   # 30억 미만
        (10_000_000_000, 16.0),   # 100억 미만
        (float("inf"),   18.0),   # 100억 이상
    ]

    def __init__(self, db: Session):
        self.db = db

    def simulate(self, bid_id: int, partners: list) -> dict:
        from fastapi import HTTPException

        bid = self.db.query(Bid).filter(Bid.id == bid_id).first()
        if not bid:
            raise HTTPException(status_code=404, detail="공고를 찾을 수 없습니다")

        base_amount  = int(bid.base_amount or 0)
        min_bid_rate = float(bid.min_bid_rate or 0.87745)

        # 기초금액에 맞는 기준점수 결정
        threshold = 18.0
        for limit, t in self._THRESHOLD_TABLE:
            if base_amount < limit:
                threshold = t
                break

        cutoff_year = (datetime.now() - timedelta(days=730)).year

        partner_results = []
        for p in partners:
            competitor_id      = p.get("competitor_id")
            user_track         = p.get("user_track")
            participation_rate = float(p.get("participation_rate", 0.0))

            if competitor_id:
                # 경쟁사 DB 조회
                stats_row = (
                    self.db.query(
                        func.sum(CompetitorStat.total_bid_count).label("total_bids"),
                        func.sum(CompetitorStat.win_count).label("win_count"),
                        func.avg(CompetitorStat.avg_bid_rate).label("avg_rate"),
                    )
                    .filter(
                        CompetitorStat.competitor_id == competitor_id,
                        CompetitorStat.period_year >= cutoff_year,
                    )
                    .first()
                )
                competitor = self.db.query(Competitor).filter(Competitor.id == competitor_id).first()
                name       = competitor.name if competitor else f"업체 #{competitor_id}"

                total_bids = int(stats_row.total_bids or 0) if stats_row else 0
                win_count  = int(stats_row.win_count  or 0) if stats_row else 0
                avg_rate   = float(stats_row.avg_rate or 0.87) if stats_row else 0.87

                # 낙찰 이력으로 시공실적 추정
                track_amount = int(base_amount * avg_rate * win_count)

                if win_count >= 1 and total_bids >= 3:
                    win_rate   = win_count / total_bids
                    perf_score = 8.0 + min(win_rate / 0.3, 1.0) * 6.0 + min(total_bids / 30, 1.0) * 6.0
                else:
                    perf_score = 4.0

            else:
                # 귀사
                name         = "귀사"
                track_amount = int(user_track or 0)
                ratio        = track_amount / base_amount if base_amount > 0 else 0
                perf_score   = min(20.0, 5.0 + ratio * 15.0)

            qual_score     = round(perf_score * participation_rate, 2)
            partner_passes = perf_score >= 8.0  # 개별 최소 충족 기준

            partner_results.append({
                "name":               name,
                "participation_rate": participation_rate,
                "track_amount":       track_amount,
                "qual_score":         qual_score,
                "passes":             partner_passes,
            })

        total_qual_score    = round(sum(r["qual_score"] for r in partner_results), 2)
        joint_passes        = total_qual_score >= threshold
        bid_amount_required = int(base_amount * min_bid_rate)
        margin              = int(bid_amount_required * 0.003)

        return {
            "bid_id":              bid_id,
            "bid_amount_required": bid_amount_required,
            "partners":            partner_results,
            "joint_result": {
                "passes":           joint_passes,
                "total_qual_score": total_qual_score,
                "threshold":        threshold,
                "min_bid_amount":   bid_amount_required,
                "min_bid_rate":     round(min_bid_rate, 4),
                "margin":           margin,
            },
        }


# ==================================================
# 발주기관 예산 집행 패턴 — 급증 시점 예측
# ==================================================

def rebuild_agency_budget_patterns(db: Session) -> dict:
    """
    기관별 월별 발주 패턴 재계산 → agency_budget_patterns upsert.

    surge_index = 해당 월 평균 건수 / (연간 평균 건수/12)
    · 1.0 = 평균, 1.5+ = 급증, 0.6- = 비수기
    최소 2년치 데이터가 있는 기관만 계산.
    """
    import time
    t0 = time.monotonic()

    result = db.execute(text("""
        WITH monthly_stats AS (
            SELECT
                agency_id,
                EXTRACT(YEAR FROM bid_open_date)::int  AS yr,
                EXTRACT(MONTH FROM bid_open_date)::int AS mo,
                COUNT(*)                                AS cnt,
                SUM(base_amount)                        AS amt
            FROM bids
            WHERE bid_open_date BETWEEN '2021-01-01' AND NOW()
              AND base_amount > 0
            GROUP BY agency_id, yr, mo
        ),
        agency_year_counts AS (
            SELECT agency_id, COUNT(DISTINCT yr) AS years_cnt
            FROM monthly_stats
            GROUP BY agency_id
            HAVING COUNT(DISTINCT yr) >= 2
        ),
        monthly_avg AS (
            SELECT
                ms.agency_id,
                ms.mo,
                ROUND(AVG(ms.cnt)::numeric, 2)           AS avg_cnt,
                ROUND(AVG(ms.amt)::numeric)::bigint       AS avg_amt,
                ayc.years_cnt
            FROM monthly_stats ms
            JOIN agency_year_counts ayc ON ayc.agency_id = ms.agency_id
            GROUP BY ms.agency_id, ms.mo, ayc.years_cnt
        ),
        agency_annual_avg AS (
            SELECT agency_id, SUM(avg_cnt) / 12.0 AS annual_monthly_avg
            FROM monthly_avg
            GROUP BY agency_id
        )
        INSERT INTO agency_budget_patterns
            (agency_id, month_of_year, avg_bid_count, avg_bid_amount, surge_index, years_of_data, updated_at)
        SELECT
            ma.agency_id,
            ma.mo,
            ma.avg_cnt,
            ma.avg_amt,
            ROUND(
                CASE WHEN aaa.annual_monthly_avg > 0
                     THEN ma.avg_cnt / aaa.annual_monthly_avg
                     ELSE 1.0 END::numeric, 3),
            ma.years_cnt,
            NOW()
        FROM monthly_avg ma
        JOIN agency_annual_avg aaa ON aaa.agency_id = ma.agency_id
        ON CONFLICT (agency_id, month_of_year) DO UPDATE SET
            avg_bid_count  = EXCLUDED.avg_bid_count,
            avg_bid_amount = EXCLUDED.avg_bid_amount,
            surge_index    = EXCLUDED.surge_index,
            years_of_data  = EXCLUDED.years_of_data,
            updated_at     = NOW()
    """))
    db.commit()
    elapsed = round(time.monotonic() - t0, 1)
    logger.info("agency_budget_patterns upsert: rows=%d elapsed=%.1fs", result.rowcount, elapsed)
    return {"upserted": result.rowcount, "elapsed_s": elapsed}


def get_upcoming_surge_agencies(
    db: Session,
    months_ahead: int = 3,
    min_surge_index: float = 1.3,
    size: int = 50,
    industry_ids: list[int] | None = None,
) -> dict:
    """
    향후 N개월에 발주 급증이 예상되는 기관 목록.

    surge_index >= min_surge_index인 기관을 해당 월별로 묶어 반환.
    industry_ids 필터는 bids.industry_id 기준.
    """
    from datetime import date
    today = date.today()
    target_months = []
    for delta in range(1, months_ahead + 1):
        m = (today.month - 1 + delta) % 12 + 1
        y = today.year + ((today.month - 1 + delta) // 12)
        target_months.append((y, m))

    month_numbers = list({m for _, m in target_months})

    industry_clause = ""
    if industry_ids:
        ids_str = ",".join(str(i) for i in industry_ids if str(i).isdigit())
        industry_clause = f"AND b_last.industry_id IN ({ids_str})"

    rows = db.execute(text(f"""
        WITH last_bid AS (
            SELECT DISTINCT ON (b.agency_id)
                b.agency_id,
                b.industry_id,
                b.bid_open_date
            FROM bids b
            WHERE b.bid_open_date IS NOT NULL
            ORDER BY b.agency_id, b.bid_open_date DESC
        )
        SELECT
            abp.agency_id,
            a.name         AS agency_name,
            abp.month_of_year,
            abp.surge_index,
            abp.avg_bid_count,
            abp.avg_bid_amount,
            abp.years_of_data
        FROM agency_budget_patterns abp
        JOIN agencies a ON a.id = abp.agency_id
        JOIN last_bid b_last ON b_last.agency_id = abp.agency_id
        WHERE abp.month_of_year IN :months
          AND abp.surge_index >= :min_si
          AND abp.avg_bid_count >= 1.0
          {industry_clause}
        ORDER BY abp.surge_index DESC, abp.avg_bid_amount DESC
        LIMIT :sz
    """), {
        "months": tuple(month_numbers),
        "min_si": min_surge_index,
        "sz": size,
    }).fetchall()

    # 월별로 그룹핑
    from collections import defaultdict
    by_month: dict[int, list] = defaultdict(list)
    for r in rows:
        by_month[r.month_of_year].append({
            "agency_id":      r.agency_id,
            "agency_name":    r.agency_name,
            "surge_index":    float(r.surge_index),
            "avg_bid_count":  float(r.avg_bid_count),
            "avg_bid_amount": r.avg_bid_amount,
            "years_of_data":  r.years_of_data,
        })

    forecast = []
    for y, m in target_months:
        forecast.append({
            "year":        y,
            "month":       m,
            "label":       f"{y}년 {m}월",
            "agencies":    by_month.get(m, [])[:size],
        })

    return {
        "forecast":        forecast,
        "months_ahead":    months_ahead,
        "min_surge_index": min_surge_index,
    }


# ==================================================
# 최종 투찰 추천 종합 서비스
# ==================================================

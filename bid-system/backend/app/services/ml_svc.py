"""
ML 추론 서비스
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

class OpportunityScoreService:
    """
    신규 공고에 대해 내게 유리한 정도를 0~100점으로 산출.
    점수 구성:
      - 경쟁 약함 (40점): HHI 낮고 경쟁자 수 적을수록
      - 내 이력 (30점): 이 발주처에서 본인 낙찰 이력 있을수록
      - 시장 추세 (15점): 최근 낙찰율 상승 추세
      - 금액 적합 (15점): 내가 자주 참여하는 금액 구간
    """

    def __init__(self, db: Session):
        self.db = db

    def score(self, bid_id: int, user_id: int) -> dict:
        bid = self.db.query(Bid).filter(Bid.id == bid_id).first()
        if not bid:
            return {"score": None, "error": "공고를 찾을 수 없습니다."}

        agency_score  = self._agency_track_score(user_id, bid.agency_id, bid.agency)
        comp_score    = self._competition_score(bid)
        trend_score   = self._trend_score(bid)
        amount_score  = self._amount_fit_score(user_id, bid.base_amount)

        total = (comp_score["pts"] + agency_score["pts"] +
                 trend_score["pts"] + amount_score["pts"])
        total = round(min(100, max(0, total)), 1)

        grade = "A" if total >= 75 else "B" if total >= 55 else "C" if total >= 35 else "D"

        return {
            "bid_id": bid_id,
            "score": total,
            "grade": grade,
            "breakdown": {
                "competition":    comp_score,
                "personal_track": agency_score,
                "market_trend":   trend_score,
                "amount_fit":     amount_score,
            },
            "recommendation": self._grade_message(grade, comp_score, agency_score),
        }

    def get_top_recommended(self, user_id: int, limit: int = 5) -> list:
        """7일 이내 개찰 예정 open 공고 중 점수 상위 limit개 반환."""
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=7)

        q = self.db.query(Bid).filter(
            Bid.status == "open",
            Bid.bid_open_date >= now,
            Bid.bid_open_date <= cutoff,
        )

        active_ids = get_active_industry_ids(self.db)
        if active_ids is not None:
            if not active_ids:
                return []
            q = q.filter(Bid.industry_id.in_(active_ids))

        bids = q.all()

        results = []
        for bid in bids:
            scored = self.score(bid.id, user_id)
            if scored.get("error"):
                continue
            results.append({
                "bid_id": bid.id,
                "title": bid.title,
                "agency_name": bid.agency.name if bid.agency else "",
                "score": scored["score"],
                "grade": scored["grade"],
                "open_date": bid.bid_open_date.isoformat() if bid.bid_open_date else None,
                "base_amount": bid.base_amount,
                "score_breakdown": scored["breakdown"],
            })

        results.sort(key=lambda x: (x["score"] or 0), reverse=True)
        return results[:limit]

    def _competition_score(self, bid: "Bid") -> dict:
        # 최근 해당 발주처 + 업종 낙찰 데이터로 경쟁강도 추정
        cutoff = datetime.now(timezone.utc) - timedelta(days=180)
        rows = self.db.execute(text("""
            SELECT COUNT(r.id) as comp_count
            FROM bids b
            JOIN bid_results r ON r.bid_id = b.id
            WHERE b.agency_id = :aid AND b.industry_id = :iid
              AND b.bid_open_date >= :cutoff AND b.status = 'closed'
            GROUP BY b.id
        """), {"aid": bid.agency_id, "iid": bid.industry_id, "cutoff": cutoff}).fetchall()

        if not rows:
            pts = 25.0
            note = "경쟁 데이터 없음 (중간값 적용)"
        else:
            avg_comp = float(np.mean([r.comp_count for r in rows]))
            # 경쟁자 수 적을수록 좋음: 5명 이하 = 40pt, 15명 이상 = 5pt
            pts = max(5.0, 40.0 - (avg_comp - 1) * 2.5)
            pts = min(40.0, pts)
            note = f"최근 6개월 평균 경쟁사 {avg_comp:.1f}명"

        return {"pts": round(pts, 1), "max": 40, "note": note}

    def _agency_track_score(self, user_id: int, agency_id: int, agency) -> dict:
        if not agency:
            return {"pts": 0.0, "max": 30, "note": "발주처 정보 없음"}

        agency_name = agency.name if hasattr(agency, "name") else ""
        total = self.db.query(func.count(MyBidRecord.id)).filter(
            MyBidRecord.user_id == user_id,
            MyBidRecord.agency_name.ilike(f"%{agency_name[:10]}%"),
        ).scalar() or 0

        won = self.db.query(func.count(MyBidRecord.id)).filter(
            MyBidRecord.user_id == user_id,
            MyBidRecord.agency_name.ilike(f"%{agency_name[:10]}%"),
            MyBidRecord.result == "won",
        ).scalar() or 0

        if total == 0:
            pts, note = 15.0, "이 발주처 참여 이력 없음 (중간값)"
        elif won == 0:
            pts = max(5.0, 15.0 - total * 0.5)
            note = f"참여 {total}건 / 낙찰 0건"
        else:
            win_rate = won / total
            pts = 15.0 + win_rate * 15.0
            note = f"참여 {total}건 / 낙찰 {won}건 ({win_rate:.0%})"

        return {"pts": round(min(30.0, pts), 1), "max": 30, "note": note}

    def _trend_score(self, bid: "Bid") -> dict:
        cutoff = datetime.now(timezone.utc) - timedelta(days=60)
        prev   = datetime.now(timezone.utc) - timedelta(days=120)
        rows = self.db.execute(text("""
            SELECT b.bid_open_date, r.bid_rate
            FROM bids b
            JOIN bid_results r ON r.bid_id = b.id AND r.is_winner = true
            WHERE b.agency_id = :aid AND b.industry_id = :iid
              AND b.bid_open_date >= :prev AND b.status = 'closed'
        """), {"aid": bid.agency_id, "iid": bid.industry_id, "prev": prev}).fetchall()

        if len(rows) < 4:
            return {"pts": 8.0, "max": 15, "note": "추세 데이터 부족"}

        recent = [float(r.bid_rate) for r in rows if r.bid_open_date >= cutoff]
        older  = [float(r.bid_rate) for r in rows if r.bid_open_date < cutoff]

        if not recent or not older:
            return {"pts": 8.0, "max": 15, "note": "추세 계산 불가"}

        diff = np.mean(recent) - np.mean(older)
        # 낙찰률 상승은 예가 가까워짐 → 진입 기회
        if diff > 0.002:
            pts, note = 15.0, f"최근 낙찰률 상승 추세 (+{diff*100:.2f}%)"
        elif diff < -0.002:
            pts, note = 5.0,  f"최근 낙찰률 하락 추세 ({diff*100:.2f}%)"
        else:
            pts, note = 10.0, "낙찰률 안정적"

        return {"pts": pts, "max": 15, "note": note}

    def _amount_fit_score(self, user_id: int, base_amount: int) -> dict:
        rows = self.db.query(MyBidRecord.base_amount).filter(
            MyBidRecord.user_id == user_id,
            MyBidRecord.base_amount.isnot(None),
            MyBidRecord.base_amount > 0,
        ).all()

        if not rows:
            return {"pts": 8.0, "max": 15, "note": "금액 이력 없음"}

        amounts = [r.base_amount for r in rows]
        p10, p90 = np.percentile(amounts, 10), np.percentile(amounts, 90)

        if p10 <= base_amount <= p90:
            pts, note = 15.0, f"자주 참여하는 금액 구간 ({base_amount/1e6:.0f}백만원)"
        elif base_amount < p10:
            ratio = base_amount / max(p10, 1)
            pts = max(5.0, 15.0 * ratio)
            note = f"평소보다 소액 ({base_amount/1e6:.0f}백만원)"
        else:
            ratio = p90 / max(base_amount, 1)
            pts = max(5.0, 15.0 * ratio)
            note = f"평소보다 고액 ({base_amount/1e6:.0f}백만원)"

        return {"pts": round(pts, 1), "max": 15, "note": note}

    def _grade_message(self, grade: str, comp: dict, track: dict) -> str:
        if grade == "A":
            return "낙찰 가능성이 높은 유망 공고입니다. 적극 참여를 추천합니다."
        elif grade == "B":
            return "참여 가능한 공고입니다. 요율 전략 수립 후 참여하세요."
        elif grade == "C":
            if comp["pts"] < 20:
                return "경쟁이 치열한 공고입니다. 신중하게 참여 여부를 검토하세요."
            return "발주처 이력이 부족합니다. 정보 수집 후 참여 여부를 결정하세요."
        else:
            return "불리한 조건의 공고입니다. 다른 공고를 우선 검토하세요."





# ==================================================
# G2B 개찰 결과 자동 연계 서비스
# ==================================================

class WinPatternService:
    """
    my_bid_records를 분석해 편향 방향·패배 원인·발주처별 승률을 반환.
    rate_diff = submitted_rate - actual_winner_rate (소수점 기준)
    양수 = 낙찰자보다 높게 투찰(above), 음수 = 낮게 투찰(below).
    """

    BIAS_THRESHOLD = 0.003  # 0.3%p 이상이면 편향 있음

    def __init__(self, db: Session):
        self.db = db

    def analyze(self, user_id: int) -> dict:
        from collections import defaultdict

        total = self.db.query(MyBidRecord).filter(MyBidRecord.user_id == user_id).count()

        records = (
            self.db.query(MyBidRecord)
            .filter(
                MyBidRecord.user_id == user_id,
                MyBidRecord.result.in_(["won", "lost"]),
                MyBidRecord.actual_winner_rate.isnot(None),
                MyBidRecord.submitted_rate.isnot(None),
            )
            .all()
        )

        won_count = sum(1 for r in records if r.result == "won")
        lost_count = sum(1 for r in records if r.result == "lost")
        overall_win_rate = round(won_count / max(won_count + lost_count, 1) * 100, 2)

        diffs = []
        for r in records:
            if r.rate_diff is not None:
                diffs.append(float(r.rate_diff))
            elif r.submitted_rate and r.actual_winner_rate:
                diffs.append(float(r.submitted_rate) - float(r.actual_winner_rate))

        mean_diff = round(float(np.mean(diffs)), 6) if diffs else None
        bias = self._compute_bias(mean_diff)

        return {
            "total": total,
            "won": won_count,
            "lost": lost_count,
            "overall_win_rate": overall_win_rate,
            "bias": bias,
            "by_agency": self._by_agency(records),
            "by_industry": [],
            "by_year": self._by_year(records),
            "loss_reasons": self._loss_reasons([r for r in records if r.result == "lost"]),
        }

    def _compute_bias(self, mean_diff: Optional[float]) -> dict:
        if mean_diff is None:
            return {"rate_diff_mean": None, "direction": "balanced", "signal": "분석 데이터 없음"}
        direction = "above" if mean_diff > 0 else "below" if mean_diff < 0 else "balanced"
        has_bias = abs(mean_diff) > self.BIAS_THRESHOLD
        pct_str = f"{abs(mean_diff * 100):.2f}%p"
        if not has_bias:
            signal = "편향 없음 — 균형적으로 투찰하는 경향"
        elif direction == "above":
            signal = f"평균 {pct_str} 높게 투찰하는 경향 — 낮게 조정 권장"
        else:
            signal = f"평균 {pct_str} 낮게 투찰하는 경향 — 높게 조정 권장"
        return {"rate_diff_mean": mean_diff, "direction": direction, "signal": signal}

    def _by_agency(self, records: list) -> list:
        from collections import defaultdict
        agency_map: dict = defaultdict(lambda: {"total": 0, "won": 0, "diffs": []})
        for r in records:
            if not r.agency_name:
                continue
            agency_map[r.agency_name]["total"] += 1
            if r.result == "won":
                agency_map[r.agency_name]["won"] += 1
            diff = float(r.rate_diff) if r.rate_diff is not None else (
                float(r.submitted_rate) - float(r.actual_winner_rate)
                if r.submitted_rate and r.actual_winner_rate else None
            )
            if diff is not None:
                agency_map[r.agency_name]["diffs"].append(diff)
        return [
            {
                "agency_name": name,
                "total": v["total"],
                "won": v["won"],
                "win_rate": round(v["won"] / max(v["total"], 1) * 100, 1),
                "avg_rate_diff": round(float(np.mean(v["diffs"])), 4) if v["diffs"] else None,
            }
            for name, v in sorted(agency_map.items(), key=lambda x: -x[1]["total"])
        ]

    def _by_year(self, records: list) -> list:
        from collections import defaultdict
        year_map: dict = defaultdict(lambda: {"total": 0, "won": 0})
        for r in records:
            if r.bid_date:
                y = r.bid_date.year
                year_map[y]["total"] += 1
                if r.result == "won":
                    year_map[y]["won"] += 1
        return [
            {
                "year": year,
                "total": v["total"],
                "won": v["won"],
                "win_rate": round(v["won"] / max(v["total"], 1) * 100, 1),
            }
            for year, v in sorted(year_map.items())
        ]

    def _loss_reasons(self, lost_records: list) -> dict:
        above_winner = 0
        below_floor = 0
        below_winner = 0
        bid_ids = [r.bid_id for r in lost_records if r.bid_id is not None]
        floor_map: dict[int, Optional[float]] = {}
        if bid_ids:
            bids = self.db.query(Bid).filter(Bid.id.in_(bid_ids)).all()
            floor_map = {b.id: float(b.min_bid_rate) if b.min_bid_rate else None for b in bids}
        for r in lost_records:
            diff = float(r.rate_diff) if r.rate_diff is not None else (
                float(r.submitted_rate) - float(r.actual_winner_rate)
                if r.submitted_rate and r.actual_winner_rate else None
            )
            if diff is None:
                continue
            if diff > 0:
                above_winner += 1
            else:
                floor_rate = floor_map.get(r.bid_id) if r.bid_id else None
                if floor_rate and r.submitted_rate and float(r.submitted_rate) < floor_rate:
                    below_floor += 1
                else:
                    below_winner += 1
        return {"above_winner": above_winner, "below_floor": below_floor, "below_winner": below_winner}

class ActualWinZoneService:
    """inpo21c_participants의 낙찰자 투찰률 실측 분포 산출."""

    def get(self, db: Session, bid_id: int) -> dict:
        bid = db.query(Bid).filter(Bid.id == bid_id).first()
        if not bid:
            return {"zones": [], "sample_count": 0}

        # 유사 공고(같은 발주처 or 공종) 낙찰율 분포
        agency_name = bid.agency.name if bid.agency else None
        industry_id = bid.industry_id

        rows = db.execute(text("""
            SELECT ip.bid_rate::numeric
            FROM inpo21c_participants ip
            JOIN inpo21c_bids ib USING (inpo21c_bid_id)
            JOIN agencies a ON a.name = ib.agency_name
            WHERE ip.is_winner = TRUE
              AND (:agency_name IS NULL OR ib.agency_name = :agency_name)
            ORDER BY ip.bid_rate
            LIMIT 500
        """), {"agency_name": agency_name}).fetchall()

        rates = [float(r[0]) for r in rows if r[0] is not None]
        if not rates:
            return {"zones": [], "sample_count": 0, "message": "충분한 실측 데이터 없음"}

        # 0.2%p 구간으로 빈도 집계
        import math
        step = 0.002
        lo = math.floor(min(rates) / step) * step
        hi = math.ceil(max(rates) / step) * step
        buckets: dict = {}
        for rate in rates:
            key = round(math.floor(rate / step) * step, 4)
            buckets[key] = buckets.get(key, 0) + 1

        total = len(rates)
        zones = [
            {
                "range_lo":   k,
                "range_hi":   round(k + step, 4),
                "count":      v,
                "probability": round(v / total * 100, 1),
            }
            for k, v in sorted(buckets.items())
        ]

        mean_rate = round(sum(rates) / total, 5)
        peak_zone = max(zones, key=lambda z: z["count"]) if zones else None

        return {
            "sample_count": total,
            "mean_winner_rate": mean_rate,
            "peak_zone":    peak_zone,
            "zones":        zones,
            "agency_name":  agency_name,
        }


# ==================================================
# ==================================================
# 프리즘 스캔 / 예가 빈도 서비스
# ==================================================

class PrismScanService:
    """프리즘 2.0 — 구간별 낙찰확률 스캔 서비스 래퍼."""

    def scan(
        self,
        db: Session,
        base_amount: int,
        industry_name: str,
        agency_id: int,
        industry_id: int,
        n_sim: int = 20_000,
    ) -> dict:
        all_zones, top10 = scan_prism_zones(
            base_amount=base_amount,
            industry_name=industry_name,
            agency_id=agency_id,
            industry_id=industry_id,
            db=db,
            n_sim=n_sim,
        )
        scan_start = all_zones[0]["rate"] if all_zones else None
        scan_end = all_zones[-1]["rate"] if all_zones else None
        return {
            "zones": all_zones,
            "top10": top10,
            "scan_meta": {
                "scan_start":     scan_start,
                "scan_end":       scan_end,
                "scan_step":      0.001,
                "total_zones":    len(all_zones),
                "floor_ok_count": sum(1 for z in all_zones if z["floor_ok"]),
                "top_n":          10,
                "industry_name":  industry_name,
            },
        }

class YegaFrequencyService:
    """복수예가 C(15,4) 빈도 분석 서비스 래퍼."""

    def calc(
        self,
        db: Session,
        base_amount: int,
        a_value: Optional[int] = None,
        agency_id: Optional[int] = None,
    ) -> dict:
        result = calc_yega_frequency(base_amount=base_amount, a_value=a_value)
        if agency_id:
            from .agency import AgencyYegaService
            agency_pattern = AgencyYegaService(db).get_pattern(agency_id)
            result["agency_pattern"] = agency_pattern
        return result


# Hot Zone / Best Rate 서비스
# ==================================================

class HotZoneService:
    """inpo21c bid_rate 기반 Hot Zone KDE 피크 탐지 + 담합 탐지."""

    def get(self, db: Session, bid_id: int, period_type: str = "24M") -> dict:
        from ..ml.hotzone import get_hot_zones as _get_hot_zones
        from ..ml.anomaly_detector import detect_collusion
        bid = db.query(Bid).filter(Bid.id == bid_id).first()
        if not bid:
            raise ValueError(f"공고를 찾을 수 없습니다: {bid_id}")
        result = _get_hot_zones(db, agency_id=bid.agency_id, period_type=period_type)
        result["bid_id"] = bid_id
        result["agency_id"] = bid.agency_id

        collusion_alert = None
        if bid.agency_id:
            try:
                rows = db.execute(text("""
                    SELECT ip.bid_rate::float
                    FROM inpo21c_participants ip
                    JOIN inpo21c_bids ib USING (inpo21c_bid_id)
                    JOIN agencies a ON (
                        TRIM(a.name) = TRIM(ib.agency_name)
                        OR TRIM(ib.agency_name) LIKE '%' || TRIM(a.name) || '%'
                        OR TRIM(a.name) LIKE '%' || TRIM(ib.agency_name) || '%'
                    )
                    WHERE a.id = :aid
                      AND ib.open_datetime >= NOW() - INTERVAL '6 months'
                      AND ip.bid_rate BETWEEN 0.80 AND 1.05
                      AND ip.company_name != '유찰'
                    ORDER BY ib.open_datetime DESC
                    LIMIT 200
                """), {"aid": bid.agency_id}).fetchall()
                if rows:
                    collusion_alert = detect_collusion([float(r[0]) for r in rows])
            except Exception:
                pass
        result["collusion_alert"] = collusion_alert
        return result

class BestRateService:
    """Hot Zone + Prism 결합 원클릭 최적 투찰 사정율 추천."""

    def get(self, db: Session, bid_id: int, period_type: str = "24M") -> dict:
        from ..ml.hotzone import get_best_rate as _get_best_rate
        bid = db.query(Bid).filter(Bid.id == bid_id).first()
        if not bid:
            raise ValueError(f"공고를 찾을 수 없습니다: {bid_id}")
        result = _get_best_rate(
            db,
            agency_id=bid.agency_id,
            base_amount=int(bid.base_amount or 0),
            period_type=period_type,
        )
        result["bid_id"] = bid_id
        result["base_amount"] = bid.base_amount
        result["explanation"] = self._build_explanation(result)
        return result

    def _build_explanation(self, r: dict) -> str:
        """신뢰도·소스별 1줄 근거 텍스트 자동 생성."""
        source     = r.get("source", "")
        confidence = float(r.get("confidence") or 0)
        peaks      = r.get("hotzone_peaks") or []
        rate       = r.get("recommended_srate")
        agency_n   = sum(p.get("total", 0) for p in peaks) if peaks else 0

        if confidence < 0.50:
            return (
                f"이 기관 실측 데이터 부족 (신뢰도 {confidence*100:.0f}%). "
                "전국 평균 기반 추정값이므로 실제 낙찰 패턴과 다를 수 있습니다."
            )

        if "hotzone" in source and peaks:
            top = peaks[0]
            win_r = top.get("win_rate", 0)
            win_n = top.get("win_count", 0)
            return (
                f"최근 {agency_n}건 중 {rate*100:.3f}% 구간 낙찰 {win_n}건"
                f"({win_r*100:.0f}%) — 가장 높은 실증 밀집도"
                + (" (Prism 일치)" if "prism" in source else "")
            )
        if source == "prism":
            return (
                f"Monte Carlo 시뮬레이션 기반 최적 구간 (실측 데이터 미흡, "
                f"신뢰도 {confidence*100:.0f}%). 수집 데이터 증가 시 정확도 향상."
            )
        return f"추천 사정율 {rate*100:.3f}% (신뢰도 {confidence*100:.0f}%)"


# ==================================================
# 시장 인텔리전스 서비스
# ==================================================

class FrequencyService:
    """발주기관별 낙찰률 빈도표 + 히스토그램 (bid_results 기반)"""

    PERIOD_MAP = {"6M": 6, "12M": 12, "24M": 24, "48M": 48}
    BUCKET_WIDTH = 0.005

    def __init__(self, db: Session):
        self.db = db

    def get_agency_freq(self, agency_id: int, industry_code: str = "ALL", period: str = "48M") -> dict:
        months = self.PERIOD_MAP.get(period, 48)
        rows = self.db.query(RateFrequencyTable).filter(
            RateFrequencyTable.agency_id == agency_id,
            RateFrequencyTable.industry_code == industry_code,
            RateFrequencyTable.period_type == period,
        ).order_by(RateFrequencyTable.bucket_from).all()

        if not rows:
            self._build_agency_freq(agency_id, industry_code, months, period)
            self.db.commit()
            rows = self.db.query(RateFrequencyTable).filter(
                RateFrequencyTable.agency_id == agency_id,
                RateFrequencyTable.industry_code == industry_code,
                RateFrequencyTable.period_type == period,
            ).order_by(RateFrequencyTable.bucket_from).all()

        agency = self.db.query(Agency).filter(Agency.id == agency_id).first()
        buckets = [
            {
                "from": float(r.bucket_from),
                "to": float(r.bucket_to),
                "count": r.count,
                "win_count": r.win_count,
                "win_rate": float(r.win_rate) if r.win_rate else 0,
            }
            for r in rows
        ]
        total = sum(b["count"] for b in buckets)
        return {
            "agency_id": agency_id,
            "agency_name": agency.name if agency else "",
            "industry_code": industry_code,
            "period": period,
            "total_bids": total,
            "buckets": buckets,
        }

    def rebuild_all(self) -> dict:
        agencies = self.db.execute(text(
            "SELECT DISTINCT b.agency_id FROM bid_results r JOIN bids b ON b.id = r.bid_id LIMIT 500"
        )).fetchall()
        built = 0
        for (agency_id,) in agencies:
            for period_label, months in self.PERIOD_MAP.items():
                try:
                    self._build_agency_freq(agency_id, "ALL", months, period_label)
                    built += 1
                except Exception:
                    pass
        self.db.commit()
        return {"built": built, "agencies": len(agencies)}

    def rebuild_agencies(self, agency_ids: list) -> dict:
        """특정 기관 목록만 빠르게 재구축 — inpo21c 수집 후 부분 갱신용."""
        built = 0
        for agency_id in agency_ids:
            for period_label, months in self.PERIOD_MAP.items():
                try:
                    self._build_agency_freq(agency_id, "ALL", months, period_label)
                    built += 1
                except Exception:
                    pass
        self.db.commit()
        return {"built": built, "agencies": len(agency_ids)}

    def _build_agency_freq(self, agency_id: int, industry_code: str, months: int, period_label: str):
        cutoff = f"NOW() - INTERVAL '{months} months'"
        sql = text(f"""
            SELECT
                r.assessment_rate,
                CASE WHEN r.is_winner THEN 1 ELSE 0 END AS is_win
            FROM bid_results r
            JOIN bids b ON b.id = r.bid_id
            WHERE b.agency_id = :agency_id
              AND r.assessment_rate IS NOT NULL
              AND b.bid_open_date >= {cutoff}
        """)
        rows = self.db.execute(sql, {"agency_id": agency_id}).fetchall()
        if not rows:
            return

        # 기존 행 삭제
        self.db.query(RateFrequencyTable).filter(
            RateFrequencyTable.agency_id == agency_id,
            RateFrequencyTable.industry_code == industry_code,
            RateFrequencyTable.period_type == period_label,
        ).delete()

        buckets: dict[float, dict] = {}
        for rate, is_win in rows:
            rate_f = float(rate)
            bucket_from = round(int(rate_f / self.BUCKET_WIDTH) * self.BUCKET_WIDTH, 6)
            bucket_to = round(bucket_from + self.BUCKET_WIDTH, 6)
            if bucket_from not in buckets:
                buckets[bucket_from] = {"to": bucket_to, "count": 0, "win": 0}
            buckets[bucket_from]["count"] += 1
            buckets[bucket_from]["win"] += is_win

        for bf, bdata in buckets.items():
            win_rate = round(bdata["win"] / bdata["count"], 4) if bdata["count"] > 0 else None
            self.db.add(RateFrequencyTable(
                agency_id=agency_id,
                industry_code=industry_code,
                period_type=period_label,
                bucket_from=bf,
                bucket_to=bdata["to"],
                bucket_width=self.BUCKET_WIDTH,
                count=bdata["count"],
                win_count=bdata["win"],
                win_rate=win_rate,
            ))


# ==================================================
# 발주기관 전략 DB 서비스 (AgencyStrategy 집계)
# ==================================================

class AgencyStrategyService:
    """발주기관별 48개월 낙찰률 통계 + 빈도표 + 히스토그램 (agency_strategies 테이블)"""

    BUCKET_W = 0.005

    def __init__(self, db: Session):
        self.db = db

    def get(self, agency_id: int, industry_code: str = "ALL", period_months: int = 48) -> dict | None:
        row = self.db.query(AgencyStrategy).filter(
            AgencyStrategy.agency_id == agency_id,
            AgencyStrategy.industry_code == industry_code,
            AgencyStrategy.period_months == period_months,
        ).first()
        if not row:
            return None
        return self._serialize(row)

    def get_or_build(self, agency_id: int, industry_code: str = "ALL", period_months: int = 48) -> dict:
        row = self.db.query(AgencyStrategy).filter(
            AgencyStrategy.agency_id == agency_id,
            AgencyStrategy.industry_code == industry_code,
            AgencyStrategy.period_months == period_months,
        ).first()
        if not row:
            self._build_one(agency_id, industry_code, period_months)
            self.db.commit()
            row = self.db.query(AgencyStrategy).filter(
                AgencyStrategy.agency_id == agency_id,
                AgencyStrategy.industry_code == industry_code,
                AgencyStrategy.period_months == period_months,
            ).first()
        if not row:
            return {"agency_id": agency_id, "total_bid_count": 0, "message": "데이터 부족"}
        return self._serialize(row)

    def rebuild_all(self) -> dict:
        """전체 기관 strategy 재계산 (데이터 5건 이상 기관만)"""
        agencies = self.db.execute(text(
            "SELECT DISTINCT b.agency_id FROM bids b "
            "JOIN bid_results r ON r.bid_id = b.id "
            "WHERE b.bid_open_date >= NOW() - INTERVAL '48 months' "
            "GROUP BY b.agency_id HAVING COUNT(CASE WHEN r.is_winner THEN 1 END) >= 5"
        )).fetchall()
        built, skipped = 0, 0
        for (agency_id,) in agencies:
            try:
                self._build_one(agency_id, "ALL", 48)
                built += 1
            except Exception:
                skipped += 1
        self.db.commit()
        return {"built": built, "skipped": skipped, "agencies": len(agencies)}

    def _build_one(self, agency_id: int, industry_code: str, period_months: int):
        from datetime import datetime, timedelta

        cutoff = datetime.utcnow() - timedelta(days=30 * period_months)

        # 낙찰률 (winner rows)
        winner_rows = self.db.execute(text("""
            SELECT r.bid_rate::float
            FROM bid_results r
            JOIN bids b ON b.id = r.bid_id
            WHERE b.agency_id = :aid
              AND r.is_winner = true
              AND r.bid_rate IS NOT NULL
              AND b.bid_open_date >= :cutoff
        """), {"aid": agency_id, "cutoff": cutoff}).fetchall()

        rates = [row[0] for row in winner_rows]
        n = len(rates)
        if n < 5:
            return

        arr = np.array(rates)

        # 건당 평균 경쟁업체 수
        avg_comp = self.db.execute(text("""
            SELECT COALESCE(AVG(cnt), 0)::float FROM (
                SELECT COUNT(*) AS cnt
                FROM bid_results r
                JOIN bids b ON b.id = r.bid_id
                WHERE b.agency_id = :aid AND b.bid_open_date >= :cutoff
                GROUP BY r.bid_id
            ) sub
        """), {"aid": agency_id, "cutoff": cutoff}).scalar() or 0.0

        # 공격성 지수: 낙찰하한율 이하 낙찰 비율
        aggression_row = self.db.execute(text("""
            SELECT
                COUNT(CASE WHEN r.bid_rate < b.min_bid_rate THEN 1 END)::float
                / NULLIF(COUNT(*), 0)::float
            FROM bid_results r
            JOIN bids b ON b.id = r.bid_id
            WHERE b.agency_id = :aid
              AND r.is_winner = true
              AND b.min_bid_rate IS NOT NULL
              AND b.bid_open_date >= :cutoff
        """), {"aid": agency_id, "cutoff": cutoff}).scalar()
        aggression_index = float(aggression_row) if aggression_row else 0.0

        # 최근 30일 변동성
        recent_cutoff = datetime.utcnow() - timedelta(days=30)
        recent_rates = [r[0] for r in self.db.execute(text("""
            SELECT r.bid_rate::float
            FROM bid_results r JOIN bids b ON b.id = r.bid_id
            WHERE b.agency_id = :aid AND r.is_winner = true
              AND r.bid_rate IS NOT NULL AND b.bid_open_date >= :rc
        """), {"aid": agency_id, "rc": recent_cutoff}).fetchall()]
        volatility_30d = float(np.std(recent_rates)) if len(recent_rates) >= 3 else None

        # 추세: 최근 12M vs 12M~24M
        cutoff_12m = datetime.utcnow() - timedelta(days=365)
        cutoff_24m = datetime.utcnow() - timedelta(days=730)
        m_recent = self.db.execute(text("""
            SELECT AVG(r.bid_rate)::float FROM bid_results r JOIN bids b ON b.id = r.bid_id
            WHERE b.agency_id = :aid AND r.is_winner = true AND b.bid_open_date >= :c12
        """), {"aid": agency_id, "c12": cutoff_12m}).scalar()
        m_older = self.db.execute(text("""
            SELECT AVG(r.bid_rate)::float FROM bid_results r JOIN bids b ON b.id = r.bid_id
            WHERE b.agency_id = :aid AND r.is_winner = true
              AND b.bid_open_date BETWEEN :c24 AND :c12
        """), {"aid": agency_id, "c24": cutoff_24m, "c12": cutoff_12m}).scalar()
        trend_direction = "stable"
        if m_recent and m_older:
            diff = m_recent - m_older
            trend_direction = "up" if diff > 0.002 else ("down" if diff < -0.002 else "stable")

        # 빈도표 JSON (0.5% 구간)
        freq_table = []
        lo_b = round(int(float(arr.min()) / self.BUCKET_W) * self.BUCKET_W, 6)
        b_ptr = lo_b
        while b_ptr <= float(arr.max()) + 1e-9:
            cnt = int(np.sum((arr >= b_ptr) & (arr < b_ptr + self.BUCKET_W)))
            if cnt > 0:
                freq_table.append({"from": round(b_ptr, 4), "to": round(b_ptr + self.BUCKET_W, 4), "count": cnt})
            b_ptr = round(b_ptr + self.BUCKET_W, 6)

        # 히스토그램 데이터 (0.860~0.965 고정 범위)
        hist_bins = np.arange(0.860, 0.966, self.BUCKET_W)
        hist_counts, _ = np.histogram(arr, bins=hist_bins)
        histogram_data = [
            [round(float(hist_bins[i]), 4), int(hist_counts[i])]
            for i in range(len(hist_counts))
        ]

        # 난이도 분류
        cv = float(np.std(arr) / np.mean(arr)) if np.mean(arr) > 0 else 0
        if avg_comp >= 10 and cv > 0.01:
            qual_difficulty = "難"
        elif avg_comp >= 5 or cv > 0.005:
            qual_difficulty = "中"
        else:
            qual_difficulty = "易"

        p25 = float(np.percentile(arr, 25))
        p75 = float(np.percentile(arr, 75))

        upsert_data = dict(
            total_bid_count=n,
            avg_win_rate=float(np.mean(arr)),
            std_win_rate=float(np.std(arr)),
            min_win_rate=float(arr.min()),
            max_win_rate=float(arr.max()),
            win_rate_p10=float(np.percentile(arr, 10)),
            win_rate_p25=p25,
            win_rate_p50=float(np.percentile(arr, 50)),
            win_rate_p75=p75,
            win_rate_p90=float(np.percentile(arr, 90)),
            avg_competitor_cnt=avg_comp,
            aggression_index=aggression_index,
            qual_difficulty=qual_difficulty,
            freq_table=freq_table,
            histogram_data=histogram_data,
            volatility_30d=volatility_30d,
            trend_direction=trend_direction,
            recommended_range_lo=p25,
            recommended_range_hi=p75,
        )

        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.exc import IntegrityError
        stmt = pg_insert(AgencyStrategy).values(
            agency_id=agency_id,
            industry_code=industry_code,
            period_months=period_months,
            **upsert_data,
        ).on_conflict_do_update(
            constraint="agency_strategies_agency_id_industry_code_period_months_key",
            set_=upsert_data,
        )
        try:
            self.db.execute(stmt)
        except IntegrityError:
            self.db.rollback()

    @staticmethod
    def _serialize(row: AgencyStrategy) -> dict:
        return {
            "agency_id":          row.agency_id,
            "industry_code":      row.industry_code,
            "period_months":      row.period_months,
            "total_bid_count":    row.total_bid_count,
            "avg_win_rate":       float(row.avg_win_rate)       if row.avg_win_rate else None,
            "std_win_rate":       float(row.std_win_rate)       if row.std_win_rate else None,
            "min_win_rate":       float(row.min_win_rate)       if row.min_win_rate else None,
            "max_win_rate":       float(row.max_win_rate)       if row.max_win_rate else None,
            "win_rate_p10":       float(row.win_rate_p10)       if row.win_rate_p10 else None,
            "win_rate_p25":       float(row.win_rate_p25)       if row.win_rate_p25 else None,
            "win_rate_p50":       float(row.win_rate_p50)       if row.win_rate_p50 else None,
            "win_rate_p75":       float(row.win_rate_p75)       if row.win_rate_p75 else None,
            "win_rate_p90":       float(row.win_rate_p90)       if row.win_rate_p90 else None,
            "avg_competitor_cnt": float(row.avg_competitor_cnt) if row.avg_competitor_cnt else None,
            "aggression_index":   float(row.aggression_index)   if row.aggression_index else None,
            "qual_difficulty":    row.qual_difficulty,
            "freq_table":         row.freq_table or [],
            "histogram_data":     row.histogram_data or [],
            "volatility_30d":     float(row.volatility_30d)     if row.volatility_30d else None,
            "trend_direction":    row.trend_direction,
            "recommended_range_lo": float(row.recommended_range_lo) if row.recommended_range_lo else None,
            "recommended_range_hi": float(row.recommended_range_hi) if row.recommended_range_hi else None,
            "updated_at":         row.updated_at.isoformat() if row.updated_at else None,
        }


# ==================================================
# 자사 전용 경쟁사 서비스
# ==================================================

class MarketIntelService:
    """inpo21c_participants 기반 시장 인텔리전스 — 발주처×사정율 히트맵."""

    def agency_heatmap(self, db: Session, months: int = 12, top_n: int = 20) -> dict:
        """발주처별 낙찰율 분포 히트맵 데이터."""
        months_safe = max(1, min(int(months), 60))
        top_n_safe  = max(5, min(int(top_n), 100))
        rows = db.execute(text(f"""
            SELECT ib.agency_name,
                   COUNT(DISTINCT ib.inpo21c_bid_id)          AS bid_count,
                   AVG(ip.bid_rate::numeric)                  AS avg_winner_rate,
                   PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY ip.bid_rate::numeric) AS p25,
                   PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY ip.bid_rate::numeric) AS p75,
                   MIN(ip.bid_rate::numeric)                  AS min_rate,
                   MAX(ip.bid_rate::numeric)                  AS max_rate
            FROM inpo21c_participants ip
            JOIN inpo21c_bids ib USING (inpo21c_bid_id)
            WHERE ip.is_winner = TRUE
              AND (ib.open_datetime IS NULL OR ib.open_datetime >= NOW() - INTERVAL '{months_safe} months')
            GROUP BY ib.agency_name
            HAVING COUNT(*) >= 3
            ORDER BY bid_count DESC
            LIMIT {top_n_safe}
        """)).fetchall()

        return {
            "months":  months,
            "agencies": [
                {
                    "agency_name":    r[0],
                    "bid_count":      int(r[1]),
                    "avg_rate":       float(r[2]) if r[2] else None,
                    "p25":            float(r[3]) if r[3] else None,
                    "p75":            float(r[4]) if r[4] else None,
                    "min_rate":       float(r[5]) if r[5] else None,
                    "max_rate":       float(r[6]) if r[6] else None,
                }
                for r in rows
            ],
        }

    def winner_rate_trend(self, db: Session, agency_name: Optional[str] = None) -> dict:
        """월별 낙찰율 추세 (open_datetime 우선, 없으면 created_at 사용)."""
        rows = db.execute(text("""
            SELECT EXTRACT(YEAR  FROM COALESCE(ib.open_datetime, ib.created_at))  AS yr,
                   EXTRACT(MONTH FROM COALESCE(ib.open_datetime, ib.created_at))  AS mo,
                   COUNT(DISTINCT ib.inpo21c_bid_id)    AS bid_count,
                   AVG(ip.bid_rate::numeric)             AS avg_rate
            FROM inpo21c_participants ip
            JOIN inpo21c_bids ib USING (inpo21c_bid_id)
            WHERE ip.is_winner = TRUE
              AND (:agency IS NULL OR ib.agency_name = :agency)
            GROUP BY yr, mo
            ORDER BY yr, mo
            LIMIT 36
        """), {"agency": agency_name}).fetchall()
        return {
            "agency_name": agency_name,
            "trend": [
                {
                    "year":       int(r[0]),
                    "month":      int(r[1]),
                    "bid_count":  int(r[2]),
                    "avg_rate":   float(r[3]) if r[3] else None,
                }
                for r in rows
            ],
        }

    def top_winner_companies(self, db: Session, agency_name: Optional[str] = None, top_n: int = 10) -> list:
        """낙찰 다발 업체 순위."""
        rows = db.execute(text("""
            SELECT ip.company_name,
                   COUNT(*) as win_count,
                   AVG(ip.bid_rate::numeric) as avg_rate,
                   MIN(ip.bid_rate::numeric) as min_rate,
                   MAX(ip.bid_rate::numeric) as max_rate
            FROM inpo21c_participants ip
            JOIN inpo21c_bids ib USING (inpo21c_bid_id)
            WHERE ip.is_winner = TRUE
              AND (:agency IS NULL OR ib.agency_name = :agency)
            GROUP BY ip.company_name
            ORDER BY win_count DESC
            LIMIT :n
        """), {"agency": agency_name, "n": top_n}).fetchall()
        return [
            {
                "company_name": r[0],
                "win_count":    int(r[1]),
                "avg_rate":     float(r[2]) if r[2] else None,
                "min_rate":     float(r[3]) if r[3] else None,
                "max_rate":     float(r[4]) if r[4] else None,
            }
            for r in rows
        ]


# ==================================================
# 투찰 실행 관리 서비스
# ==================================================

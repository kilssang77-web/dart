"""
추천 서비스
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

import time as _time
_history_cache: dict = {}
_HISTORY_TTL = 3600  # 1시간 캐시


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
        cache_key = f"history_{months}"
        _now = _time.monotonic()
        _cached = _history_cache.get(cache_key)
        if _cached is not None:
            _df, _ts = _cached
            if _now - _ts < _HISTORY_TTL:
                return _df

        cutoff = datetime.now() - timedelta(days=months * 30)
        rows = db.execute(text("""
            SELECT b.id, b.agency_id, b.industry_id, b.region_id,
                   b.base_amount, b.bid_open_date,
                   r.bid_rate as winner_rate,
                   GREATEST(
                       COALESCE(b.participant_count, 0),
                       (SELECT COUNT(*) FROM bid_results r2 WHERE r2.bid_id = b.id)
                   ) as competitor_count
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
        _history_cache[cache_key] = (df, _time.monotonic())
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

        wp = result["win_probabilities"].get("at_balanced")
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
                win_prob_center=wp.get("at_balanced"),
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

        # bid_id 제공 시 실제 공고 낙찰하한율 자동 적용 [2순위 개선]
        _bid_id = getattr(req, "bid_id", None)
        if _bid_id:
            try:
                _bid_row = db.execute(text(
                    "SELECT min_bid_rate, bid_open_date FROM bids WHERE id = :bid_id"
                ), {"bid_id": _bid_id}).fetchone()
                if _bid_row:
                    if _bid_row[0] and float(_bid_row[0]) > 0.5:
                        min_bid_rate = max(min_bid_rate, float(_bid_row[0]))
                    if _bid_row[1] and not getattr(req, "bid_open_date", None):
                        bid_date = _bid_row[1]
            except Exception as _e:
                logger.debug("bid_id floor_rate 조회 실패 (무시): %s", _e)

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

        # ── Step 8.5: 개인화 편향 보정 (Monte Carlo 전 적용)
        personal_info = {"correction": 0.0, "agency_correction": None,
                         "confidence": 0.0, "direction": "balanced",
                         "avg_bias_pct": 0.0, "sample_count": 0, "narrative": ""}
        if user_id:
            try:
                agency_name_for_bias = None
                _ag = db.query(Agency).filter(Agency.id == req.agency_id).first()
                if _ag:
                    agency_name_for_bias = _ag.name
                personal_info = PersonalBiasAnalyzer().compute(
                    db, user_id,
                    agency_name=agency_name_for_bias,
                )
                # 신뢰도 비례 보정값 (낮은 신뢰도면 보정 축소)
                effective_corr = personal_info["correction"] * personal_info["confidence"]
                # 발주처 특화 보정 병합
                if personal_info.get("agency_correction") is not None:
                    agency_conf = min(1.0, len([1]) * personal_info["confidence"])
                    effective_corr = (effective_corr * 0.6 +
                                      personal_info["agency_correction"] * personal_info["confidence"] * 0.4)
                ens_center += effective_corr
                ens_lower  += effective_corr
                ens_upper  += effective_corr
                # 낙찰하한율 재확인
                ens_lower  = max(ens_lower,  hard_floor + 0.0005)
                ens_center = max(ens_center, ens_lower  + 0.0005)
                ens_upper  = max(ens_upper,  ens_center + 0.0005)
            except Exception as _e:
                logger.debug(f"개인화 보정 실패 (무시): {_e}")

        # ── Step 9-pre: 경쟁사 프로파일 (시뮬레이션 입력용)
        comp_profiles = get_competitor_profiles(
            db, req.known_competitor_ids or [],
            req.agency_id, req.industry_id, bid_date
        )

        # ── Step 9: 복수예가 Monte Carlo 시뮬레이션 기반 4전략
        industry_name = self._get_industry_name(db, req.industry_id)
        srate_std_val = features_a.get("agency_srate_std") or 0.012
        expected_n = max(3, min(features_c.get("expected_competitor_count", 8), 150))
        if comp_profiles:
            comp_means = [p["avg_rate"] for p in comp_profiles]
            comp_stds  = [max(p["std_rate"], 0.003) for p in comp_profiles]
        else:
            comp_means, comp_stds = get_market_competitor_distributions(
                db, req.agency_id, req.industry_id, bid_date
            )
        # 기대 경쟁업체 수에 맞게 상위 N개만 사용
        comp_means = comp_means[:expected_n]
        comp_stds  = comp_stds[:expected_n]
        # inpo21c 실증 분포 (데이터 있으면 합성 정규분포 대체)
        inpo_rates = None
        try:
            inpo_rates = get_inpo_raw_rates(db, expected_n)
        except Exception as _e:
            logger.debug("inpo21c 실증 분포 조회 실패 (무시): %s", _e)

        _yega_stats  = load_inpo21c_yega_stats(db, req.agency_id or 0, announcement_no=getattr(req, "announcement_no", None))
        _pos_weights = _yega_stats.get("pos_weights")
        _spread_half = _yega_stats.get("spread_half", 0.028)

        # 복수예가 패턴 ML 피처 주입 (Engine B)
        _yega_ml = _compute_yega_ml_features(_pos_weights)
        features_b["yega_top3_freq"]   = _yega_ml["top3_freq"]
        features_b["yega_entropy"]     = _yega_ml["entropy"]
        features_b["yega_mode_bucket"] = _yega_ml["mode_bucket"]

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
            empirical_comp_rates=inpo_rates,
            expected_n_comp=expected_n if inpo_rates is not None else 0,
            pos_weights=_pos_weights,
            spread_half=_spread_half,
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
                "safe_lower": round(ens_lower  - 0.003, 6),
                "lower":      round(ens_lower,   6),
                "center":     round(ens_center,  6),
                "upper":      round(ens_upper,   6),
                "safe_upper": round(ens_upper  + 0.003, 6),
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
            "personal_correction": personal_info,
        }

    # ──────────────────────────────────────────
    # 내부 메서드
    # ──────────────────────────────────────────

    def _get_industry_name(self, db: Session, industry_id: int) -> str:
        from ..models import Industry
        ind = db.query(Industry).filter(Industry.id == industry_id).first()
        return ind.name if ind else ""

    def _load_history(self, db: Session, months: int = 24) -> "pd.DataFrame":
        import pandas as pd
        cutoff = datetime.now() - timedelta(days=months * 30)
        rows = db.execute(text("""
            SELECT b.id, b.agency_id, b.industry_id, b.region_id,
                   b.base_amount, b.bid_open_date,
                   r.bid_rate AS winner_rate,
                   GREATEST(
                       COALESCE(b.participant_count, 0),
                       (SELECT COUNT(*) FROM bid_results r2 WHERE r2.bid_id = b.id)
                   ) AS competitor_count
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
        from ..ml.engine import FEATURE_LABELS
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
            from ..models import PredictionLogV2
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

class SingleRecommendService:
    """E5: 단일 최적 전략 추천 서비스"""

    def recommend(self, db: Session, user_id: int, req: dict) -> dict:
        from ..models import Bid, CompanyProfile, BidDecision, ActualBidOutcome
        from ..ml.assessment  import predict_srate, load_srate_stats
        from ..ml.competition import compute_competition_features, get_market_competitor_distributions
        from ..ml.simulation  import simulate_yejung
        from ..ml.personal    import PersonalBiasAnalyzer
        from ..ml.qualification import check_qualification, get_valid_bid_range
        from ..ml.strategy    import StrategyInput, recommend as strategy_recommend
        from ..ml.a_value     import calc_floor_rate

        bid_id   = req.get("bid_id")
        base_amt = req["base_amount"]

        bid = db.query(Bid).filter(Bid.id == bid_id).first() if bid_id else None
        profile = db.query(CompanyProfile).first()

        # 사정율 예측
        _fa2         = load_srate_stats(db, req["agency_id"], req.get("industry_id"), req.get("region_id"), base_amt)
        _sr2         = predict_srate(_fa2, base_amt)
        _rng3        = _sr2["srate_range"]
        srate_center = _rng3["center"]
        srate_std    = (_rng3["upper"] - _rng3["lower"]) / 2

        # Monte Carlo 사정율 분포 생성
        import numpy as np
        rng = np.random.default_rng(42)
        _ann_no = req.get("announcement_no") or (bid.announcement_no if bid else None)
        _ys2 = load_inpo21c_yega_stats(db, req.get("agency_id") or 0, announcement_no=_ann_no)
        srate_dist = simulate_yejung(
            base_amt, srate_center, srate_std, n_sim=30_000, rng=rng,
            pos_weights=_ys2.get("pos_weights"),
            spread_half=_ys2.get("spread_half", 0.028),
        )

        # 경쟁사 최소 투찰률 분포
        comp = compute_competition_features(
            db, req["agency_id"], req.get("industry_id"), base_amt
        )
        comp_means, comp_stds = get_market_competitor_distributions(
            db, req["agency_id"], req.get("industry_id")
        )

        # 경쟁사 max 분포 시뮬레이션 (복수예가: 예정가 이하 최고가 낙찰 기준)
        if comp_means:
            n_sim = 30_000
            n_comp = len(comp_means)
            comp_matrix = np.column_stack([
                rng.normal(m, max(s, 0.002), n_sim)
                for m, s in zip(comp_means, comp_stds)
            ])
            comp_max_dist = comp_matrix.max(axis=1)
        else:
            comp_max_dist = None

        # 낙찰하한율 — industry_id → 공종명 조회 후 calc_floor_rate 호출
        _industry_id = req.get("industry_id")
        _industry_name = ""
        if _industry_id:
            _ind_row = db.execute(
                text("SELECT name FROM industries WHERE id = :id"),
                {"id": _industry_id},
            ).fetchone()
            if _ind_row:
                _industry_name = _ind_row[0]
        floor_rate = calc_floor_rate(_industry_name)

        # 적격심사 유효 범위
        valid_low = valid_high = None
        qual_result_dict = None
        if bid_id and profile:
            try:
                from .agency import QualificationService
                qual_svc = QualificationService()
                qual_result_dict = qual_svc.check(db, bid_id, user_id)
                from ..ml.qualification import QualificationResult, get_valid_bid_range
                from ..ml.qualification import QualificationResult as QR
                qr = QR(
                    verdict=qual_result_dict["verdict"],
                    pass_prob=qual_result_dict["pass_prob"],
                    min_pass_amount=qual_result_dict["min_pass_amount"],
                    max_pass_amount=qual_result_dict["max_pass_amount"],
                    score_breakdown=qual_result_dict["score_breakdown"],
                    fail_reason=qual_result_dict["fail_reason"],
                    criteria_type=qual_result_dict["criteria_type"],
                )
                lo_amt, hi_amt = get_valid_bid_range(qr, floor_rate, base_amt)
                if lo_amt and hi_amt:
                    valid_low  = lo_amt / base_amt
                    valid_high = hi_amt / base_amt
            except Exception:
                pass

        # 개인 편향 보정
        bias_correction = 0.0
        try:
            analyzer = PersonalBiasAnalyzer()
            bias_info = analyzer.analyze(db, user_id)
            bias_correction = bias_info.get("correction", 0.0)
        except Exception:
            pass

        # 월 수주 목표 현황
        monthly_target     = profile.monthly_win_target if profile else 3
        from ..models import ActualBidOutcome
        current_month_wins = db.execute(
            text("SELECT COUNT(*) FROM actual_bid_outcomes WHERE result='WON' AND DATE_TRUNC('month', created_at) = DATE_TRUNC('month', NOW())")
        ).scalar() or 0

        inp = StrategyInput(
            base_amount=base_amt,
            floor_rate=floor_rate,
            srate_center=srate_center,
            srate_std=srate_std,
            srate_dist=srate_dist,
            competitor_means=comp_means,
            competitor_stds=comp_stds,
            competitor_max_dist=comp_max_dist,
            valid_low=valid_low,
            valid_high=valid_high,
            bias_correction=bias_correction,
            monthly_target=monthly_target,
            current_month_wins=current_month_wins,
            historical_win_rate=0.20,
        )

        from ..ml.strategy import recommend as do_recommend
        rec = do_recommend(inp)

        return {
            "rate":              rec.rate,
            "bid_amount":        rec.bid_amount,
            "win_prob":          rec.win_prob,
            "expected_value":    rec.expected_value,
            "confidence":        rec.confidence,
            "strategy_type":     rec.strategy_type,
            "rationale":         rec.rationale,
            "rationale_details": rec.rationale_details,
            "valid_range":       list(rec.valid_range),
            "prism_top5":        rec.prism_top5,
            "qualification":     qual_result_dict,
        }

class BidSelectionService:
    """E1: 공고 선별 엔진 서비스"""

    def evaluate_bid(self, db: Session, bid_id: int, user_id: int) -> dict:
        from ..models import Bid, CompanyProfile, BidDecision, PortfolioState
        from ..ml.selection import SelectionInput, evaluate
        from ..ml.assessment import predict_srate, load_srate_stats
        from ..ml.competition import compute_competition_features

        bid = db.query(Bid).filter(Bid.id == bid_id).first()
        if not bid:
            from fastapi import HTTPException
            raise HTTPException(404, "공고를 찾을 수 없습니다")

        profile   = db.query(CompanyProfile).first()
        from .agency import QualificationService
        qual_svc  = QualificationService()

        # 적격심사 사전 체크 (profile 없으면 기본값)
        try:
            qual = qual_svc.check(db, bid_id, user_id)
            qualify_prob = qual["pass_prob"]
        except Exception:
            qualify_prob = 0.8

        # 면허 / 지역 매칭
        license_match = True
        region_ok     = True
        if profile and profile.license_codes and bid.license_codes:
            license_match = bool(set(profile.license_codes) & set(bid.license_codes or []))
        if bid.region_restriction and profile and profile.region_codes:
            region_ok = bool(set(profile.region_codes) & set([str(bid.region_id or "")]))

        # 경쟁 강도
        comp = compute_competition_features(
            db=db,
            agency_id=bid.agency_id,
            industry_id=bid.industry_id,
            base_amount=bid.base_amount,
        )
        comp_score   = comp.get("competitor_strength_score", 5.0)
        strong_count = sum(1 for s in comp.get("competitor_scores", []) if s >= 7.0)

        # 사정율 예측
        _fa        = load_srate_stats(db, bid.agency_id, bid.industry_id, bid.region_id, bid.base_amount)
        _sr        = predict_srate(_fa, bid.base_amount)
        _rng2      = _sr["srate_range"]
        srate_info = {"center": _rng2["center"], "std": (_rng2["upper"] - _rng2["lower"]) / 2}
        floor_rate = float(bid.min_bid_rate or 0.87745)
        best_wp    = max(0.0, min(1.0, 1.0 - comp_score / 12.0))  # 근사값

        # 전략 부합도
        in_target_region   = bool(profile and bid.region_id and bid.region_id in (profile.target_industries or []))
        in_target_industry = bool(profile and bid.industry_id and bid.industry_id in (profile.target_industries or []))

        # 과거 승률
        hist = db.execute(
            text("""
                SELECT COUNT(*) FILTER (WHERE abo.result='WON') as wins,
                       COUNT(*) as total
                FROM actual_bid_outcomes abo
                JOIN bids b ON b.id = abo.bid_id
                WHERE b.agency_id = :aid AND abo.user_id = :uid
            """),
            {"aid": bid.agency_id, "uid": user_id},
        ).fetchone()
        hist_win_rate = (hist.wins / hist.total) if hist and hist.total > 0 else 0.20

        # 보증한도 현황
        from .agency import CompanyProfileService
        bond_svc = CompanyProfileService()
        bond = bond_svc.get_remaining_bond(db)

        # 현재 활성 투찰 건수
        active_count = db.query(func.count(PortfolioState.id)).filter(
            PortfolioState.status == "ACTIVE",
        ).scalar() or 0

        inp = SelectionInput(
            bid_id=bid_id,
            base_amount=bid.base_amount,
            agency_id=bid.agency_id,
            industry_id=bid.industry_id,
            region_id=bid.region_id,
            license_match=license_match,
            region_restriction_ok=region_ok,
            qualify_prob=qualify_prob,
            expected_competitor_count=comp.get("expected_competitor_count", 5),
            competitor_strength_score=comp_score,
            strong_competitor_count=strong_count,
            best_win_prob=best_wp,
            estimated_margin=profile.target_min_margin if profile else 0.05,
            in_target_region=in_target_region,
            in_target_industry=in_target_industry,
            bond_limit_total=bond["total"],
            bond_limit_used=bond["used"],
            max_concurrent_bids=profile.max_concurrent_bids if profile else 5,
            current_active_bids=active_count,
            historical_win_rate=hist_win_rate,
        )

        from ..ml.selection import evaluate
        result = evaluate(inp)

        # 결과 저장
        decision = BidDecision(
            bid_id=bid_id,
            user_id=user_id,
            selection_score=result.score,
            ev_score=result.ev_score,
            qualify_prob=result.qualify_prob,
            win_prob_best=result.win_prob_best,
            expected_margin=result.expected_margin,
            competitor_risk=result.competitor_risk,
            verdict=result.verdict,
            no_go_reasons=result.no_go_reasons,
            recommended_strategy=result.recommended_strategy,
        )
        db.add(decision)
        db.commit()
        db.refresh(decision)

        return {
            "bid_id":               bid_id,
            "verdict":              result.verdict,
            "score":                result.score,
            "ev_score":             result.ev_score,
            "qualify_prob":         result.qualify_prob,
            "win_prob_best":        result.win_prob_best,
            "expected_margin":      result.expected_margin,
            "competitor_risk":      result.competitor_risk,
            "no_go_reasons":        result.no_go_reasons,
            "score_detail":         result.score_detail,
            "recommended_strategy": result.recommended_strategy,
            "decision_id":          decision.id,
        }

    def get_go_list(self, db: Session, user_id: int, days: int = 7) -> dict:
        """최근 n일 GO 목록 반환"""
        from ..models import BidDecision, Bid
        cutoff = datetime.utcnow() - timedelta(days=days)
        decisions = db.query(BidDecision).filter(
            BidDecision.user_id == user_id,
            BidDecision.created_at >= cutoff,
        ).order_by(BidDecision.selection_score.desc()).all()

        go    = [d for d in decisions if d.verdict == "GO"]
        watch = [d for d in decisions if d.verdict == "WATCH"]
        no_go = [d for d in decisions if d.verdict == "NO_GO"]

        def _fmt(d: BidDecision) -> dict:
            bid = db.query(Bid).filter(Bid.id == d.bid_id).first()
            # 근거 데이터 건수 (신뢰도 지표)
            agency_id = bid.agency_id if bid else None
            data_count = 0
            if agency_id:
                row = db.execute(text(
                    "SELECT COUNT(*) FROM bid_results r JOIN bids b ON b.id=r.bid_id WHERE b.agency_id=:aid"
                ), {"aid": agency_id}).scalar()
                data_count = int(row or 0)
            confidence = "high" if data_count >= 100 else ("medium" if data_count >= 20 else "low")
            return {
                "bid_id":               d.bid_id,
                "title":                bid.title if bid else "",
                "base_amount":          bid.base_amount if bid else 0,
                "bid_open_date":        bid.bid_open_date.isoformat() if bid and bid.bid_open_date else None,
                "verdict":              d.verdict,
                "score":                float(d.selection_score or 0),
                "ev_score":             d.ev_score or 0,
                "qualify_prob":         float(d.qualify_prob or 0),
                "win_prob_best":        float(d.win_prob_best or 0),
                "competitor_risk":      d.competitor_risk,
                "no_go_reasons":        d.no_go_reasons or [],
                "recommended_strategy": d.recommended_strategy,
                "recommended_rate":     float(d.recommended_rate) if d.recommended_rate else None,
                "actual_action":        d.actual_action,
                "data_count":           data_count,
                "confidence":           confidence,
            }

        return {
            "go":         [_fmt(d) for d in go],
            "watch":      [_fmt(d) for d in watch],
            "no_go":      [_fmt(d) for d in no_go],
            "total":      len(decisions),
            "go_count":   len(go),
            "watch_count": len(watch),
            "no_go_count": len(no_go),
        }

class FinalRecommendService:
    """사정율통계 + 프리즘 + 예가 + 트렌드 + 개인화를 합산해 최종 투찰 사정율 1개 산출."""

    def __init__(self, db: Session):
        self.db = db

    def get(self, bid_id: int, user_id: int) -> dict:
        from fastapi import HTTPException

        bid = self.db.query(Bid).filter(Bid.id == bid_id).first()
        if not bid:
            raise HTTPException(status_code=404, detail="공고를 찾을 수 없습니다.")

        agency   = self.db.query(Agency).filter(Agency.id == bid.agency_id).first()
        industry = (self.db.query(Industry).filter(Industry.id == bid.industry_id).first()
                    if bid.industry_id else None)
        industry_name = industry.name if industry else ""
        base_amount   = int(bid.base_amount)

        # 1. 사정율 통계 (기준 mean + 표본수)
        features = load_srate_stats(
            self.db, bid.agency_id, bid.industry_id or 0, bid.region_id or 0, base_amount
        )
        srate_mean = (
            features.get("agency_srate_mean")
            or features.get("industry_srate_mean")
            or features.get("global_srate_mean")
            or 0.8876
        )
        sample_count = int(features.get("agency_srate_n") or 0)

        # 2. 트렌드 방향 (SrateTrendService 재사용)
        from .statistics import SrateTrendService
        trend           = SrateTrendService().get_trend(self.db, bid.agency_id, bid.industry_id)
        trend_direction = trend.get("direction", "stable")

        # 3. 프리즘 스캔 (전 구간 win_prob + top1 근거)
        try:
            all_zones, top10 = scan_prism_zones(
                base_amount=base_amount,
                industry_name=industry_name,
                agency_id=bid.agency_id,
                industry_id=bid.industry_id or 0,
                db=self.db,
                n_sim=15_000,
            )
        except Exception:
            all_zones, top10 = [], []

        prism_top = top10[0] if top10 else None

        # 4. 예가 빈도 top1 (크로스체크 근거) — yega_range를 inpo21c_bid_notices에서 동적 조회
        try:
            a_val = int(bid.a_value) if bid.a_value else None
            spread_half = 0.028  # fallback
            if bid.announcement_no:
                ibn_row = self.db.execute(text(
                    "SELECT yega_range_max FROM inpo21c_bid_notices "
                    "WHERE announcement_no LIKE :ano ORDER BY announcement_no LIMIT 1"
                ), {"ano": bid.announcement_no + "%"}).fetchone()
                if ibn_row and ibn_row[0] is not None:
                    spread_half = abs(int(ibn_row[0])) / 100.0
            yega   = calc_yega_frequency(base_amount, a_value=a_val, srate_center=srate_mean, spread_half=spread_half)
            yega_rows     = yega.get("frequency", [])
            yega_top_rate = float(yega_rows[0]["rate"])        if yega_rows else None
            yega_top_prob = float(yega_rows[0]["probability"]) if yega_rows else None
        except Exception:
            yega_top_rate = yega_top_prob = None

        # 5. 개인화 편향 보정
        try:
            bias = PersonalBiasAnalyzer().compute(
                self.db, user_id,
                agency_name=agency.name if agency else None,
            )
        except Exception:
            bias = PersonalBiasAnalyzer()._empty_result()

        # 6. 권장 사정율 합산
        trend_adj    = 0.001 if trend_direction == "up" else (-0.001 if trend_direction == "down" else 0.0)
        correction   = float(bias.get("correction", 0.0))
        bias_applied = abs(correction) > 0.0001

        recommended_rate = round(float(srate_mean) + trend_adj + correction, 6)

        # 7. 낙찰하한율 (A값 기준 floor → base_amount 기준 환산)
        floor_pct = calc_floor_rate(industry_name)
        if bid.min_bid_rate:
            floor_rate = round(float(bid.min_bid_rate), 5)
        else:
            floor_rate = round(float(srate_mean) * floor_pct, 5)

        # recommended_rate가 floor 미달이면 floor로 올림
        if recommended_rate < floor_rate:
            recommended_rate = floor_rate

        # 8. 전략별 근접 zone win_prob 탐색
        def _win_prob(rate: float) -> float:
            if rate < floor_rate:          # floor 미달 → 실격이므로 확률 0
                return 0.0
            if not all_zones:
                return 0.0
            nearest = min(all_zones, key=lambda z: abs(z["rate"] - rate))
            return round(float(nearest.get("win_prob", 0.0)), 4)

        def _strat(rate: float) -> dict:
            r = round(max(rate, floor_rate), 6)   # 항상 floor 이상으로 클램핑
            return {"rate": r, "amount": round(base_amount * r), "win_prob": _win_prob(r)}

        # recommended_rate가 floor에 클램핑됐을 때 aggressive/balanced가 모두
        # floor로 수렴하는 문제 수정.
        #
        # _gap = rec - floor:
        #   정상 케이스(gap 충분): 기존 ±0.5% 간격 그대로 유지
        #   클램핑 케이스(gap=0):  floor 기준 최소 간격 0.1%/0.3%/0.6% 보장
        #   → 세 전략이 항상 aggressive < balanced < conservative 순서 유지
        _gap = max(recommended_rate - floor_rate, 0.0)
        strategies = {
            "aggressive":   _strat(floor_rate + max(_gap - 0.005, 0.001)),
            "balanced":     _strat(floor_rate + max(_gap,         0.003)),
            "conservative": _strat(floor_rate + max(_gap + 0.005, 0.006)),
            "floor_safe":   _strat(floor_rate + 0.001),
        }

        # 9. 신뢰도 (표본 수 기준)
        confidence = "high" if sample_count >= 50 else ("medium" if sample_count >= 10 else "low")

        # 10. 시그널 메시지
        dir_msg = {
            "up":     "발주처 최근 사정율 상승 추세 → 균형형 이상 추천",
            "down":   "발주처 최근 사정율 하락 추세 → 공격형 이하 고려",
            "stable": "발주처 사정율 안정 추세 → 균형형 추천",
        }
        signal = dir_msg.get(trend_direction, "균형형 추천")
        if bias_applied:
            if bias.get("direction") == "too_low":
                signal += " · 과거 낮게 투찰 경향 → 상향 보정 적용"
            elif bias.get("direction") == "too_high":
                signal += " · 과거 높게 투찰 경향 → 하향 보정 적용"

        # 11. 근거 패널
        evidence = {
            "srate_stats": {
                "mean": round(float(srate_mean), 6),
                "sample_count": sample_count,
                "trend_direction": trend_direction,
            },
            "prism_top": {
                "rate":        round(float(prism_top["rate"]), 6),
                "probability": round(float(prism_top["win_prob"]), 4),
            } if prism_top else None,
            "yega_top": {
                "rate":        round(yega_top_rate, 6),
                "probability": round(yega_top_prob, 2),
            } if (yega_top_rate is not None and yega_top_prob is not None) else None,
            "personal_bias": {
                "rate_diff_mean": round(correction, 6),
                "applied":        bias_applied,
            },
        }

        return {
            "bid_id":             bid_id,
            "base_amount":        base_amount,
            "recommended_rate":   recommended_rate,
            "recommended_amount": round(base_amount * recommended_rate),
            "confidence":         confidence,
            "floor_rate":         floor_rate,
            "strategies":         strategies,
            "evidence":           evidence,
            "signal":             signal,
        }


# ==================================================
# 자사 승률 패턴 진단 서비스
# ==================================================

class ActualOutcomeService:
    """E6: 실제 투찰 결과 수집 및 피드백 처리"""

    def record_outcome(self, db: Session, user_id: int, data: dict) -> dict:
        from ..models import ActualBidOutcome, PredictionLogV2, BidDecision

        bid_id = data["bid_id"]

        # 직전 예측값 조회 (캘리브레이션용)
        pred_log = db.query(PredictionLogV2).filter(
            PredictionLogV2.bid_id == bid_id
        ).order_by(PredictionLogV2.created_at.desc()).first()

        predicted_wp    = float(pred_log.win_prob_center) if pred_log and pred_log.win_prob_center else None
        predicted_srate = float(pred_log.srate_pred_center) if pred_log and pred_log.srate_pred_center else None

        # 사정율 오차
        srate_error = None
        if predicted_srate and data.get("actual_srate"):
            srate_error = abs(predicted_srate - data["actual_srate"])

        outcome = ActualBidOutcome(
            bid_id=bid_id,
            user_id=user_id,
            bid_decision_id=data.get("bid_decision_id"),
            submitted_rate=data["submitted_rate"],
            result=data["result"],
            disqualify_reason=data.get("disqualify_reason"),
            actual_srate=data.get("actual_srate"),
            winner_rate=data.get("winner_rate"),
            winner_biz_no=data.get("winner_biz_no"),
            our_rank=data.get("our_rank"),
            total_bidders=data.get("total_bidders"),
            predicted_win_prob=predicted_wp,
            predicted_srate=predicted_srate,
            srate_error=srate_error,
            collected_at=datetime.utcnow(),
        )
        db.add(outcome)

        # 포트폴리오 상태 갱신
        from ..models import PortfolioState
        ps = db.query(PortfolioState).filter(
            PortfolioState.bid_id == bid_id,
            PortfolioState.user_id == user_id,
        ).first()
        if ps:
            ps.status     = "WON" if data["result"] == "WON" else "LOST"
            ps.result_date = datetime.utcnow().date()

        # bid_decision actual_action 갱신
        if data.get("bid_decision_id"):
            dec = db.query(BidDecision).filter(
                BidDecision.id == data["bid_decision_id"]
            ).first()
            if dec:
                dec.actual_action = "BID"
                dec.actual_rate   = data["submitted_rate"]

        # my_bid_records도 같이 갱신 (기존 테이블 연동)
        rec = db.query(MyBidRecord).filter(
            MyBidRecord.bid_id == bid_id,
            MyBidRecord.user_id == user_id,
        ).first()
        if rec:
            rec.result            = data["result"].lower()
            rec.actual_winner_rate = data.get("winner_rate")

        db.commit()
        db.refresh(outcome)

        # 재학습 트리거 위임
        from .user_bids import MyBidFeedbackService
        MyBidFeedbackService(db)._check_retrain_trigger()

        return {"id": outcome.id, "result": outcome.result}

"""투찰 결정 서비스 — DecisionService."""
import logging
from sqlalchemy.orm import Session
from .models import Bid
from .ml.assessment import load_srate_stats, predict_srate
from .ml.simulation import (
    simulate_yejung_from_real, simulate_yejung, simulate_yejung_bimodal,
    scan_zones_from_dist, monte_carlo_win_prob_gmm,
)

logger = logging.getLogger(__name__)


class DecisionService:
    """투찰 결정 전용 서비스 — TenderDecisionPage 백엔드."""

    def get_bid_context(self, db: Session, bid_id: int) -> dict:
        from .ml.a_value import calc_floor_rate
        from .ml.yega import load_inpo21c_yega_stats
        from .ml.competitor_predict import predict_bid_zone
        from .ml.assessment import load_agency_srate_profile

        b = db.query(Bid).filter(Bid.id == bid_id).first()
        if not b:
            return {}

        industry_name = b.industry.name if b.industry else ""
        agency_id = b.agency_id or 0
        industry_id = b.industry_id or 0
        floor_rate = calc_floor_rate(industry_name)

        features = load_srate_stats(db, agency_id, industry_id, 0, b.base_amount)
        ep = predict_srate(features, b.base_amount)
        srate_center = ep["srate_range"]["center"]
        srate_std = (
            features.get("agency_srate_std")
            or features.get("global_srate_std")
            or 0.012
        )

        # B-4: 기관별 세분화 프로파일로 사정율 중심 보정
        agency_profile = {}
        try:
            agency_profile = load_agency_srate_profile(db, agency_id, industry_id, b.bid_open_date)
            if agency_profile.get("confidence", 0) >= 0.3:
                profile_center = agency_profile["blended_center"]
                conf = agency_profile["confidence"]
                srate_center = srate_center * (1 - conf * 0.4) + profile_center * (conf * 0.4)
                srate_center = round(srate_center, 5)
        except Exception:
            pass
        expected_n = int(
            features.get("expected_competitor_count")
            or features.get("global_comp_count")
            or 8
        )

        yega_stats = load_inpo21c_yega_stats(db, agency_id) if agency_id else {}
        pos_weights = yega_stats.get("pos_weights")

        competitor_zones: list = []
        try:
            czones = predict_bid_zone(db, agency_id, industry_id, b.base_amount)
            competitor_zones = czones if isinstance(czones, list) else []
        except Exception:
            pass

        from datetime import datetime as _dt, date as _date
        def _to_date(v):
            if v is None:
                return None
            if isinstance(v, _date) and not isinstance(v, _dt):
                return v
            if isinstance(v, _dt):
                return v.date()
            return v

        return {
            "bid_id":               b.id,
            "announcement_no":      b.announcement_no,
            "title":                b.title,
            "base_amount":          b.base_amount,
            "agency_id":            b.agency_id,
            "agency_name":          b.agency.name if b.agency else "",
            "industry_id":          b.industry_id,
            "industry_name":        industry_name,
            "floor_rate":           floor_rate,
            "a_value":              b.a_value,
            "srate_center":         round(srate_center, 4),
            "srate_std":            round(srate_std, 4),
            "expected_competitors": expected_n,
            "pos_weights":          pos_weights,
            "competitor_zones":     competitor_zones,
            "notice_date":          _to_date(b.notice_date),
            "bid_open_date":        _to_date(b.bid_open_date),
            "status":               b.status,
            "agency_srate_profile": {
                "blended_center":  agency_profile.get("blended_center"),
                "seasonal_adj":    agency_profile.get("seasonal_adj"),
                "trend_slope":     agency_profile.get("trend_slope"),
                "confidence":      agency_profile.get("confidence"),
            } if agency_profile else None,
        }

    def simulate_bid(self, db: Session, bid_id: int, req) -> dict:
        from itertools import combinations as _comb
        import numpy as _np
        from .ml.a_value import calc_floor_rate
        from .ml.yega import load_inpo21c_yega_stats, calc_yega_frequency
        from .ml.rank_model import get_inpo_raw_rates
        from .ml.simulation import monte_carlo_win_prob_empirical, monte_carlo_win_prob

        b = db.query(Bid).filter(Bid.id == bid_id).first()
        if not b:
            return {}

        industry_name = b.industry.name if b.industry else ""
        agency_id = b.agency_id or 0
        industry_id = b.industry_id or 0
        base_amount = b.base_amount
        if not base_amount or base_amount <= 0:
            return {"error": "base_amount_missing", "bid_id": bid_id}
        floor_rate = calc_floor_rate(industry_name)

        features = load_srate_stats(db, agency_id, industry_id, 0, base_amount)
        ep = predict_srate(features, base_amount)
        srate_center = ep["srate_range"]["center"]
        srate_std = (
            features.get("agency_srate_std")
            or features.get("global_srate_std")
            or 0.012
        )

        yega_stats = load_inpo21c_yega_stats(db, agency_id) if agency_id else {}
        pos_weights = yega_stats.get("pos_weights")

        n_sim = min(max(req.n_sim, 5_000), 50_000)
        yega_values = req.yega_values

        if yega_values and len(yega_values) == 15 and all(v > 0 for v in yega_values):
            mode = "real"
            srate_dist = simulate_yejung_from_real(yega_values, base_amount)
            candidates = [
                {"idx": i + 1, "amount": int(yega_values[i]), "rate": round(yega_values[i] / base_amount, 4)}
                for i in range(15)
            ]
            vals = _np.array(yega_values, dtype=_np.float64)
            combos = [(list(c), float(vals[list(c)].mean())) for c in _comb(range(15), 4)]
            top_combos = sorted(combos, key=lambda x: abs(x[1] - base_amount * srate_center))[:20]
            top_combinations = [
                {
                    "combo": [i + 1 for i in c[0]],
                    "amount": int(round(c[1])),
                    "rate": round(c[1] / base_amount, 4),
                    "prob": round(1 / 1365, 5),
                }
                for c in top_combos
            ]
        else:
            mode = "estimated"
            rng = _np.random.default_rng(42)
            # 기관 사정율 분포의 bimodal 여부 감지: 사분위 범위가 넓고 표준편차가 큰 경우
            _use_bimodal = (
                srate_std > 0.010 or
                features.get("agency_srate_p75") is not None
                and features.get("agency_srate_p25") is not None
                and float(features["agency_srate_p75"] or 0) - float(features["agency_srate_p25"] or 0) > 0.018
            )
            if _use_bimodal:
                srate_dist = simulate_yejung_bimodal(
                    base_amount, srate_center, srate_std, n_sim, rng, pos_weights,
                    high_mix=min(0.40, srate_std * 4),
                )
                mode = "estimated_bimodal"
            else:
                srate_dist = simulate_yejung(base_amount, srate_center, srate_std, n_sim, rng, pos_weights)
            yega_res = calc_yega_frequency(base_amount, b.a_value, srate_center)
            candidates = [
                {"idx": i + 1, "amount": int(c["amount"]), "rate": round(c["rate"], 4)}
                for i, c in enumerate(yega_res.get("candidates", []))
            ]
            top_combinations = [
                {
                    "combo": [],
                    "amount": int(t["amount"]),
                    "rate": round(t["rate"], 4),
                    "prob": round(t["probability"], 5),
                }
                for t in yega_res.get("top10", [])
            ]

        expected_n = int(
            features.get("expected_competitor_count")
            or features.get("global_comp_count")
            or 8
        )
        inpo_rates = None
        manual_rates = req.competitor_rates if req.competitor_rates else None
        if manual_rates and len(manual_rates) >= 2:
            valid = [r for r in manual_rates if 0.80 <= r <= 1.00]
            if len(valid) >= 2:
                inpo_rates = valid
                expected_n = max(expected_n, len(valid))
        if inpo_rates is None:
            try:
                inpo_rates = get_inpo_raw_rates(db, expected_n)
            except Exception:
                pass
        # journal 낙찰자 투찰률로 보강 (기관별 실전 데이터)
        if inpo_rates is not None:
            try:
                from .ml.rank_model import get_journal_winner_rates
                _journal_rates = get_journal_winner_rates(db, agency_id)
                if _journal_rates is not None and len(_journal_rates) >= 5:
                    import numpy as _np2
                    _base = _np2.array(inpo_rates) if not isinstance(inpo_rates, _np2.ndarray) else inpo_rates
                    n_journal = min(len(_journal_rates), int(len(_base) * 0.3))
                    inpo_rates = _np2.concatenate([_base, _journal_rates[:n_journal]])
            except Exception:
                pass

        eff_floor = floor_rate * float(_np.median(srate_dist))
        rng2 = _np.random.default_rng(42)

        # GMM 파라미터 — DB 데이터로 피팅 시도 (scan_zones_from_dist 호출 전에 준비)
        _gmm_params = None
        try:
            from .ml.competitor_cluster import fit_from_db, get_cluster_params
            _gmm_params = fit_from_db(db)
        except Exception:
            pass

        all_zones, top_zones = scan_zones_from_dist(
            srate_dist, floor_rate, base_amount,
            inpo_rates, expected_n, n_sim=min(n_sim, 20_000),
            gmm_params=_gmm_params,
        )

        # 전략 투찰율: top_zones 승률 기반 → 없으면 floor 오프셋 fallback
        if top_zones:
            _by_wp   = sorted(top_zones, key=lambda z: z["win_prob"], reverse=True)
            _by_rate = sorted(top_zones, key=lambda z: z["rate"],     reverse=True)
            rate_agg = _by_wp[0]["rate"]    # 최고 승률 구간
            rate_con = _by_rate[0]["rate"]  # 최고 투찰율 구간 (높을수록 안전 마진)
            if rate_con <= rate_agg:
                rate_con = round(rate_agg + 0.0005, 4)
            if len(_by_wp) >= 2:
                rate_bal = _by_wp[1]["rate"]
                _lo, _hi = min(rate_agg, rate_con), max(rate_agg, rate_con)
                if not (_lo < rate_bal < _hi):
                    rate_bal = round((_lo + _hi) / 2, 4)
            else:
                rate_bal = round((rate_agg + rate_con) / 2, 4)
            rate_agg, rate_bal, rate_con = sorted([rate_agg, rate_bal, rate_con])
        else:
            rate_agg = round(eff_floor + 0.0003, 4)
            rate_bal = round(max(eff_floor + 0.0015, rate_agg + 0.0005), 4)
            rate_con = round(max(eff_floor + 0.003,  rate_bal + 0.0005), 4)
        # 낙찰하한 안전 보정
        rate_agg = max(rate_agg, round(eff_floor + 0.0001, 4))
        rate_bal = max(rate_bal, round(rate_agg + 0.0003, 4))
        rate_con = max(rate_con, round(rate_bal + 0.0003, 4))

        def _wp(r):
            # 우선순위: GMM > empirical inpo > pure Monte Carlo
            if _gmm_params is not None and expected_n > 0:
                return monte_carlo_win_prob_gmm(r, floor_rate, srate_dist, expected_n, n_sim, rng2, _gmm_params)
            if inpo_rates is not None and len(inpo_rates) >= 5 and expected_n > 0:
                return monte_carlo_win_prob_empirical(r, floor_rate, srate_dist, inpo_rates, expected_n, n_sim, rng2)
            return monte_carlo_win_prob(r, floor_rate, srate_dist, [], [], n_sim, rng2)

        # 회사 원가율 프로파일에서 가져오기 (없으면 업종 평균 적용)
        cost_rate = 0.0
        try:
            from .models import CompanyProfile
            prof = db.query(CompanyProfile).first()
            cost_rate = float(prof.cost_rate) if prof and prof.cost_rate else 0.0
        except Exception:
            pass
        # cost_rate: 기초금액 대비 비율. CompanyProfile 없으면 실효낙찰하한 × 0.99 사용.
        # (투찰금액의 99%가 원가 = 낙찰하한 직상 투찰 시 1% 마진)
        if not cost_rate or cost_rate <= 0:
            cost_rate = eff_floor * 0.990

        def _ep(r: float, wp_dict: dict) -> float:
            wp = wp_dict.get("win_prob", 0.0) or 0.0
            profit_margin = max(0.0, r - cost_rate)
            return round(wp * profit_margin * base_amount, 0)

        wp_agg = _wp(rate_agg)
        wp_bal = _wp(rate_bal)
        wp_con = _wp(rate_con)

        strategies = {
            "aggressive":   {**wp_agg, "rate": rate_agg, "amount": int(round(rate_agg * base_amount)), "label": "공격형",
                             "expected_profit": _ep(rate_agg, wp_agg)},
            "balanced":     {**wp_bal, "rate": rate_bal, "amount": int(round(rate_bal * base_amount)), "label": "균형형",
                             "expected_profit": _ep(rate_bal, wp_bal)},
            "conservative": {**wp_con, "rate": rate_con, "amount": int(round(rate_con * base_amount)), "label": "안정형",
                             "expected_profit": _ep(rate_con, wp_con)},
        }

        best = max(top_zones, key=lambda z: z["win_prob"]) if top_zones else None
        if best:
            optimal = {
                "rate":     best["rate"],
                "amount":   best["amount"],
                "win_prob": best["win_prob"],
                "srate":    round(float(_np.median(srate_dist)), 4),
                "floor_ok": best.get("floor_ok", True),
            }
        else:
            optimal = {}

        hist_counts, bin_edges = _np.histogram(srate_dist, bins=30)
        histogram = [
            {
                "bin_center": round(float((bin_edges[i] + bin_edges[i + 1]) / 2), 4),
                "count":      int(hist_counts[i]),
                "prob":       round(float(hist_counts[i]) / len(srate_dist), 4),
            }
            for i in range(len(hist_counts))
        ]
        # 전략 설명 (왜 이 투찰율인지)
        _source_label = "Monte Carlo top_zones" if top_zones else "floor+offset fallback"
        for k, _r in [("aggressive", rate_agg), ("balanced", rate_bal), ("conservative", rate_con)]:
            if k in strategies:
                strategies[k]["reason"] = (
                    f"inpo21c 실증 {_source_label} 기반 — "
                    f"floor {round(eff_floor*100,3)}% × "
                    f"{'최고 승률' if k=='aggressive' else '2위 승률' if k=='balanced' else '최고 마진'} 구간"
                )

        pred_log_id = None
        try:
            from .models import PredictionLogV2
            from .ml.engine import get_model_meta
            meta = get_model_meta()
            plog = PredictionLogV2(
                bid_id=bid_id,
                model_version=meta.get("version"),
                srate_pred_center=round(srate_center, 6),
                rate_aggressive=strategies["aggressive"]["rate"],
                rate_balanced=strategies["balanced"]["rate"],
                rate_conservative=strategies["conservative"]["rate"],
                win_prob_center=strategies["balanced"].get("win_prob"),
            )
            db.add(plog)
            db.commit()
            db.refresh(plog)
            pred_log_id = plog.id
        except Exception as _e:
            logger.warning(f"prediction_logs_v2 저장 실패: {_e}")

        return {
            "bid_id":           bid_id,
            "base_amount":      base_amount,
            "floor_rate":       floor_rate,
            "srate_center":     round(srate_center, 4),
            "srate_std":        round(srate_std, 4),
            "mode":             mode,
            "pred_log_id":      pred_log_id,
            "yega_candidates":  candidates,
            "top_combinations": top_combinations,
            "all_zones":        [dict(z) for z in all_zones],
            "top_zones":        [dict(z) for z in top_zones],
            "strategies":       strategies,
            "optimal":          optimal,
            "histogram":        histogram,
        }

    def get_agency_win_histogram(self, db: Session, bid_id: int) -> dict:
        """
        inpo21c 실증 데이터 기반 기관별 낙찰 분포.
        base_ratio(투찰/기초) 0.001 버킷 단위로 집계.
        """
        from sqlalchemy import text as _text
        from .models import Bid

        b = db.query(Bid).filter(Bid.id == bid_id).first()
        if not b or not b.agency_id:
            return {"bins": [], "data_source": "none", "total_wins": 0, "total_bids": 0, "inpo21c_n": 0}

        agency_id = b.agency_id

        # 기관별 집계
        rows = db.execute(_text("""
            SELECT
                ROUND(ip.base_ratio::numeric, 3)                     AS rate_bucket,
                COUNT(*)                                              AS total_cnt,
                SUM(CASE WHEN ip.is_winner THEN 1 ELSE 0 END)        AS win_cnt
            FROM inpo21c_participants ip
            JOIN inpo21c_bids ib ON ib.inpo21c_bid_id = ip.inpo21c_bid_id
            JOIN agencies a ON (
                TRIM(a.name) = TRIM(ib.agency_name)
                OR TRIM(ib.agency_name) LIKE '%%' || TRIM(a.name) || '%%'
                OR TRIM(a.name) LIKE '%%' || TRIM(ib.agency_name) || '%%'
            )
            WHERE a.id = :aid
              AND ip.base_ratio BETWEEN 0.855 AND 0.945
            GROUP BY rate_bucket
            ORDER BY rate_bucket
        """), {"aid": agency_id}).fetchall()

        data_source = "agency"
        if len(rows) < 5:
            # 기관 데이터 부족 → 전국 집계 fallback
            data_source = "national"
            rows = db.execute(_text("""
                SELECT
                    ROUND(base_ratio::numeric, 3) AS rate_bucket,
                    COUNT(*)                       AS total_cnt,
                    SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) AS win_cnt
                FROM inpo21c_participants
                WHERE base_ratio BETWEEN 0.855 AND 0.945
                GROUP BY rate_bucket
                ORDER BY rate_bucket
            """)).fetchall()

        bins = []
        total_wins = 0
        total_bids = 0
        for r in rows:
            bucket, total_cnt, win_cnt = float(r[0]), int(r[1]), int(r[2])
            win_rate = round(win_cnt / total_cnt, 4) if total_cnt > 0 else 0.0
            bins.append({
                "rate":        bucket,
                "total_count": total_cnt,
                "win_count":   win_cnt,
                "win_rate":    win_rate,
            })
            total_wins += win_cnt
            total_bids += total_cnt

        # 승률 기준 TOP 3 구간
        eligible = [b for b in bins if b["total_count"] >= 3]
        top_zones = sorted(eligible, key=lambda x: x["win_rate"], reverse=True)[:3]
        for i, z in enumerate(top_zones, 1):
            z["rank"] = i

        return {
            "bins":        bins,
            "top_zones":   top_zones,
            "total_wins":  total_wins,
            "total_bids":  total_bids,
            "data_source": data_source,
            "agency_id":   agency_id,
            "agency_name": b.agency.name if b.agency else "",
            "inpo21c_n":   total_bids,
        }

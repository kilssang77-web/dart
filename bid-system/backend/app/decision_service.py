"""투찰 결정 서비스 — DecisionService."""
import logging
from sqlalchemy.orm import Session
from .models import Bid
from .ml.assessment import load_srate_stats, predict_srate
from .ml.simulation import (
    simulate_yejung_from_real, simulate_yejung, simulate_yejung_bimodal,
    scan_zones_from_dist, monte_carlo_win_prob_gmm,
)
from .ml.personal import PersonalBiasAnalyzer
from .ml.features_p4 import load_p4_features

logger = logging.getLogger(__name__)


class DecisionService:
    """투찰 결정 전용 서비스 — TenderDecisionPage 백엔드."""

    def get_bid_context(self, db: Session, bid_id: int, user_id: int = 0) -> dict:
        from .ml.a_value import calc_floor_rate
        from .ml.yega import load_inpo21c_yega_stats
        from .ml.competitor_predict import predict_bid_zone
        from .ml.assessment import load_agency_srate_profile, predict_a_ratio

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

        yega_stats = load_inpo21c_yega_stats(db, agency_id, announcement_no=b.announcement_no) if agency_id else {}
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

        agency_name = b.agency.name if b.agency else ""

        personal_bias = None
        if user_id:
            try:
                personal_bias = PersonalBiasAnalyzer().compute(
                    db, user_id, agency_name=agency_name
                )
            except Exception:
                pass

        # Phase 4: 사전규격·계약정보 피처
        p4 = {}
        try:
            p4 = load_p4_features(
                db,
                agency_id=b.agency_id,
                bid_id=b.id,
                announcement_no=b.announcement_no,
            )
        except Exception:
            pass

        # A값 비율 4단계 모델
        a_ratio_result = {}
        try:
            a_ratio_result = predict_a_ratio(db, agency_id or None, industry_id or None, b.base_amount or 0)
        except Exception:
            pass

        return {
            "bid_id":               b.id,
            "announcement_no":      b.announcement_no,
            "title":                b.title,
            "base_amount":          b.base_amount,
            "agency_id":            b.agency_id,
            "agency_name":          agency_name,
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
            "personal_bias":        personal_bias,
            # Phase 4 피처
            "pre_spec_gap_days":    p4.get("pre_spec_gap_days"),
            "has_pre_spec":         p4.get("has_pre_spec", False),
            "agency_contract_freq": p4.get("agency_contract_freq"),
            "joint_bid_prob":       p4.get("joint_bid_prob"),
            # A값 비율 모델 (4단계 계층)
            "a_ratio":              a_ratio_result.get("ratio"),
            "a_ratio_level":        a_ratio_result.get("level", "L1"),
            "a_ratio_sample_count": a_ratio_result.get("sample_count", 0),
            "a_ratio_std":          a_ratio_result.get("std"),
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

        yega_stats = load_inpo21c_yega_stats(db, agency_id, announcement_no=b.announcement_no) if agency_id else {}
        pos_weights = yega_stats.get("pos_weights")
        spread_half = yega_stats.get("spread_half", 0.028)

        n_sim = min(max(req.n_sim, 5_000), 50_000)
        yega_values = req.yega_values

        if yega_values and len(yega_values) == 15 and all(v > 0 for v in yega_values):
            mode = "real"
            srate_dist = simulate_yejung_from_real(yega_values, base_amount)
            candidates = [
                {"idx": i + 1, "amount": int(yega_values[i]), "rate": round(yega_values[i] / base_amount, 6)}
                for i in range(15)
            ]
            vals = _np.array(yega_values, dtype=_np.float64)
            combos = [(list(c), float(vals[list(c)].mean())) for c in _comb(range(15), 4)]
            top_combos = sorted(combos, key=lambda x: abs(x[1] - base_amount * srate_center))[:20]
            top_combinations = [
                {
                    "combo": [i + 1 for i in c[0]],
                    "amount": int(round(c[1])),
                    "rate": round(c[1] / base_amount, 6),
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
                    spread_half=spread_half,
                )
                mode = "estimated_bimodal"
            else:
                srate_dist = simulate_yejung(base_amount, srate_center, srate_std, n_sim, rng, pos_weights, spread_half)
            yega_res = calc_yega_frequency(base_amount, b.a_value, srate_center)
            candidates = [
                {"idx": i + 1, "amount": int(c["amount"]), "rate": round(c["rate"], 6)}
                for i, c in enumerate(yega_res.get("candidates", []))
            ]
            top_combinations = [
                {
                    "combo": [],
                    "amount": int(t["amount"]),
                    "rate": round(t["rate"], 6),
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

        # 낙찰자 실측 투찰율 — centroid 교정 전용 (경쟁자 pool과 분리)
        _winner_rates_centroid = None
        try:
            from .ml.hotzone import _query_bid_rate_dist
            _hz_rows, _ = _query_bid_rate_dist(db, agency_id, 24)
            if _hz_rows:
                _hz_wc = _np.array(
                    [float(r[4]) for r in _hz_rows if r[4] is not None and 0.80 <= float(r[4]) <= 1.00],
                    dtype=_np.float64,
                )
                if len(_hz_wc) >= 3:
                    _winner_rates_centroid = _hz_wc
        except Exception:
            pass

        all_zones, top_zones = scan_zones_from_dist(
            srate_dist, floor_rate, base_amount,
            inpo_rates, expected_n, n_sim=min(n_sim // 10, 3_000),
            gmm_params=_gmm_params,
            winner_rates=_winner_rates_centroid,
        )

        # 전략 투찰율: top_zones 승률 기반 → 없으면 floor 오프셋 fallback
        if top_zones:
            _by_wp   = sorted(top_zones, key=lambda z: z["win_prob"], reverse=True)
            _by_rate = sorted(top_zones, key=lambda z: z["rate"],     reverse=True)
            rate_agg = _by_wp[0]["rate"]    # 최고 승률 구간
            rate_con = _by_rate[0]["rate"]  # 최고 투찰율 구간 (높을수록 안전 마진)
            if rate_con <= rate_agg:
                rate_con = round(rate_agg + 0.0005, 6)
            if len(_by_wp) >= 2:
                rate_bal = _by_wp[1]["rate"]
                _lo, _hi = min(rate_agg, rate_con), max(rate_agg, rate_con)
                if not (_lo < rate_bal < _hi):
                    rate_bal = round((_lo + _hi) / 2, 6)
            else:
                rate_bal = round((rate_agg + rate_con) / 2, 6)
            rate_agg, rate_bal, rate_con = sorted([rate_agg, rate_bal, rate_con])
        else:
            rate_agg = round(eff_floor + 0.0003, 6)
            rate_bal = round(max(eff_floor + 0.0015, rate_agg + 0.0005), 6)
            rate_con = round(max(eff_floor + 0.003,  rate_bal + 0.0005), 6)
        # 낙찰하한 안전 보정
        rate_agg = max(rate_agg, round(eff_floor + 0.0001, 6))
        rate_bal = max(rate_bal, round(rate_agg + 0.0003, 6))
        rate_con = max(rate_con, round(rate_bal + 0.0003, 6))

        # 실증 낙찰확률 모델 로드 (base_ratio → bid_rate 변환 필요)
        _srate_med = float(_np.median(srate_dist))

        def _wp(r):
            # 0순위: 실증 win_prob_model (inpo21c 실제 낙찰 이력 기반)
            # win_prob_model은 ip.bid_rate(= base_ratio) 단위로 학습됨 → r을 그대로 전달
            try:
                from .ml.win_prob_model import predict as _wpm_predict
                _emp = _wpm_predict(
                    r, _srate_med, expected_n, floor_rate
                )
                if _emp >= 0:
                    return {"win_prob": _emp, "avg_rank": None, "valid_ratio": 1.0}
            except Exception:
                pass
            # 1순위: GMM
            if _gmm_params is not None and expected_n > 0:
                return monte_carlo_win_prob_gmm(r, floor_rate, srate_dist, expected_n, n_sim, rng2, _gmm_params)
            # 2순위: empirical inpo
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

        # P1: 확보예가 BidScore — 최적 투찰율 기준으로 계산
        bid_score_data = None
        try:
            from .ml.simulation import calc_bid_score
            _opt_rate = optimal.get("rate") if optimal else None
            if _opt_rate:
                bid_score_data = calc_bid_score(srate_dist, _opt_rate, floor_rate)
                # 각 전략에도 BidScore 추가
                for _k, _r in [("aggressive", rate_agg), ("balanced", rate_bal), ("conservative", rate_con)]:
                    if _k in strategies:
                        _bs = calc_bid_score(srate_dist, _r, floor_rate)
                        strategies[_k]["bid_score"] = _bs
        except Exception as _bs_err:
            logger.warning(f"BidScore 계산 실패 (무시): {_bs_err}")

        # P1 Benchmark: 동일 기관/금액대 과거 낙찰자 BidScore 분포
        bid_score_benchmark = None
        try:
            from sqlalchemy import text as _text

            _AGENCY_TYPE_KW = [
                "교육청", "교육지원청", "시청", "군청", "구청", "도청",
                "공사", "공단", "대학교", "대학", "공기업", "공공기관",
            ]

            def _extract_agency_type(name: str) -> str | None:
                for kw in _AGENCY_TYPE_KW:
                    if kw in name:
                        return kw
                return None

            _agency_name = b.agency.name if b.agency else None
            if _agency_name and base_amount > 0:
                _amount_min = int(base_amount * 0.5)
                _amount_max = int(base_amount * 2.0)
                _base_sql = """
                    SELECT ip.base_ratio
                    FROM inpo21c_participants ip
                    JOIN inpo21c_bids ib ON ib.inpo21c_bid_id = ip.inpo21c_bid_id
                    WHERE ip.is_winner = TRUE
                      AND ip.base_ratio BETWEEN 0.80 AND 1.05
                      AND ib.base_amount BETWEEN :amount_min AND :amount_max
                """

                # 1차: 기관명 정확 매칭 또는 prefix 6자 매칭
                _agency_prefix = _agency_name[:6] if len(_agency_name) >= 6 else _agency_name
                _rows = db.execute(_text(_base_sql + """
                      AND (TRIM(ib.agency_name) = TRIM(:agency_name)
                           OR TRIM(ib.agency_name) LIKE :agency_like)
                      AND ib.open_datetime >= NOW() - INTERVAL '2 years'
                    LIMIT 400
                """), {
                    "agency_name": _agency_name,
                    "agency_like": f"%{_agency_prefix}%",
                    "amount_min":  _amount_min,
                    "amount_max":  _amount_max,
                }).fetchall()
                _scope = "agency"

                # 2차 폴백: 기관 종류(교육청/시청/공사 등) 키워드 매칭
                if len(_rows) < 5:
                    _kw = _extract_agency_type(_agency_name)
                    if _kw:
                        _rows = db.execute(_text(_base_sql + """
                              AND ib.agency_name LIKE :kw_like
                              AND ib.open_datetime >= NOW() - INTERVAL '3 years'
                            LIMIT 400
                        """), {
                            "kw_like":   f"%{_kw}%",
                            "amount_min": _amount_min,
                            "amount_max": _amount_max,
                        }).fetchall()
                        _scope = "similar_agency"

                # 3차 폴백: 금액대 전국 평균
                if len(_rows) < 5:
                    _rows = db.execute(_text(_base_sql + """
                          AND ib.open_datetime >= NOW() - INTERVAL '2 years'
                        LIMIT 400
                    """), {
                        "amount_min": _amount_min,
                        "amount_max": _amount_max,
                    }).fetchall()
                    _scope = "national"

                _winner_rates = _np.array([
                    float(r[0]) for r in _rows if r[0] is not None
                ])
                if len(_winner_rates) >= 5:
                    from .ml.simulation import calc_bid_score_benchmark
                    bid_score_benchmark = calc_bid_score_benchmark(
                        srate_dist, _winner_rates, floor_rate
                    )
                    bid_score_benchmark["scope"] = _scope
        except Exception as _bsb_err:
            logger.warning(f"BidScore 벤치마크 계산 실패 (무시): {_bsb_err}")

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
            "bid_score":           bid_score_data,
            "bid_score_benchmark": bid_score_benchmark,
        }

    def get_win_prob_curve(self, db: Session, bid_id: int) -> dict:
        """
        bid_rate 구간별 모델 낙찰확률 곡선 — TenderDecisionPage 시각화용.
        bid_id로 해당 공고의 srate_center, expected_competitors 추출 후 predict_curve 호출.
        """
        from .ml.win_prob_model import predict_curve as _wpc
        from .ml.a_value import calc_floor_rate
        from .ml.assessment import load_srate_stats
        import numpy as _np

        b = db.query(Bid).filter(Bid.id == bid_id).first()
        if not b:
            return {"curve": [], "srate": 0.90, "n_competitors": 8}

        industry_name = b.industry.name if b.industry else ""
        floor_rate    = calc_floor_rate(industry_name)
        features      = load_srate_stats(db, b.agency_id or 0, b.industry_id or 0, 0, b.base_amount)
        from .ml.assessment import predict_srate as _ps
        ep            = _ps(features, b.base_amount)
        srate         = float(ep["srate_range"]["center"])
        expected_n    = int(
            features.get("expected_competitor_count")
            or features.get("global_comp_count")
            or 8
        )

        curve = _wpc(srate, expected_n, floor_rate)
        return {
            "curve":        curve,
            "srate":        round(srate, 4),
            "floor_rate":   round(floor_rate, 4),
            "n_competitors": expected_n,
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

    def get_competitor_prediction(self, db: Session, bid_id: int, top_n: int = 15) -> dict:
        """
        경쟁사 투찰 구간 예측 — inpo21c 이력 기반.
        기관 우선 매칭 → 부족 시 공종 전국 fallback.
        각 경쟁사의 P25-P75 구간 = "이 회사가 이 기관에서 주로 투찰하는 구간"
        """
        from sqlalchemy import text as _text
        from .models import Bid

        b = db.query(Bid).filter(Bid.id == bid_id).first()
        if not b:
            return {"competitors": [], "match_type": "none", "agency_name": "", "data_points": 0}

        agency_name = b.agency.name if b.agency else ""
        industry_name = b.industry.name if b.industry else ""

        # ── 1) 기관별 경쟁사 패턴 ──────────────────────────────
        AGENCY_SQL = _text("""
            SELECT
                ip.company_name,
                ip.biz_reg_no,
                COUNT(*)                                                    AS total_bids,
                COUNT(CASE WHEN ip.is_winner THEN 1 END)                   AS wins,
                ROUND(AVG(ip.bid_rate)::numeric * 100, 3)                  AS avg_rate_pct,
                ROUND(STDDEV(ip.bid_rate)::numeric * 100, 4)               AS std_pct,
                ROUND(PERCENTILE_CONT(0.10) WITHIN GROUP (ORDER BY ip.bid_rate::float8) * 100, 3) AS p10,
                ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY ip.bid_rate::float8) * 100, 3) AS p25,
                ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY ip.bid_rate::float8) * 100, 3) AS p50,
                ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY ip.bid_rate::float8) * 100, 3) AS p75,
                ROUND(PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY ip.bid_rate::float8) * 100, 3) AS p90,
                MAX(ib.open_datetime)::date                                 AS last_seen
            FROM inpo21c_participants ip
            JOIN inpo21c_bids ib ON ib.inpo21c_bid_id = ip.inpo21c_bid_id
            WHERE (
                TRIM(ib.agency_name) = TRIM(:agency)
                OR TRIM(ib.agency_name) LIKE '%%' || TRIM(:agency) || '%%'
                OR TRIM(:agency) LIKE '%%' || TRIM(ib.agency_name) || '%%'
            )
              AND ip.bid_rate IS NOT NULL AND ip.bid_rate > 0.5
              AND ip.bid_rate < 1.5
            GROUP BY ip.company_name, ip.biz_reg_no
            HAVING COUNT(*) >= 2
            ORDER BY total_bids DESC
            LIMIT :top_n
        """)

        rows = db.execute(AGENCY_SQL, {"agency": agency_name, "top_n": top_n}).fetchall()
        match_type = "agency"
        data_points = len(rows)

        # ── 2) 기관 데이터 부족 → 공종 전국 fallback ─────────
        if len(rows) < 5 and industry_name:
            INDUSTRY_SQL = _text("""
                SELECT
                    ip.company_name,
                    ip.biz_reg_no,
                    COUNT(*)                                                    AS total_bids,
                    COUNT(CASE WHEN ip.is_winner THEN 1 END)                   AS wins,
                    ROUND(AVG(ip.bid_rate)::numeric * 100, 3)                  AS avg_rate_pct,
                    ROUND(STDDEV(ip.bid_rate)::numeric * 100, 4)               AS std_pct,
                    ROUND(PERCENTILE_CONT(0.10) WITHIN GROUP (ORDER BY ip.bid_rate::float8) * 100, 3) AS p10,
                    ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY ip.bid_rate::float8) * 100, 3) AS p25,
                    ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY ip.bid_rate::float8) * 100, 3) AS p50,
                    ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY ip.bid_rate::float8) * 100, 3) AS p75,
                    ROUND(PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY ip.bid_rate::float8) * 100, 3) AS p90,
                    MAX(ib.open_datetime)::date                                 AS last_seen
                FROM inpo21c_participants ip
                JOIN inpo21c_bids ib ON ib.inpo21c_bid_id = ip.inpo21c_bid_id
                WHERE (
                    TRIM(ib.industry) LIKE '%%' || TRIM(:industry) || '%%'
                    OR TRIM(:industry) LIKE '%%' || TRIM(ib.industry) || '%%'
                )
                  AND ip.bid_rate IS NOT NULL AND ip.bid_rate > 0.5
                  AND ip.bid_rate < 1.5
                GROUP BY ip.company_name, ip.biz_reg_no
                HAVING COUNT(*) >= 5
                ORDER BY total_bids DESC
                LIMIT :top_n
            """)
            rows = db.execute(INDUSTRY_SQL, {"industry": industry_name, "top_n": top_n}).fetchall()
            match_type = "industry"
            data_points = len(rows)

        # ── 3) 전국 fallback ───────────────────────────────────
        if len(rows) < 3:
            NATIONAL_SQL = _text("""
                SELECT
                    ip.company_name,
                    ip.biz_reg_no,
                    COUNT(*)                                                    AS total_bids,
                    COUNT(CASE WHEN ip.is_winner THEN 1 END)                   AS wins,
                    ROUND(AVG(ip.bid_rate)::numeric * 100, 3)                  AS avg_rate_pct,
                    ROUND(STDDEV(ip.bid_rate)::numeric * 100, 4)               AS std_pct,
                    ROUND(PERCENTILE_CONT(0.10) WITHIN GROUP (ORDER BY ip.bid_rate::float8) * 100, 3) AS p10,
                    ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY ip.bid_rate::float8) * 100, 3) AS p25,
                    ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY ip.bid_rate::float8) * 100, 3) AS p50,
                    ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY ip.bid_rate::float8) * 100, 3) AS p75,
                    ROUND(PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY ip.bid_rate::float8) * 100, 3) AS p90,
                    MAX(ib.open_datetime)::date                                 AS last_seen
                FROM inpo21c_participants ip
                JOIN inpo21c_bids ib ON ib.inpo21c_bid_id = ip.inpo21c_bid_id
                WHERE ip.bid_rate IS NOT NULL AND ip.bid_rate > 0.5 AND ip.bid_rate < 1.5
                GROUP BY ip.company_name, ip.biz_reg_no
                HAVING COUNT(*) >= 20
                ORDER BY total_bids DESC
                LIMIT :top_n
            """)
            rows = db.execute(NATIONAL_SQL, {"top_n": top_n}).fetchall()
            match_type = "national"
            data_points = len(rows)

        # ── 공격성 분류 ────────────────────────────────────────
        def _aggression(avg: float, p25: float, p75: float, std: float) -> str:
            # 평균이 높을수록 공격적 (높게 투찰), 분산이 클수록 불안정
            if avg >= 91.0:
                return "aggressive"
            elif avg <= 89.5:
                return "conservative"
            elif std is not None and float(std) >= 3.0:
                return "volatile"
            else:
                return "balanced"

        competitors = []
        for r in rows:
            avg = float(r[4]) if r[4] is not None else None
            std = float(r[5]) if r[5] is not None else None
            p25 = float(r[7]) if r[7] is not None else None
            p50 = float(r[8]) if r[8] is not None else None
            p75 = float(r[9]) if r[9] is not None else None
            win_rate = round(int(r[3]) / int(r[2]), 4) if int(r[2]) > 0 else 0.0

            competitors.append({
                "company_name":   r[0],
                "biz_reg_no":     r[1] or "",
                "total_bids":     int(r[2]),
                "wins":           int(r[3]),
                "win_rate":       win_rate,
                "avg_rate_pct":   avg,
                "std_pct":        std,
                "p10_pct":        float(r[6]) if r[6] is not None else None,
                "p25_pct":        p25,
                "p50_pct":        p50,
                "p75_pct":        p75,
                "p90_pct":        float(r[10]) if r[10] is not None else None,
                "typical_range":  [p25, p75] if p25 and p75 else None,
                "aggression":     _aggression(avg or 90.0, p25 or 90.0, p75 or 90.0, std or 1.0),
                "last_seen":      str(r[11]) if r[11] else None,
            })

        return {
            "competitors":  competitors,
            "match_type":   match_type,
            "agency_name":  agency_name,
            "industry_name": industry_name,
            "data_points":  data_points,
        }

    def get_position_analysis(self, db: Session, bid_id: int) -> dict:
        """
        A값 추첨 포지션 이력 기반 투찰율 추천.

        inpo21c_yega.is_selected 실측 데이터로 기관별 추첨 선호 포지션을 분석하고
        해당 포지션 조합의 예정가격을 계산해 최적 투찰율을 반환한다.
        """
        from .ml.yega import get_position_bid_recommendation
        from .ml.a_value import calc_floor_rate

        b = db.query(Bid).filter(Bid.id == bid_id).first()
        if not b:
            return {"bid_id": bid_id, "has_data": False}

        industry_name = b.industry.name if b.industry else ""
        floor_rate    = calc_floor_rate(industry_name)
        a_value       = b.a_value or int((b.base_amount or 0) * 0.8876)

        if not b.base_amount or b.base_amount <= 0:
            return {"bid_id": bid_id, "has_data": False}

        result = get_position_bid_recommendation(
            db,
            agency_id   = b.agency_id,
            a_value     = a_value,
            base_amount = b.base_amount,
            floor_rate  = floor_rate,
        )
        result["bid_id"]   = bid_id
        result["has_data"] = result["sample_count"] > 0
        return result

    def get_quick_decision(self, db: Session, bid_id: int, user_id: int = 0) -> dict:
        """
        1화면 의사결정 집계 — 핵심 신호만 종합하여 GO/PASS/NEUTRAL 판정 반환.

        우선순위:
          1. 낙찰확률 (win_prob_model)
          2. 경쟁 강도 (expected_competitors)
          3. A값 포지션 신뢰도
          4. 기관 낙찰율
        """
        import numpy as _np
        from .ml.a_value import calc_floor_rate
        from .ml.assessment import load_srate_stats, predict_srate
        from .ml.hotzone import get_best_rate
        from .ml.win_prob_model import predict as _wpm_predict

        b = db.query(Bid).filter(Bid.id == bid_id).first()
        if not b:
            return {}

        industry_name = b.industry.name if b.industry else ""
        agency_id     = b.agency_id or 0
        industry_id   = b.industry_id or 0
        base_amount   = b.base_amount or 0
        from .ml.a_value import calc_floor_rate_with_agency
        _floor_data = calc_floor_rate_with_agency(db, agency_id, industry_name)
        floor_rate    = _floor_data["floor_rate"]
        _agency_a_ratio = _floor_data["a_ratio"]
        _a_ratio_confidence = _floor_data["a_ratio_confidence"]
        _a_ratio_sample_count = _floor_data["a_ratio_sample_count"]

        features = load_srate_stats(db, agency_id, industry_id, 0, base_amount)
        ep        = predict_srate(features, base_amount)
        srate_med = float(ep["srate_range"]["center"])
        expected_n = int(features.get("expected_competitor_count") or features.get("global_comp_count") or 8)

        # 최적 투찰율 (best_rate)
        best = get_best_rate(db, agency_id, base_amount, period_type="24M")
        recommended_rate   = best.get("recommended_srate")
        recommended_amount = best.get("recommended_price")
        best_source        = best.get("source", "fallback")
        confidence         = float(best.get("confidence", 0.30))

        # 낙찰확률
        win_prob = 0.0
        if recommended_rate:
            try:
                wp = _wpm_predict(recommended_rate, srate_med, expected_n, floor_rate)
                win_prob = max(0.0, float(wp))
            except Exception:
                pass

        # 기관 낙찰율
        agency_win_rate = None
        try:
            from sqlalchemy import text as _t
            row = db.execute(_t("""
                SELECT ROUND(AVG(CASE WHEN ip.is_winner THEN 1.0 ELSE 0.0 END), 4)
                FROM inpo21c_participants ip
                JOIN inpo21c_bids ib USING (inpo21c_bid_id)
                JOIN agencies a ON (
                    TRIM(a.name) = TRIM(ib.agency_name)
                    OR TRIM(ib.agency_name) LIKE '%%' || TRIM(a.name) || '%%'
                )
                WHERE a.id = :aid AND ib.open_datetime >= NOW() - INTERVAL '24 months'
            """), {"aid": agency_id}).scalar()
            agency_win_rate = float(row) if row is not None else None
        except Exception:
            pass

        # 포지션 분석
        pos = self.get_position_analysis(db, bid_id)
        position_top4 = pos.get("top_positions", [])

        # GO/PASS 판정
        reasons, risks = [], []
        go_score = 0.5  # 기본 중립

        # 낙찰확률 기여
        if win_prob >= 0.35:
            go_score += 0.20
            reasons.append(f"AI 낙찰확률 {win_prob*100:.0f}% — 양호한 수준")
        elif win_prob >= 0.20:
            go_score += 0.05
            reasons.append(f"AI 낙찰확률 {win_prob*100:.0f}% — 보통 수준")
        else:
            go_score -= 0.15
            risks.append(f"AI 낙찰확률 {win_prob*100:.0f}% — 경쟁 강도 높음")

        # 경쟁자 수
        if expected_n <= 5:
            go_score += 0.15
            reasons.append(f"예상 경쟁사 {expected_n}개 — 비교적 소수")
        elif expected_n <= 10:
            go_score += 0.05
        elif expected_n >= 15:
            go_score -= 0.20
            risks.append(f"예상 경쟁사 {expected_n}개 이상 — 과열 경쟁 우려")
        else:
            risks.append(f"예상 경쟁사 {expected_n}개 — 보통 수준 경쟁")

        # 기관 낙찰율
        if agency_win_rate is not None:
            if agency_win_rate >= 0.12:
                go_score += 0.10
                reasons.append(f"이 기관 낙찰율 {agency_win_rate*100:.1f}% — 높은 편")
            elif agency_win_rate <= 0.05:
                go_score -= 0.10
                risks.append(f"이 기관 낙찰율 {agency_win_rate*100:.1f}% — 낮은 편")

        # 기관 A값 자동학습 신뢰도 반영
        if _a_ratio_confidence >= 0.7:
            go_score += 0.04
            reasons.append(f"기관 A값 비율 자동학습 고신뢰 ({_a_ratio_sample_count}건, {_agency_a_ratio*100:.2f}%)")
        elif _a_ratio_confidence >= 0.3:
            go_score += 0.01
            reasons.append(f"기관 A값 부분 학습 ({_a_ratio_sample_count}건)")

        # 포지션 데이터 신뢰도
        if pos.get("confidence", 0) >= 0.60:
            go_score += 0.05
            reasons.append(f"A값 포지션 분석 고신뢰 ({pos['sample_count']}건 이력)")

        # 추천 소스
        if best_source in ("winner+hotzone", "winner"):
            go_score += 0.05
            reasons.append("실증 낙찰자 분포 기반 추천율 활용")

        # ── KISCON 경쟁사 위험도 연동 ──────────────────────────────
        kiscon_risk_count = 0
        kiscon_strong_count = 0
        try:
            from sqlalchemy import text as _ksql
            agency_display = db.execute(_ksql(
                "SELECT name FROM agencies WHERE id = :aid"
            ), {"aid": agency_id}).scalar() or ""

            if agency_display:
                # 강점 기관(risk_agencies)에 이 발주처가 있는 경쟁사 수
                risk_rows = db.execute(_ksql("""
                    SELECT ckp.corp_name, ckp.win_count_2y, ckp.bid_count_2y
                    FROM competitor_kiscon_profiles ckp
                    WHERE :agency LIKE ANY(
                        SELECT '%' || unnest(ckp.risk_agencies) || '%'
                    )
                    AND ckp.win_count_2y > 0
                    LIMIT 10
                """), {"agency": agency_display}).fetchall()

                # 주력 기관(top_agencies)에 이 발주처가 있는 경쟁사 수
                top_rows = db.execute(_ksql("""
                    SELECT COUNT(*)
                    FROM competitor_kiscon_profiles ckp
                    WHERE :agency LIKE ANY(
                        SELECT '%' || unnest(ckp.top_agencies) || '%'
                    )
                    AND ckp.bid_count_2y >= 3
                """), {"agency": agency_display}).scalar() or 0

                kiscon_risk_count  = len(risk_rows)
                kiscon_strong_count = int(top_rows)

                if kiscon_risk_count >= 3:
                    go_score -= 0.12
                    risks.append(f"KISCON 강점 경쟁사 {kiscon_risk_count}개 — 이 기관 낙찰률 30%+ 업체들")
                elif kiscon_risk_count >= 1:
                    go_score -= 0.05
                    risks.append(f"KISCON 위험 경쟁사 {kiscon_risk_count}개 활동 중")

                if kiscon_strong_count >= 5:
                    go_score -= 0.05
                    risks.append(f"주력 경쟁사 {kiscon_strong_count}개 이 기관 집중")
        except Exception:
            pass

        # ── 기관 시즌 패턴 반영 ────────────────────────────────────
        try:
            from datetime import datetime as _dt2
            import calendar as _cal
            open_dt = b.bid_open_date
            if open_dt:
                month = open_dt.month if hasattr(open_dt, 'month') else open_dt.split('-')[1]
                month = int(month)
                # Q4 예산 소진기 (10-12월): 기관 집중 발주 → 경쟁 심화
                if month in (10, 11, 12):
                    go_score -= 0.03
                    risks.append("Q4 예산소진기 — 경쟁 집중 시기")
                # Q1 (1-3월): 신규 예산 집행 시작 → 경쟁 완화
                elif month in (1, 2, 3):
                    go_score += 0.03
                    reasons.append("Q1 신규예산기 — 경쟁 완화 시기")
        except Exception:
            pass

        go_score = round(max(0.0, min(1.0, go_score)), 3)

        if go_score >= 0.65:
            go_decision = "go"
        elif go_score <= 0.38:
            go_decision = "pass"
        else:
            go_decision = "neutral"

        # 5등급제: S/A/B/C/F
        score_pct = go_score * 100
        if score_pct >= 78:
            grade = "S"
        elif score_pct >= 65:
            grade = "A"
        elif score_pct >= 50:
            grade = "B"
        elif score_pct >= 38:
            grade = "C"
        else:
            grade = "F"

        # 데이터 품질 수준 (1~5) — string→int 변환
        _dql_map = {"global": 1, "industry": 2, "bid_type": 3, "region": 3, "agency": 5}
        _dql_raw = features.get("data_quality_level") or "global"
        if isinstance(_dql_raw, str):
            dql = _dql_map.get(_dql_raw, 1)
        else:
            dql = max(1, min(5, int(_dql_raw)))

        # 신호별 점수 (0~1) — 프론트 신호 행렬용
        signal_win_prob   = round(min(1.0, win_prob / 0.35), 3) if win_prob else 0.0
        signal_competition = round(max(0.0, 1.0 - (expected_n - 3) / 17), 3)
        signal_data_quality = round(dql / 5, 3)
        signal_agency       = round(min(1.0, (agency_win_rate or 0.0) / 0.15), 3)
        signal_confidence   = round(min(1.0, confidence / 0.70), 3)

        return {
            "bid_id":               bid_id,
            "title":                b.title,
            "base_amount":          base_amount,
            "recommended_rate":     recommended_rate,
            "recommended_amount":   recommended_amount,
            "win_prob":             round(win_prob, 4),
            "go_decision":          go_decision,
            "go_score":             go_score,
            "grade":                grade,
            "data_quality_level":   dql,
            "signals": {
                "win_prob":     signal_win_prob,
                "competition":  signal_competition,
                "data_quality": signal_data_quality,
                "agency_rate":  signal_agency,
                "confidence":   signal_confidence,
            },
            "confidence":           round(confidence, 3),
            "reasons":              reasons[:5],
            "risk_factors":         risks[:4],
            "expected_competitors": expected_n,
            "agency_win_rate":      round(agency_win_rate, 4) if agency_win_rate else None,
            "best_rate_source":     best_source,
            "position_top4":        position_top4,
            "floor_rate":           floor_rate,
            "kiscon_risk_count":    kiscon_risk_count,
            "kiscon_strong_count":  kiscon_strong_count,
            "agency_a_ratio":       round(_agency_a_ratio, 5),
            "a_ratio_confidence":   round(_a_ratio_confidence, 3),
            "a_ratio_sample_count": _a_ratio_sample_count,
        }

    def get_pq_floor(self, db: Session, bid_id: int) -> dict:
        """P2: PQ 적격심사 기준 최저 투찰율 계산 — CompanyProfile 자동 연동."""
        from .ml.qualification import check_qualification
        from .models import CompanyProfile

        b = db.query(Bid).filter(Bid.id == bid_id).first()
        if not b:
            return {}

        base_amount = b.base_amount or 0
        # 추정가격 1억 미만은 PQ 적격심사 미해당
        if base_amount < 100_000_000:
            return {
                "bid_id":          bid_id,
                "applicable":      False,
                "pq_floor_rate":   None,
                "pq_floor_amount": None,
                "verdict":         "NOT_APPLICABLE",
                "pass_prob":       1.0,
                "score_breakdown": {},
                "criteria_type":   "none",
                "warning":         None,
            }

        # 사정율 예측
        agency_id  = b.agency_id  or 0
        industry_id = b.industry_id or 0
        features = load_srate_stats(db, agency_id, industry_id, 0, base_amount)
        ep = predict_srate(features, base_amount)
        srate_center = ep["srate_range"]["center"]
        srate_std = features.get("agency_srate_std") or features.get("global_srate_std") or 0.012

        # CompanyProfile에서 PQ 입력값 추출
        prof = db.query(CompanyProfile).first()
        our_experience  = 0
        annual_revenue  = 0
        workforce_count = 0
        if prof:
            annual_revenue  = int(prof.annual_revenue or 0)
            workforce_count = int(prof.workforce_count or 0)
            for cap in (prof.construction_capabilities or []):
                if isinstance(cap, dict):
                    our_experience = max(our_experience, int(cap.get("performance", 0) or 0))

        result = check_qualification(
            base_amount=base_amount,
            estimated_price_center=srate_center,
            estimated_price_std=srate_std,
            our_experience=our_experience,
            annual_revenue=annual_revenue,
            workforce_count=workforce_count,
        )

        pq_floor_rate = None
        if result.min_pass_amount and base_amount > 0:
            pq_floor_rate = round(result.min_pass_amount / base_amount, 6)

        warning = None
        if result.verdict == "FAIL":
            warning = f"적격심사 통과 확률 {result.pass_prob:.0%} — 이 공고는 PQ 통과가 어렵습니다"
        elif result.verdict == "UNCERTAIN" and pq_floor_rate:
            warning = f"PQ 최저 통과 투찰율 {pq_floor_rate*100:.4f}% — 이 이하 투찰 시 낙찰 후 계약 취소 위험"

        return {
            "bid_id":          bid_id,
            "applicable":      True,
            "pq_floor_rate":   pq_floor_rate,
            "pq_floor_amount": result.min_pass_amount,
            "verdict":         result.verdict,
            "pass_prob":       result.pass_prob,
            "score_breakdown": result.score_breakdown,
            "criteria_type":   result.criteria_type,
            "warning":         warning,
        }

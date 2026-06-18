"""
어드민 서비스
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

class G2BSyncService:
    """
    G2B 개찰 결과를 투찰이력(my_bid_records)에 자동 반영.

    개찰 완료된 공고의 낙찰자 정보를 기반으로:
    - result: 'won' / 'lost' 자동 설정
    - actual_winner_rate, winner_name, winner_biz_no, rate_diff 채우기

    낙찰 판정 기준:
      abs(submitted_rate - winner_bid_rate) < 0.0003 → won
      그 외 → lost
    """

    def sync(self, db: Session) -> dict:
        pending = (
            db.query(MyBidRecord)
            .filter(
                MyBidRecord.result.is_(None),
                MyBidRecord.bid_id.isnot(None),
            )
            .all()
        )

        won = lost = skipped = 0
        for rec in pending:
            bid = db.query(Bid).filter(Bid.id == rec.bid_id).first()
            if not bid or bid.status != "closed":
                skipped += 1
                continue

            winner_row = (
                db.query(BidResult, Competitor)
                .join(Competitor, Competitor.id == BidResult.competitor_id)
                .filter(BidResult.bid_id == rec.bid_id, BidResult.is_winner == True)
                .first()
            )
            if not winner_row:
                skipped += 1
                continue

            winner_result, winner_comp = winner_row
            winner_rate     = float(winner_result.bid_rate)
            submitted_rate  = float(rec.submitted_rate)

            rec.actual_winner_rate = winner_rate
            rec.winner_name        = winner_comp.name
            rec.winner_biz_no      = winner_comp.biz_reg_no
            rec.rate_diff          = round(submitted_rate - winner_rate, 4)

            if abs(submitted_rate - winner_rate) < 0.0003:
                rec.result = "won"
                won += 1
            else:
                rec.result = "lost"
                lost += 1
                # 惜敗 알림: 낙찰자와 근소한 차이(1%p 이내) — 2위 가능성
                rate_diff_pct = abs(submitted_rate - winner_rate) * 100
                if rate_diff_pct < 1.0:
                    self._notify_seikihai(db, rec, winner_rate, rate_diff_pct)

        try:
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("G2B 연계 커밋 실패: %s", e)
            return {"won": 0, "lost": 0, "skipped": skipped, "error": str(e)}

        logger.info("G2B 자동 연계: won=%d, lost=%d, skipped=%d", won, lost, skipped)
        return {"won": won, "lost": lost, "skipped": skipped}

    def _notify_seikihai(self, db: Session, rec, winner_rate: float, diff_pct: float) -> None:
        try:
            title = f"[惜敗 알림] {rec.title[:40]}"
            body = (
                f"낙찰자와 {diff_pct:.2f}%p 차이로 아깝게 패찰했습니다. "
                f"낙찰율: {winner_rate*100:.3f}%, 귀사 투찰율: {float(rec.submitted_rate)*100:.3f}%"
            )
            link = f"/my-bids"
            users = db.query(User).filter(User.is_active == True).all()
            for u in users:
                n = Notification(user_id=u.id, ntype="seikihai", title=title, body=body, link=link)
                db.add(n)
        except Exception as exc:
            logger.warning("惜敗 알림 생성 실패: %s", exc)

class InpoNoticesSyncService:
    """
    inpo21c_bid_notices → bids 자동 동기화.

    G2B BidPublicInfoService02가 죽어있는 동안 info21c 입찰공고 사전정보를
    bids 테이블로 자동 전환하여 공고 파이프라인을 유지한다.
    매일 09:00 KST inpo21c 입찰공고 수집 직후 호출됨.
    """

    def sync(self, db: Session) -> dict:
        rows = db.execute(text("""
            SELECT n.inpo21c_bid_id, n.announcement_no, n.agency_name,
                   n.base_amount, n.open_datetime, n.min_bid_rate,
                   n.yega_method, n.yega_draw_count, n.yega_total_count,
                   n.region, n.industry
            FROM inpo21c_bid_notices n
            WHERE n.open_datetime > NOW() - INTERVAL '1 day'
              AND n.announcement_no IS NOT NULL
        """)).fetchall()

        created = skipped = 0
        for r in rows:
            # suffix 제거: "R26BK01531315-000" → "R26BK01531315"
            ann_no = re.sub(r'-\d+$', '', (r.announcement_no or '').strip())
            if not ann_no:
                skipped += 1
                continue

            existing = db.execute(
                text("SELECT id FROM bids WHERE announcement_no = :a"),
                {"a": ann_no}
            ).fetchone()
            if existing:
                skipped += 1
                continue

            try:
                agency_row = db.execute(
                    text("SELECT id FROM agencies WHERE name = :n"),
                    {"n": r.agency_name or ''}
                ).fetchone()
                if not agency_row:
                    db.execute(
                        text("INSERT INTO agencies (name) VALUES (:n) ON CONFLICT (name) DO NOTHING"),
                        {"n": r.agency_name or '미상'}
                    )
                    db.flush()
                    agency_row = db.execute(
                        text("SELECT id FROM agencies WHERE name = :n"),
                        {"n": r.agency_name or '미상'}
                    ).fetchone()

                yega_info = ""
                if r.yega_draw_count and r.yega_total_count:
                    yega_info = f"복수예가:{r.yega_draw_count}/{r.yega_total_count}"
                elif r.yega_method:
                    yega_info = r.yega_method[:100]

                db.execute(text("""
                    INSERT INTO bids
                        (announcement_no, title, agency_id, base_amount,
                         bid_open_date, min_bid_rate, status, source, bid_method)
                    VALUES
                        (:ann, :title, :agency_id, :base_amount,
                         :open_dt, :min_rate, 'open', 'inpo21c', :bid_method)
                    ON CONFLICT (announcement_no) DO NOTHING
                """), {
                    "ann":        ann_no,
                    "title":      f"[inpo21c] {r.agency_name or ''} ({ann_no})",
                    "agency_id":  agency_row[0],
                    "base_amount": r.base_amount or 0,
                    "open_dt":    r.open_datetime,
                    "min_rate":   r.min_bid_rate,
                    "bid_method": yega_info or None,
                })
                db.commit()
                created += 1
            except Exception as exc:
                db.rollback()
                logger.warning("inpo21c_bid_notices sync 실패 [%s]: %s", ann_no, exc)
                skipped += 1

        logger.info("inpo21c → bids 동기화: 신규=%d, 스킵=%d", created, skipped)
        return {"created": created, "skipped": skipped}


# DecisionService and JournalService extracted to dedicated modules.
# Re-exported here for backward compatibility with all existing router imports.
from ..decision_service import DecisionService  # noqa: E402, F401
from ..journal_service  import JournalService   # noqa: E402, F401

# ── kept below for reference during transition ──────────────────
class _DecisionService_REMOVED:
    """투찰 결정 전용 서비스 — TenderDecisionPage 백엔드."""

    def get_bid_context(self, db: Session, bid_id: int) -> dict:
        from ..ml.a_value import calc_floor_rate
        from ..ml.yega import load_inpo21c_yega_stats
        from ..ml.competitor_predict import predict_bid_zone

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
        }

    def simulate_bid(self, db: Session, bid_id: int, req) -> dict:
        from itertools import combinations as _comb
        import numpy as _np
        from ..ml.a_value import calc_floor_rate
        from ..ml.yega import load_inpo21c_yega_stats, calc_yega_frequency
        from ..ml.rank_model import get_inpo_raw_rates
        from ..ml.simulation import monte_carlo_win_prob_empirical, monte_carlo_win_prob

        b = db.query(Bid).filter(Bid.id == bid_id).first()
        if not b:
            return {}

        industry_name = b.industry.name if b.industry else ""
        agency_id = b.agency_id or 0
        industry_id = b.industry_id or 0
        base_amount = b.base_amount
        # base_amount=0인 공고는 시뮬레이션 불가 (수집 미완료)
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

        # 실측 모드: 15개 모두 양수여야 함
        if yega_values and len(yega_values) == 15 and all(v > 0 for v in yega_values):
            mode = "real"
            srate_dist = simulate_yejung_from_real(yega_values, base_amount)
            candidates = [
                {"idx": i + 1, "amount": int(yega_values[i]), "rate": round(yega_values[i] / base_amount, 4)}
                for i in range(15)
            ]
            # C(15,4)=1365 전수 열거
            vals = _np.array(yega_values, dtype=_np.float64)
            combos = [(list(c), float(vals[list(c)].mean())) for c in _comb(range(15), 4)]
            # 예정가격에 가까운 순 상위 20개
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
        # 경쟁사 수 직접 지정 우선
        if req.expected_n and 1 <= req.expected_n <= 200:
            expected_n = req.expected_n
        # 경쟁사 투찰률: 수동 입력 우선, 없으면 DB 조회
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
                from ..ml.rank_model import get_journal_winner_rates
                _journal_rates = get_journal_winner_rates(db, agency_id)
                if _journal_rates is not None and len(_journal_rates) >= 5:
                    import numpy as _np2
                    _base = _np2.array(inpo_rates) if not isinstance(inpo_rates, _np2.ndarray) else inpo_rates
                    # journal 낙찰자율 30% 혼합 (실전 데이터 우선)
                    n_journal = min(len(_journal_rates), int(len(_base) * 0.3))
                    inpo_rates = _np2.concatenate([_base, _journal_rates[:n_journal]])
            except Exception:
                pass

        all_zones, top_zones = scan_zones_from_dist(
            srate_dist, floor_rate, base_amount,
            inpo_rates, expected_n, n_sim=min(n_sim, 20_000),
        )

        eff_floor = floor_rate * float(_np.median(srate_dist))
        rate_agg  = round(eff_floor + 0.0003, 4)
        rate_bal  = round(max(eff_floor + 0.0015, rate_agg + 0.0005), 4)
        rate_con  = round(max(eff_floor + 0.003,  rate_bal + 0.0005), 4)
        rng2 = _np.random.default_rng(42)

        def _wp(r):
            if inpo_rates is not None and len(inpo_rates) >= 5 and expected_n > 0:
                return monte_carlo_win_prob_empirical(r, floor_rate, srate_dist, inpo_rates, expected_n, n_sim, rng2)
            return monte_carlo_win_prob(r, floor_rate, srate_dist, [], [], n_sim, rng2)

        strategies = {
            "aggressive":   {**_wp(rate_agg), "rate": rate_agg, "amount": int(round(rate_agg * base_amount)), "label": "공격형"},
            "balanced":     {**_wp(rate_bal), "rate": rate_bal, "amount": int(round(rate_bal * base_amount)), "label": "균형형"},
            "conservative": {**_wp(rate_con), "rate": rate_con, "amount": int(round(rate_con * base_amount)), "label": "안정형"},
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

        # prediction_logs_v2에 이번 추천 저장 (bid_id 반드시 기록)
        pred_log_id = None
        try:
            from ..models import PredictionLogV2
            from ..ml.engine import get_model_meta
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


# ─────────────────────────────────────────────────────────────
# JournalService extracted → app/journal_service.py (re-exported above)
# ─────────────────────────────────────────────────────────────

class _JournalService_REMOVED:
    """
    투찰 의사결정 → 실제투찰 → 개찰결과 를 bid_journal에 기록.
    prediction_logs_v2와 연결해 모델 성능을 실측으로 검증한다.
    """

    def create(self, db: Session, user_id: int, req) -> "BidJournal":
        from ..models import BidJournal, Bid
        from ..schemas import JournalCreateRequest
        from datetime import datetime as _dt

        b = db.query(Bid).filter(Bid.id == req.bid_id).first()
        ann_no = b.announcement_no if b else None

        rate_delta = None
        if req.submitted_rate and req.recommended_rate:
            rate_delta = round(float(req.submitted_rate) - float(req.recommended_rate), 6)

        submitted_amount = req.submitted_amount
        if not submitted_amount and req.submitted_rate and b and b.base_amount:
            submitted_amount = int(round(float(req.submitted_rate) * b.base_amount))

        obj = BidJournal(
            bid_id=req.bid_id,
            user_id=user_id,
            announcement_no=ann_no,
            predicted_at=_dt.now() if req.pred_log_id else None,
            pred_log_id=req.pred_log_id,
            recommended_rate=req.recommended_rate,
            recommended_amount=req.recommended_amount,
            pred_win_prob=req.pred_win_prob,
            pred_srate_center=req.pred_srate_center,
            strategy_chosen=req.strategy_chosen,
            submitted_at=_dt.now(),
            submitted_rate=req.submitted_rate,
            submitted_amount=submitted_amount,
            floor_rate=req.floor_rate,
            rate_delta=rate_delta,
            note=req.note,
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def record_result(self, db: Session, journal_id: int, user_id: int, req) -> "BidJournal":
        from ..models import BidJournal
        from datetime import datetime as _dt

        VALID_RESULTS = {"낙찰", "패찰", "무효", "취소"}
        if req.result not in VALID_RESULTS:
            from fastapi import HTTPException
            raise HTTPException(400, f"result는 {VALID_RESULTS} 중 하나여야 합니다.")

        obj = db.query(BidJournal).filter(
            BidJournal.id == journal_id,
            BidJournal.user_id == user_id,
        ).first()
        if not obj:
            from fastapi import HTTPException
            raise HTTPException(404, "저널 레코드를 찾을 수 없습니다.")

        obj.result = req.result
        obj.opened_at = _dt.now()
        if req.actual_srate is not None:
            obj.actual_srate = req.actual_srate
        if req.our_rank is not None:
            obj.our_rank = req.our_rank
        if req.total_bidders is not None:
            obj.total_bidders = req.total_bidders
        if req.winner_rate is not None:
            obj.winner_rate = req.winner_rate
        if req.winner_amount is not None:
            obj.winner_amount = req.winner_amount
        if req.winner_biz_no is not None:
            obj.winner_biz_no = req.winner_biz_no
        if req.winner_name is not None:
            obj.winner_name = req.winner_name
        if req.note is not None:
            obj.note = req.note

        # 파생 필드 계산
        if obj.winner_rate and obj.submitted_rate:
            obj.rate_gap = round(float(obj.winner_rate) - float(obj.submitted_rate), 6)
        if obj.actual_srate and obj.pred_srate_center:
            obj.srate_error = round(float(obj.actual_srate) - float(obj.pred_srate_center), 6)

        db.commit()
        db.refresh(obj)
        return obj

    def list_journals(self, db: Session, user_id: int, result_filter: str = None,
                      page: int = 1, size: int = 20) -> dict:
        from ..models import BidJournal
        from ..schemas import JournalOut

        q = db.query(BidJournal).filter(BidJournal.user_id == user_id)
        if result_filter:
            if result_filter == "pending":
                q = q.filter(BidJournal.result == None)  # noqa: E711
            else:
                q = q.filter(BidJournal.result == result_filter)

        total = q.count()
        items = q.order_by(BidJournal.created_at.desc()).offset((page - 1) * size).limit(size).all()
        return {
            "total": total,
            "page": page,
            "size": size,
            "items": [JournalOut.model_validate(i).model_dump() for i in items],
        }

    def get_stats(self, db: Session, user_id: int) -> dict:
        """피드백 루프 현황 + 모델 성능 지표."""
        from sqlalchemy import text as _text

        rows = db.execute(_text("""
            SELECT
              COUNT(*)                                              AS total,
              COUNT(CASE WHEN result IS NOT NULL  THEN 1 END)      AS with_result,
              COUNT(CASE WHEN result = '낙찰'    THEN 1 END)      AS wins,
              COUNT(CASE WHEN result = '패찰'    THEN 1 END)      AS losses,
              COUNT(CASE WHEN result IS NULL
                          AND submitted_rate IS NOT NULL THEN 1 END) AS pending_result,
              ROUND(AVG(CASE WHEN result IS NOT NULL
                             THEN ABS(srate_error) END)::numeric, 4) AS avg_srate_mae,
              ROUND(AVG(CASE WHEN result = '패찰'
                             THEN rate_gap END)::numeric, 4)      AS avg_rate_gap_loss,
              ROUND(AVG(CASE WHEN result IS NOT NULL
                             THEN rate_delta END)::numeric, 4)    AS avg_rate_delta
            FROM bid_journal
            WHERE user_id = :uid
        """), {"uid": user_id}).fetchone()

        total      = rows[0] or 0
        with_result= rows[1] or 0
        wins       = rows[2] or 0
        losses     = rows[3] or 0
        pending    = rows[4] or 0
        mae        = float(rows[5]) if rows[5] else None
        avg_gap    = float(rows[6]) if rows[6] else None
        avg_delta  = float(rows[7]) if rows[7] else None

        win_rate = round(wins / with_result, 4) if with_result > 0 else None

        return {
            "total":            total,
            "with_result":      with_result,
            "pending_result":   pending,
            "wins":             wins,
            "losses":           losses,
            "win_rate":         win_rate,
            "avg_srate_mae":    mae,
            "avg_rate_gap_loss": avg_gap,   # 패찰 시 낙찰자와 우리 투찰률 차이
            "avg_rate_delta":   avg_delta,   # AI추천 vs 실제 투찰 차이
            "feedback_completeness": round(with_result / total, 4) if total > 0 else 0,
        }

class InpoParticipantService:
    """inpo21c_participants → 공고별 전체 참여자 목록 반환."""

    def get(self, db: Session, bid_id: int) -> list:
        bid = db.query(Bid).filter(Bid.id == bid_id).first()
        if not bid or not bid.announcement_no:
            return []
        rows = db.execute(text("""
            SELECT ip.rank, ip.company_name, ip.biz_reg_no,
                   ip.bid_rate, ip.base_ratio, ip.is_winner
            FROM inpo21c_participants ip
            JOIN inpo21c_bids ib USING (inpo21c_bid_id)
            WHERE ib.announcement_no LIKE :ano
            ORDER BY ip.rank
        """), {"ano": bid.announcement_no + "%"}).fetchall()
        return [
            {
                "rank":         r[0],
                "company_name": r[1],
                "biz_reg_no":   r[2],
                "bid_rate":     float(r[3]) if r[3] is not None else None,
                "base_ratio":   float(r[4]) if r[4] is not None else None,
                "is_winner":    bool(r[5]),
            }
            for r in rows
        ]


# ==================================================
# 惜敗 분석 서비스 — my_bid_records × inpo21c_participants
# ==================================================

class SekihaiService:
    """자사 투찰이력 × inpo21c 실측 순위 교차 분석."""

    def get_rank(self, db: Session, announcement_no: str) -> dict:
        """announcement_no 기준 inpo21c 참여자 목록에서 모든 순위 반환."""
        rows = db.execute(text("""
            SELECT ip.rank, ip.company_name, ip.bid_rate, ip.is_winner,
                   ib.base_amount, ib.estimated_amount
            FROM inpo21c_participants ip
            JOIN inpo21c_bids ib USING (inpo21c_bid_id)
            WHERE ib.announcement_no LIKE :ano
            ORDER BY ip.rank
        """), {"ano": announcement_no + "%"}).fetchall()
        if not rows:
            return {"found": False, "participants": []}
        winner = next((r for r in rows if r[3]), None)
        return {
            "found": True,
            "total_count": len(rows),
            "winner_rate": float(winner[2]) if winner and winner[2] else None,
            "base_amount": int(rows[0][4]) if rows[0][4] else None,
            "participants": [
                {
                    "rank":         r[0],
                    "company_name": r[1],
                    "bid_rate":     float(r[2]) if r[2] is not None else None,
                    "is_winner":    bool(r[3]),
                }
                for r in rows[:20]
            ],
        }

    def batch_ranks(self, db: Session, announcement_nos: list[str]) -> dict:
        """여러 announcement_no에 대한 순위 정보 일괄 반환."""
        result: dict = {}
        for ano in announcement_nos:
            if not ano:
                continue
            rows = db.execute(text("""
                SELECT ip.rank, ip.company_name, ip.bid_rate, ip.is_winner
                FROM inpo21c_participants ip
                JOIN inpo21c_bids ib USING (inpo21c_bid_id)
                WHERE ib.announcement_no LIKE :ano
                ORDER BY ip.rank
            """), {"ano": ano + "%"}).fetchall()
            if rows:
                winner = next((r for r in rows if r[3]), None)
                result[ano] = {
                    "found": True,
                    "total_count": len(rows),
                    "winner_rate": float(winner[2]) if winner and winner[2] else None,
                    "top5": [
                        {"rank": r[0], "company_name": r[1], "bid_rate": float(r[2]) if r[2] else None, "is_winner": bool(r[3])}
                        for r in rows[:5]
                    ],
                }
            else:
                result[ano] = {"found": False}
        return result


# ==================================================
# 경쟁 레이더 서비스 — 동반 입찰 경쟁사 분석
# ==================================================

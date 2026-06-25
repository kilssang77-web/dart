"""투찰 피드백 루프 서비스 — JournalService."""
import logging
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class JournalService:
    """
    투찰 의사결정 → 실제투찰 → 개찰결과 를 bid_journal에 기록.
    prediction_logs_v2와 연결해 모델 성능을 실측으로 검증한다.
    """

    def create(self, db: Session, user_id: int, req) -> "BidJournal":
        from .models import BidJournal, Bid
        from .schemas import JournalCreateRequest
        from datetime import datetime as _dt
        from sqlalchemy import text as _text

        b = db.query(Bid).filter(Bid.id == req.bid_id).first()
        ann_no = b.announcement_no if b else None

        rate_delta = None
        if req.submitted_rate and req.recommended_rate:
            rate_delta = round(float(req.submitted_rate) - float(req.recommended_rate), 6)

        submitted_amount = req.submitted_amount
        if not submitted_amount and req.submitted_rate and b and b.base_amount:
            submitted_amount = int(round(float(req.submitted_rate) * b.base_amount))

        # pred_srate_center 자동 보완: 미전달 시 prediction_logs_v2에서 lookup
        pred_srate_center = req.pred_srate_center
        pred_win_prob = req.pred_win_prob
        pred_log_id = req.pred_log_id

        if pred_srate_center is None and req.bid_id:
            try:
                # 1순위: prediction_logs_v2 lookup
                if pred_log_id:
                    row = db.execute(_text(
                        "SELECT srate_pred_center, win_prob_center FROM prediction_logs_v2 WHERE id = :lid"
                    ), {"lid": pred_log_id}).fetchone()
                else:
                    row = db.execute(_text(
                        "SELECT id, srate_pred_center, win_prob_center FROM prediction_logs_v2 "
                        "WHERE bid_id = :bid AND user_id = :uid ORDER BY created_at DESC LIMIT 1"
                    ), {"bid": req.bid_id, "uid": user_id}).fetchone()
                    if row:
                        pred_log_id = row[0]
                if row:
                    srate_col = row[1] if len(row) == 3 else row[0]
                    prob_col  = row[2] if len(row) == 3 else row[1]
                    if srate_col is not None:
                        pred_srate_center = float(srate_col)
                    if pred_win_prob is None and prob_col is not None:
                        pred_win_prob = float(prob_col)
            except Exception as e:
                logger.warning("prediction_logs_v2 lookup 실패: %s", e)

        # 2순위: prediction_logs_v2에도 없으면 ML 모델로 직접 예측
        if pred_srate_center is None and b and b.base_amount:
            try:
                from .ml.assessment import load_srate_stats, predict_srate
                features = load_srate_stats(
                    db,
                    agency_id=getattr(b, "agency_id", None),
                    industry_id=getattr(b, "industry_id", None),
                    region_id=getattr(b, "region_id", None),
                    base_amount=int(b.base_amount),
                )
                ep = predict_srate(features, int(b.base_amount))
                pred_srate_center = float(ep["srate_range"]["center"])
                logger.info("journal#new bid_id=%d pred_srate_center 자동 계산: %.4f", req.bid_id, pred_srate_center)
            except Exception as e:
                logger.warning("pred_srate_center ML 계산 실패: %s", e)

        obj = BidJournal(
            bid_id=req.bid_id,
            user_id=user_id,
            announcement_no=ann_no,
            predicted_at=_dt.now() if pred_log_id else None,
            pred_log_id=pred_log_id,
            recommended_rate=req.recommended_rate,
            recommended_amount=req.recommended_amount,
            pred_win_prob=pred_win_prob,
            pred_srate_center=pred_srate_center,
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
        from .models import BidJournal
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

        # pred_srate_center 미설정 시 ML로 보완 (retroactive)
        if obj.pred_srate_center is None and obj.bid_id:
            try:
                from .models import Bid
                from .ml.assessment import load_srate_stats, predict_srate
                b2 = db.query(Bid).filter(Bid.id == obj.bid_id).first()
                if b2 and b2.base_amount:
                    features = load_srate_stats(
                        db,
                        agency_id=getattr(b2, "agency_id", None),
                        industry_id=getattr(b2, "industry_id", None),
                        region_id=getattr(b2, "region_id", None),
                        base_amount=int(b2.base_amount),
                    )
                    ep = predict_srate(features, int(b2.base_amount))
                    obj.pred_srate_center = float(ep["srate_range"]["center"])
                    logger.info("record_result: bid_id=%d pred_srate_center 소급 계산 %.4f", obj.bid_id, obj.pred_srate_center)
            except Exception as e:
                logger.warning("record_result pred_srate_center 소급 계산 실패: %s", e)

        # 파생 필드 계산
        if obj.winner_rate and obj.submitted_rate:
            obj.rate_gap = round(float(obj.winner_rate) - float(obj.submitted_rate), 6)
        if obj.actual_srate and obj.pred_srate_center:
            obj.srate_error = round(float(obj.actual_srate) - float(obj.pred_srate_center), 6)

        db.commit()

        # actual_bid_outcomes 동기화 (피드백 루프 핵심 테이블)
        _sync_actual_outcome(db, obj)

        db.refresh(obj)
        return obj

    def list_journals(self, db: Session, user_id: int, result_filter: str = None,
                      page: int = 1, size: int = 20) -> dict:
        from .models import BidJournal
        from .schemas import JournalOut

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
        """피드백 루프 현황 + 모델 성능 지표 + 월별 추이 + 전략별 성과."""
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

        total       = rows[0] or 0
        with_result = rows[1] or 0
        wins        = rows[2] or 0
        losses      = rows[3] or 0
        pending     = rows[4] or 0
        mae         = float(rows[5]) if rows[5] else None
        avg_gap     = float(rows[6]) if rows[6] else None
        avg_delta   = float(rows[7]) if rows[7] else None
        win_rate    = round(wins / with_result, 4) if with_result > 0 else None

        # 월별 추이
        monthly_rows = db.execute(_text("""
            SELECT
              TO_CHAR(created_at, 'YYYY-MM')                                          AS month,
              COUNT(*)                                                                 AS total,
              COUNT(CASE WHEN result = '낙찰' THEN 1 END)                            AS wins,
              COUNT(CASE WHEN result = '패찰' THEN 1 END)                            AS losses,
              ROUND(
                COUNT(CASE WHEN result = '낙찰' THEN 1 END)::numeric
                / NULLIF(COUNT(CASE WHEN result IS NOT NULL THEN 1 END), 0)
              , 4)                                                                     AS win_rate
            FROM bid_journal
            WHERE user_id = :uid
              AND result IS NOT NULL
            GROUP BY month
            ORDER BY month DESC
            LIMIT 12
        """), {"uid": user_id}).fetchall()
        monthly_trend = [
            {
                "month":    r[0],
                "total":    int(r[1]),
                "wins":     int(r[2]),
                "losses":   int(r[3]),
                "win_rate": float(r[4]) if r[4] is not None else None,
            }
            for r in reversed(monthly_rows)
        ]

        # 전략별 낙찰 성과
        strat_rows = db.execute(_text("""
            SELECT
              strategy_chosen,
              COUNT(*)                                                                AS total,
              COUNT(CASE WHEN result = '낙찰' THEN 1 END)                           AS wins,
              ROUND(
                COUNT(CASE WHEN result = '낙찰' THEN 1 END)::numeric
                / NULLIF(COUNT(CASE WHEN result IS NOT NULL THEN 1 END), 0)
              , 4)                                                                    AS win_rate
            FROM bid_journal
            WHERE user_id = :uid
              AND result IS NOT NULL
              AND strategy_chosen IS NOT NULL
            GROUP BY strategy_chosen
            ORDER BY wins DESC
        """), {"uid": user_id}).fetchall()
        strategy_stats = [
            {
                "strategy": r[0],
                "total":    int(r[1]),
                "wins":     int(r[2]),
                "win_rate": float(r[3]) if r[3] is not None else None,
            }
            for r in strat_rows
        ]

        return {
            "total":                total,
            "with_result":          with_result,
            "pending_result":       pending,
            "wins":                 wins,
            "losses":               losses,
            "win_rate":             win_rate,
            "avg_srate_mae":        mae,
            "avg_rate_gap_loss":    avg_gap,
            "avg_rate_delta":       avg_delta,
            "feedback_completeness": round(with_result / total, 4) if total > 0 else 0,
            "monthly_trend":        monthly_trend,
            "strategy_stats":       strategy_stats,
        }


# ── 결과 매핑 ──────────────────────────────────────────────────
_RESULT_MAP = {"낙찰": "WON", "패찰": "LOST", "무효": "DISQUALIFIED", "취소": "DISQUALIFIED"}


def _sync_actual_outcome(db: Session, journal: "BidJournal") -> None:
    """bid_journal 결과를 actual_bid_outcomes에 upsert (피드백 루프 연결)."""
    from .models import ActualBidOutcome

    outcome_result = _RESULT_MAP.get(journal.result)
    if not outcome_result or not journal.submitted_rate:
        return

    try:
        existing = db.query(ActualBidOutcome).filter(
            ActualBidOutcome.user_id == journal.user_id,
            ActualBidOutcome.bid_id == journal.bid_id,
        ).first()

        fields = dict(
            bid_id            = journal.bid_id,
            user_id           = journal.user_id,
            announcement_no   = journal.announcement_no,
            submitted_rate    = float(journal.submitted_rate),
            result            = outcome_result,
            actual_srate      = float(journal.actual_srate) if journal.actual_srate else None,
            winner_rate       = float(journal.winner_rate) if journal.winner_rate else None,
            winner_biz_no     = journal.winner_biz_no if hasattr(journal, "winner_biz_no") else None,
            our_rank          = journal.our_rank,
            total_bidders     = journal.total_bidders,
            predicted_win_prob= float(journal.pred_win_prob) if journal.pred_win_prob else None,
            predicted_srate   = float(journal.pred_srate_center) if journal.pred_srate_center else None,
            srate_error       = float(journal.srate_error) if journal.srate_error else None,
            collected_at      = journal.opened_at,
        )

        if existing:
            for k, v in fields.items():
                setattr(existing, k, v)
        else:
            db.add(ActualBidOutcome(**fields))

        db.commit()
        logger.info("actual_bid_outcomes 동기화: journal#%d → %s", journal.id, outcome_result)
    except Exception as exc:
        db.rollback()
        logger.error("actual_bid_outcomes 동기화 실패 journal#%d: %s", journal.id, exc)

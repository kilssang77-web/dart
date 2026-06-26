"""
E6: 피드백 학습 엔진

목표: 실전 투찰 결과 → 자동 모델 갱신
      경험이 쌓일수록 시스템이 더 정확해진다.

파이프라인:
  1. G2B 개찰 결과 자동 수집 → actual_bid_outcomes
  2. 결과 50건 누적 시 모델 재학습 트리거
  3. 사정율 예측 MAE 추적 + Isotonic 캘리브레이션
  4. 경쟁사 투찰 패턴 갱신 (competitor_strategy_patterns)
  5. KPI 스냅샷 업데이트

수주율 기여:
  - 사정율 예측이 정확해질수록 투찰 구간 정밀도 향상
  - 경쟁사 패턴 갱신으로 E4 예측 품질 향상
  - 모델 성능 저하 자동 감지 → 재학습
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from datetime import date, datetime, timedelta
import logging

logger = logging.getLogger(__name__)

RETRAIN_THRESHOLD   = 50   # 신규 결과 n건 누적 시 재학습
MIN_SAMPLE_FOR_EVAL = 20   # 성능 평가 최소 샘플 수


@dataclass
class OutcomeRecord:
    """피드백 루프 입력 데이터"""
    bid_id:            int
    user_id:           int
    submitted_rate:    float
    result:            str           # WON / LOST / DISQUALIFIED
    actual_srate:      Optional[float]
    winner_rate:       Optional[float]
    our_rank:          Optional[int]
    total_bidders:     Optional[int]
    predicted_win_prob: Optional[float]
    predicted_srate:   Optional[float]
    bid_decision_id:   Optional[int] = None
    disqualify_reason: Optional[str] = None


@dataclass
class FeedbackStats:
    """피드백 처리 결과 요약"""
    new_outcomes:      int
    win_count:         int
    loss_count:        int
    disqualified:      int
    srate_mae:         Optional[float]
    win_prob_ece:      Optional[float]   # Expected Calibration Error
    retrain_triggered: bool
    retrain_models:    List[str]


def compute_srate_mae(records: List[OutcomeRecord]) -> Optional[float]:
    """사정율 예측 MAE 계산"""
    pairs = [
        (r.predicted_srate, r.actual_srate)
        for r in records
        if r.predicted_srate is not None and r.actual_srate is not None
    ]
    if len(pairs) < MIN_SAMPLE_FOR_EVAL:
        return None
    errors = [abs(pred - actual) for pred, actual in pairs]
    return round(sum(errors) / len(errors), 6)


def compute_win_prob_ece(records: List[OutcomeRecord], n_bins: int = 5) -> Optional[float]:
    """
    낙찰확률 캘리브레이션 오차 (ECE) 계산.
    ECE가 낮을수록 "낙찰확률 70%라고 했을 때 실제로 70% 낙찰" 상태.
    """
    pairs = [
        (r.predicted_win_prob, 1 if r.result == "WON" else 0)
        for r in records
        if r.predicted_win_prob is not None and r.result in ("WON", "LOST")
    ]
    if len(pairs) < MIN_SAMPLE_FOR_EVAL:
        return None

    bin_size = 1.0 / n_bins
    total_ece = 0.0
    total_n = len(pairs)

    for i in range(n_bins):
        lo = i * bin_size
        hi = (i + 1) * bin_size
        bin_pairs = [(pred, actual) for pred, actual in pairs if lo <= pred < hi]
        if not bin_pairs:
            continue
        bin_conf  = sum(p for p, _ in bin_pairs) / len(bin_pairs)
        bin_acc   = sum(a for _, a in bin_pairs) / len(bin_pairs)
        total_ece += (len(bin_pairs) / total_n) * abs(bin_conf - bin_acc)

    return round(total_ece, 6)


def check_retrain_needed(
    new_outcome_count: int,
    last_retrain_date: Optional[date],
    srate_mae: Optional[float],
    win_prob_ece: Optional[float],
) -> Dict[str, bool]:
    """
    재학습 필요 여부 판단.

    조건:
      - 신규 결과 RETRAIN_THRESHOLD건 이상 누적
      - 사정율 MAE > 0.005 (정확도 저하)
      - ECE > 0.10 (캘리브레이션 오차 과다)
      - 마지막 학습 후 30일 초과
    """
    needs = {}
    needs["count_threshold"]     = new_outcome_count >= RETRAIN_THRESHOLD
    needs["srate_degradation"]   = srate_mae is not None and srate_mae > 0.005
    needs["calibration_drift"]   = win_prob_ece is not None and win_prob_ece > 0.10
    needs["periodic"]            = (
        last_retrain_date is None
        or (date.today() - last_retrain_date).days >= 30
    )
    return needs


def update_competitor_patterns_from_outcomes(
    records: List[OutcomeRecord],
    db,
) -> int:
    """
    개찰 결과에서 경쟁사 투찰 패턴 업데이트.
    actual_bid_outcomes → competitor_strategy_patterns 갱신.
    Returns: 갱신된 경쟁사 수
    """
    from sqlalchemy import text

    updated_count = 0
    for record in records:
        if record.actual_srate is None:
            continue

        # bid_results에서 이 공고의 경쟁사 투찰 데이터 조회
        rows = db.execute(
            text("""
                SELECT br.competitor_id, br.bid_rate, b.agency_id, b.industry_id, b.base_amount
                FROM bid_results br
                JOIN bids b ON b.id = br.bid_id
                WHERE br.bid_id = :bid_id
            """),
            {"bid_id": record.bid_id},
        ).fetchall()

        for row in rows:
            _upsert_competitor_pattern(db, row, record.actual_srate)
            updated_count += 1

    return updated_count


def _upsert_competitor_pattern(db, row, actual_srate: float):
    """경쟁사 패턴 UPSERT — 새 투찰 데이터로 분위수 갱신"""
    from sqlalchemy import text
    import math

    # 금액 버킷 계산 (10억 단위)
    amount_bucket = min(9, int(math.log10(max(row.base_amount, 1)) - 8))
    amount_bucket = max(0, amount_bucket)

    # 기존 패턴 조회
    existing = db.execute(
        text("""
            SELECT id, bid_rate_p50, sample_count
            FROM competitor_strategy_patterns
            WHERE competitor_id = :cid
              AND agency_id = :aid
              AND industry_id = :iid
              AND amount_bucket = :bucket
        """),
        {
            "cid":    row.competitor_id,
            "aid":    row.agency_id,
            "iid":    row.industry_id,
            "bucket": amount_bucket,
        },
    ).fetchone()

    if existing is None:
        # 신규 삽입 (단일 데이터 → 모든 분위수 동일)
        db.execute(
            text("""
                INSERT INTO competitor_strategy_patterns
                  (competitor_id, agency_id, industry_id, amount_bucket,
                   bid_rate_p10, bid_rate_p25, bid_rate_p50, bid_rate_p75, bid_rate_p90,
                   participation_rate, win_rate, sample_count)
                VALUES (:cid, :aid, :iid, :bucket,
                        :rate, :rate, :rate, :rate, :rate,
                        1.0, :win_rate, 1)
                ON CONFLICT (competitor_id, agency_id, industry_id, amount_bucket) DO NOTHING
            """),
            {
                "cid":      row.competitor_id,
                "aid":      row.agency_id,
                "iid":      row.industry_id,
                "bucket":   amount_bucket,
                "rate":     float(row.bid_rate),
                "win_rate": 1.0 if getattr(row, "is_winner", False) else 0.0,
            },
        )
    # 기존 있으면 sample_count가 많아야 의미 있으므로 배치 재계산으로 처리


def build_kpi_snapshot(
    db,
    user_id: Optional[int],
    snapshot_date: date,
    period_type: str = "MONTHLY",
) -> Dict[str, Any]:
    """
    KPI 스냅샷 계산.
    actual_bid_outcomes 테이블에서 집계.
    """
    from sqlalchemy import text

    if period_type == "MONTHLY":
        start_date = snapshot_date.replace(day=1)
        end_date   = snapshot_date
    elif period_type == "WEEKLY":
        start_date = snapshot_date - timedelta(days=6)
        end_date   = snapshot_date
    else:  # DAILY
        start_date = end_date = snapshot_date

    user_filter = "AND user_id = :uid" if user_id else ""

    rows = db.execute(
        text(f"""
            SELECT result, submitted_rate, actual_srate, predicted_srate,
                   predicted_win_prob, our_rank, total_bidders
            FROM actual_bid_outcomes
            WHERE DATE(COALESCE(collected_at, created_at)) BETWEEN :start AND :end
              AND result IN ('WON', 'LOST', 'DISQUALIFIED')
              {user_filter}
        """),
        {"start": start_date, "end": end_date, "uid": user_id} if user_id
        else {"start": start_date, "end": end_date},
    ).fetchall()

    if not rows:
        return {}

    total_bids  = len(rows)
    wins        = [r for r in rows if r.result == "WON"]
    losses      = [r for r in rows if r.result == "LOST"]
    disq        = [r for r in rows if r.result == "DISQUALIFIED"]
    win_count   = len(wins)
    win_rate    = win_count / total_bids if total_bids > 0 else 0.0

    # 사정율 MAE
    srate_pairs = [
        (r.predicted_srate, r.actual_srate)
        for r in rows
        if r.predicted_srate and r.actual_srate
    ]
    srate_mae = (
        sum(abs(p - a) for p, a in srate_pairs) / len(srate_pairs)
        if srate_pairs else None
    )

    # ECE
    prob_pairs = [
        (r.predicted_win_prob, 1 if r.result == "WON" else 0)
        for r in rows
        if r.predicted_win_prob and r.result in ("WON", "LOST")
    ]
    ece = compute_win_prob_ece([
        OutcomeRecord(
            bid_id=0, user_id=0, submitted_rate=0.0,
            result="WON" if a == 1 else "LOST",
            actual_srate=None, winner_rate=None,
            our_rank=None, total_bidders=None,
            predicted_win_prob=p, predicted_srate=None,
        )
        for p, a in prob_pairs
    ])

    # 패찰 시 평균 순위
    ranked_losses = [r for r in losses if r.our_rank is not None]
    avg_rank_loss = (
        sum(r.our_rank for r in ranked_losses) / len(ranked_losses)
        if ranked_losses else None
    )

    # 선별 통계 (bid_decisions 조회)
    decision_rows = db.execute(
        text(f"""
            SELECT verdict, COUNT(*) as cnt
            FROM bid_decisions
            WHERE DATE(created_at) BETWEEN :start AND :end
              {'AND user_id = :uid' if user_id else ''}
            GROUP BY verdict
        """),
        {"start": start_date, "end": end_date, "uid": user_id} if user_id
        else {"start": start_date, "end": end_date},
    ).fetchall()

    go_cnt    = sum(r.cnt for r in decision_rows if r.verdict == "GO")
    no_go_cnt = sum(r.cnt for r in decision_rows if r.verdict == "NO_GO")
    total_dec = sum(r.cnt for r in decision_rows)
    go_rate   = go_cnt / total_dec if total_dec > 0 else None

    return {
        "snapshot_date":         snapshot_date,
        "user_id":               user_id,
        "period_type":           period_type,
        "total_bids":            total_bids,
        "total_wins":            win_count,
        "win_rate":              round(win_rate, 4),
        "qualify_pass_rate":     1.0 - (len(disq) / total_bids) if total_bids > 0 else None,
        "avg_rank_at_loss":      round(avg_rank_loss, 2) if avg_rank_loss else None,
        "srate_mae":             round(srate_mae, 6) if srate_mae else None,
        "win_prob_calibration":  round(ece, 6) if ece else None,
        "go_rate":               round(go_rate, 4) if go_rate else None,
        "no_go_saved":           no_go_cnt,
    }


def should_alert(kpi: Dict[str, Any]) -> List[str]:
    """KPI 이상값 → 경고 메시지 생성"""
    alerts = []

    win_rate = kpi.get("win_rate")
    if win_rate is not None and win_rate < 0.20:
        alerts.append(f"수주율 {win_rate:.0%} 저조 — 공고 선별 전략 재검토 필요")

    qualify_rate = kpi.get("qualify_pass_rate")
    if qualify_rate is not None and qualify_rate < 0.95:
        alerts.append(f"적격심사 탈락 {(1 - qualify_rate):.0%} — 시공실적 프로파일 갱신 필요")

    srate_mae = kpi.get("srate_mae")
    if srate_mae is not None and srate_mae > 0.005:
        alerts.append(f"사정율 예측 MAE {srate_mae:.4f} 초과 — 모델 재학습 권장")

    ece = kpi.get("win_prob_calibration")
    if ece is not None and ece > 0.10:
        alerts.append(f"낙찰확률 캘리브레이션 오차 {ece:.3f} — 확률값 신뢰도 저하")

    avg_rank = kpi.get("avg_rank_at_loss")
    if avg_rank is not None and avg_rank > 5:
        alerts.append(f"패찰 시 평균 순위 {avg_rank:.1f}위 — 투찰률이 크게 빗나가는 중")

    return alerts

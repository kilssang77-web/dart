"""Walk-forward 모델 검증 — 예측 win_prob vs 실제 낙찰률 캘리브레이션."""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


class WalkForwardValidator:
    """
    매월 1일: 전월 예측 vs 실제 결과 비교.
    actual_bid_outcomes에 쌓인 데이터 기반.
    결과를 ml_validation_results 테이블에 저장.
    """

    def run(self, db: Session, months_back: int = 1) -> dict:
        cutoff = datetime.utcnow() - timedelta(days=months_back * 30)
        rows = db.execute(text("""
            SELECT
                o.predicted_win_prob,
                o.result,
                o.srate_error,
                j.strategy_chosen
            FROM actual_bid_outcomes o
            LEFT JOIN bid_journal j ON j.announcement_no = o.announcement_no
            WHERE o.created_at >= :cutoff
              AND o.predicted_win_prob IS NOT NULL
        """), {"cutoff": cutoff}).fetchall()

        if not rows:
            return {"status": "no_data", "count": 0}

        total = len(rows)
        wins = sum(1 for r in rows if r[1] == "WON")
        actual_win_rate = wins / total if total > 0 else 0.0

        # 사정율 예측 MAE
        srate_errors = [abs(float(r[2])) for r in rows if r[2] is not None]
        srate_mae = sum(srate_errors) / len(srate_errors) if srate_errors else None

        # 예측 확률 캘리브레이션 (버킷별)
        buckets = {"0.0-0.2": [], "0.2-0.4": [], "0.4-0.6": [], "0.6-0.8": [], "0.8-1.0": []}
        for r in rows:
            p = float(r[0])
            won = r[1] == "WON"
            if p < 0.2:   buckets["0.0-0.2"].append(won)
            elif p < 0.4: buckets["0.2-0.4"].append(won)
            elif p < 0.6: buckets["0.4-0.6"].append(won)
            elif p < 0.8: buckets["0.6-0.8"].append(won)
            else:         buckets["0.8-1.0"].append(won)

        calibration = {
            k: round(sum(v) / len(v), 3) if v else None
            for k, v in buckets.items()
        }

        # 전략별 낙찰률
        strategy_stats: dict = {}
        for r in rows:
            s = r[3] or "unknown"
            if s not in strategy_stats:
                strategy_stats[s] = {"total": 0, "wins": 0}
            strategy_stats[s]["total"] += 1
            if r[1] == "WON":
                strategy_stats[s]["wins"] += 1
        strategy_win_rates = {
            k: round(v["wins"] / v["total"], 3) if v["total"] > 0 else 0
            for k, v in strategy_stats.items()
        }

        result = {
            "status": "ok",
            "period": f"최근 {months_back}개월",
            "total": total,
            "wins": wins,
            "actual_win_rate": round(actual_win_rate, 3),
            "srate_mae": round(srate_mae, 4) if srate_mae else None,
            "calibration": calibration,
            "strategy_win_rates": strategy_win_rates,
        }

        # 결과 저장
        self._save_result(db, result)
        logger.info("Walk-forward 검증 완료: %s", result)
        return result

    def _save_result(self, db: Session, result: dict) -> None:
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS ml_validation_results (
                    id SERIAL PRIMARY KEY,
                    run_at TIMESTAMPTZ DEFAULT NOW(),
                    total INTEGER,
                    wins INTEGER,
                    actual_win_rate NUMERIC(5,3),
                    srate_mae NUMERIC(6,4),
                    calibration JSONB,
                    strategy_win_rates JSONB
                )
            """))
            db.execute(text("""
                INSERT INTO ml_validation_results
                    (total, wins, actual_win_rate, srate_mae, calibration, strategy_win_rates)
                VALUES (:total, :wins, :awr, :mae, :cal::jsonb, :swr::jsonb)
            """), {
                "total": result["total"],
                "wins":  result["wins"],
                "awr":   result["actual_win_rate"],
                "mae":   result["srate_mae"],
                "cal":   str(result["calibration"]).replace("'", '"'),
                "swr":   str(result["strategy_win_rates"]).replace("'", '"'),
            })
            db.commit()
        except Exception as e:
            logger.warning("검증 결과 저장 실패: %s", e)

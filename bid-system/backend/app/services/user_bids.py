"""
투찰이력 서비스
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

class MyBidFeedbackService:
    """MyBidRecord → ActualBidOutcome 동기화 + 임계치 도달 시 자동 재학습."""

    import threading as _threading
    RETRAIN_LOCK = False  # 동시 재학습 방지 (프로세스 내 단순 플래그)
    _RETRAIN_EVENT = _threading.Event()  # 재진입 방지용 atomic 플래그

    def __init__(self, db: Session):
        self.db = db

    def sync_outcome(self, rec: "MyBidRecord") -> bool:
        """낙찰/패찰 결과를 ActualBidOutcome에 반영. pending이면 skip."""
        if rec.result not in ("won", "lost"):
            return False

        result_val = "WON" if rec.result == "won" else "LOST"

        # 기존 레코드 조회 — bid_id 우선, 없으면 announcement_no
        existing = None
        if rec.bid_id:
            existing = (
                self.db.query(ActualBidOutcome)
                .filter(ActualBidOutcome.user_id == rec.user_id,
                        ActualBidOutcome.bid_id == rec.bid_id)
                .first()
            )
        if existing is None and rec.announcement_no:
            existing = (
                self.db.query(ActualBidOutcome)
                .filter(ActualBidOutcome.user_id == rec.user_id,
                        ActualBidOutcome.announcement_no == rec.announcement_no)
                .first()
            )

        if existing:
            existing.result       = result_val
            existing.submitted_rate = rec.submitted_rate
            existing.winner_rate  = rec.actual_winner_rate
            existing.collected_at = datetime.utcnow()
        else:
            if rec.bid_id is None and not rec.announcement_no:
                return False  # 연결 키 없음 — 동기화 불가
            self.db.add(ActualBidOutcome(
                bid_id          = rec.bid_id,
                user_id         = rec.user_id,
                announcement_no = rec.announcement_no,
                submitted_rate  = rec.submitted_rate,
                result          = result_val,
                winner_rate     = rec.actual_winner_rate,
                collected_at    = datetime.utcnow(),
            ))

        self.db.flush()
        self._check_retrain_trigger()
        return True

    def _check_retrain_trigger(self):
        from ..ml.feedback import RETRAIN_THRESHOLD
        last_log = (
            self.db.query(ModelPerformanceLog)
            .order_by(ModelPerformanceLog.created_at.desc())
            .first()
        )
        last_date = last_log.eval_date if last_log else None
        cutoff = datetime.combine(last_date, datetime.min.time()) if last_date else datetime.min
        new_count = (
            self.db.query(func.count(ActualBidOutcome.id))
            .filter(
                ActualBidOutcome.created_at >= cutoff,
                ActualBidOutcome.result.in_(["WON", "LOST"]),
            )
            .scalar() or 0
        )
        if new_count >= RETRAIN_THRESHOLD and not MyBidFeedbackService.RETRAIN_LOCK:
            logger.info("자동 재학습 트리거: 신규 결과 %d건 누적", new_count)
            import threading
            threading.Thread(target=self._run_retrain, daemon=True).start()

    @classmethod
    def _run_retrain(cls):
        """백그라운드 재학습 — Engine A(사정율) + Engine B(낙찰률)."""
        # atomic test-and-set: 이미 실행 중이면 즉시 반환
        if cls._RETRAIN_EVENT.is_set():
            logger.info("ML 재학습 이미 실행 중 — 중복 호출 무시")
            return
        cls._RETRAIN_EVENT.set()
        cls.RETRAIN_LOCK = True
        from ..database import SessionLocal
        from ..ml.engine import train_models, train_models_temporal, build_features, FEATURE_COLS, get_engine
        from ..ml.assessment import compute_and_store_stats, train_srate_model
        import pandas as pd
        from sqlalchemy import text as sa_text

        db = SessionLocal()
        try:
            # Engine A
            compute_and_store_stats(db)
            train_srate_model(db)

            # Engine B — 낙찰률 회귀 모델
            # 최근 36개월 + 최대 5,000건으로 제한 (메모리 보호)
            from datetime import timedelta
            train_cutoff = datetime.now() - timedelta(days=36 * 30)
            rows = db.execute(sa_text("""
                SELECT b.id, b.agency_id, b.industry_id,
                       COALESCE(b.region_id, 0) AS region_id,
                       b.base_amount, b.bid_open_date,
                       COALESCE(b.region_restriction, false),
                       b.construction_period, r.bid_rate
                FROM bids b
                JOIN bid_results r ON r.bid_id = b.id AND r.is_winner = true
                WHERE b.base_amount > 0
                  AND r.bid_rate BETWEEN 0.80 AND 1.00
                  AND b.bid_open_date >= :cutoff
                ORDER BY b.bid_open_date
                LIMIT 5000
            """), {"cutoff": train_cutoff}).fetchall()

            cutoff = datetime.now() - timedelta(days=24 * 30)
            hist_rows = db.execute(sa_text("""
                SELECT b.id, b.agency_id, b.industry_id,
                       COALESCE(b.region_id, 0), b.base_amount, b.bid_open_date,
                       r.bid_rate,
                       (SELECT COUNT(*) FROM bid_results r2 WHERE r2.bid_id = b.id)
                FROM bids b
                LEFT JOIN bid_results r ON r.bid_id = b.id AND r.is_winner = true
                WHERE b.bid_open_date >= :cutoff AND b.base_amount > 0
                LIMIT 10000
            """), {"cutoff": cutoff}).fetchall()

            hist_df = pd.DataFrame(hist_rows, columns=[
                "id", "agency_id", "industry_id", "region_id",
                "base_amount", "bid_open_date", "winner_rate", "competitor_count",
            ])
            for col in ["winner_rate", "base_amount", "competitor_count"]:
                hist_df[col] = pd.to_numeric(hist_df[col], errors="coerce")
            # 날짜 정렬 후 numpy 배열로 변환 — O(n²) 루프에서 copy() 제거를 위해
            hist_df["bid_open_date"] = pd.to_datetime(hist_df["bid_open_date"], errors="coerce")
            hist_df = hist_df.sort_values("bid_open_date").reset_index(drop=True)
            hist_dates = hist_df["bid_open_date"].values  # numpy array for fast bisect

            from ..ml.yega import load_inpo21c_yega_stats as _load_yega
            _yega_cache: dict = {}

            records = []
            for row in rows:
                bid_id, agency_id, industry_id, region_id, base_amount, bid_open_date, region_restriction, construction_period, winner_rate = row
                if winner_rate is None:
                    continue
                # O(log n) 이진 탐색으로 슬라이스 인덱스 산출 — copy() 없음
                if bid_open_date is not None:
                    import numpy as _np
                    _ts = pd.Timestamp(bid_open_date).to_datetime64()
                    _idx = int(_np.searchsorted(hist_dates, _ts, side="left"))
                    hist_before = hist_df.iloc[:_idx]
                else:
                    hist_before = hist_df
                _aid = int(agency_id) if agency_id else 0
                if _aid not in _yega_cache:
                    try:
                        _yega_cache[_aid] = _load_yega(db, _aid)
                    except Exception:
                        _yega_cache[_aid] = {}
                _yega_ml = _compute_yega_ml_features(_yega_cache[_aid].get("pos_weights"))
                try:
                    feats = build_features(
                        agency_id=_aid,
                        industry_id=int(industry_id) if industry_id else 0,
                        region_id=int(region_id),
                        base_amount=int(base_amount),
                        construction_period=int(construction_period) if construction_period else None,
                        region_restriction=bool(region_restriction),
                        bid_open_date=bid_open_date,
                        historical_df=hist_before,
                        yega_features=_yega_ml,
                    )
                    feats["target_rate"]   = float(winner_rate)
                    feats["is_winner"]     = True
                    feats["bid_open_date"] = bid_open_date
                    records.append(feats)
                except Exception:
                    pass

            # clf_df: inpo21c_participants 낙찰자+비낙찰자 (win_model 학습용)
            clf_df = None
            try:
                clf_rows = db.execute(sa_text("""
                    SELECT b.agency_id, b.industry_id,
                           COALESCE(b.region_id, 0) AS region_id,
                           b.base_amount, b.bid_open_date,
                           COALESCE(b.region_restriction, false),
                           b.construction_period,
                           p.bid_rate, p.is_winner
                    FROM inpo21c_participants p
                    JOIN inpo21c_bids ib ON ib.inpo21c_bid_id = p.inpo21c_bid_id
                    JOIN bids b ON b.announcement_no = ib.announcement_no
                    WHERE b.agency_id IS NOT NULL AND b.industry_id IS NOT NULL
                      AND b.base_amount > 0
                      AND p.bid_rate BETWEEN 0.80 AND 1.00
                    ORDER BY b.bid_open_date DESC
                    LIMIT 3000
                """)).fetchall()
                clf_records = []
                import numpy as _np2
                for crow in clf_rows:
                    c_agency, c_ind, c_reg, c_amt, c_dt, c_rr, c_cp, c_rate, c_win = crow
                    if c_rate is None:
                        continue
                    if c_dt is not None:
                        _ts2 = pd.Timestamp(c_dt).to_datetime64()
                        _idx2 = int(_np2.searchsorted(hist_dates, _ts2, side="left"))
                        hist_c = hist_df.iloc[:_idx2]
                    else:
                        hist_c = hist_df
                    try:
                        cf = build_features(
                            agency_id=int(c_agency) if c_agency else 0,
                            industry_id=int(c_ind) if c_ind else 0,
                            region_id=int(c_reg),
                            base_amount=int(c_amt),
                            construction_period=int(c_cp) if c_cp else None,
                            region_restriction=bool(c_rr),
                            bid_open_date=c_dt,
                            historical_df=hist_c,
                        )
                        cf["target_rate"] = float(c_rate)
                        cf["our_bid_rate"] = float(c_rate)
                        cf["is_winner"] = bool(c_win)
                        cf["bid_open_date"] = c_dt
                        clf_records.append(cf)
                    except Exception:
                        pass
                if len(clf_records) >= 20:
                    clf_df = pd.DataFrame(clf_records)
                    for col in FEATURE_COLS:
                        if col not in clf_df.columns:
                            clf_df[col] = None
                    logger.info("clf_df 빌드 완료: %d건 (pos=%d neg=%d)",
                                len(clf_records),
                                sum(1 for r in clf_records if r.get("is_winner")),
                                sum(1 for r in clf_records if not r.get("is_winner")))
            except Exception as _clf_e:
                logger.warning("clf_df 빌드 실패: %s", _clf_e)

            if len(records) >= 20:
                train_df = pd.DataFrame(records)
                for col in FEATURE_COLS:
                    if col not in train_df.columns:
                        train_df[col] = None
                result = train_models_temporal(train_df, clf_df=clf_df, val_weeks=4, date_col="bid_open_date")
                if result:
                    get_engine().reload()
                    tv = result.get("temporal_val_metrics") or {}
                    db.add(ModelPerformanceLog(
                        model_name    = "auto_retrain",
                        model_version = result.get("version", ""),
                        eval_date     = datetime.utcnow().date(),
                        sample_count  = tv.get("train_size") or result.get("train_size", 0),
                        mae           = tv.get("mae"),
                        rmse          = tv.get("rmse"),
                    ))
                    db.commit()
                    logger.info("자동 재학습 완료: %s", result)
            else:
                logger.warning("자동 재학습 스킵 — 피처 빌드 성공 %d건 (최소 20건 필요)", len(records))

            # win_prob_model 재학습 (Task #5)
            try:
                from ..ml.win_prob_model import train as _wp_train
                wp_result = _wp_train(db)
                logger.info("win_prob_model 재학습 완료: %s", wp_result)
            except Exception as _wp_e:
                logger.warning("win_prob_model 재학습 실패: %s", _wp_e)

        except Exception as exc:
            logger.error("자동 재학습 실패: %s", exc)
        finally:
            cls.RETRAIN_LOCK = False
            cls._RETRAIN_EVENT.clear()
            db.close()

class MyBidImportService:
    """투찰이력 엑셀 파일 → MyBidRecord 일괄 등록."""

    RESULT_MAP = {
        "낙찰": "won", "수주": "won", "won": "won",
        "유찰": "lost", "패찰": "lost", "미낙찰": "lost", "lost": "lost",
    }

    def __init__(self, db: Session):
        self.db = db

    # ── 숫자 파싱 헬퍼 ──────────────────────────────────────
    @staticmethod
    def _to_float(val) -> float | None:
        if val is None or str(val).strip() in ("", "-"):
            return None
        try:
            return float(str(val).replace("%", "").replace(",", "").strip())
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _to_int(val) -> int:
        if val is None:
            return 0
        try:
            return int(float(str(val).replace(",", "").strip()))
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _to_date(val):
        """문자열 또는 datetime/date → date 객체."""
        if val is None:
            return None
        from datetime import date, datetime
        if isinstance(val, date):
            return val if isinstance(val, date) and not isinstance(val, datetime) else val.date()
        s = str(val).strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        return None

    # ── 헤더 정규화 (다양한 표기 허용) ─────────────────────
    _HEADER_ALIASES: dict[str, str] = {
        # 공고번호
        "공고번호": "공고번호", "announcement_no": "공고번호",
        # 공고제목
        "공고제목": "공고제목", "공고명": "공고제목", "제목": "공고제목", "title": "공고제목",
        # 발주처
        "발주처": "발주처", "발주기관": "발주처", "agency": "발주처", "agency_name": "발주처",
        # 입찰일
        "입찰일": "입찰일", "투찰일": "입찰일", "bid_date": "입찰일",
        # 기초금액
        "기초금액": "기초금액", "예정가격": "기초금액", "base_amount": "기초금액",
        # 제출투찰률
        "제출투찰률": "제출투찰률", "투찰률": "제출투찰률", "투찰율": "제출투찰률",
        "submitted_rate": "제출투찰률",
        # 추천투찰률
        "추천투찰률": "추천투찰률", "ai추천률": "추천투찰률", "ai추천율": "추천투찰률",
        "recommendation_rate": "추천투찰률",
        # 결과
        "결과": "결과", "result": "결과", "낙패": "결과",
        # 실제낙찰률
        "실제낙찰률": "실제낙찰률", "낙찰률": "실제낙찰률", "actual_winner_rate": "실제낙찰률",
        # 비고
        "비고": "비고", "메모": "비고", "note": "비고",
    }

    def _normalize_headers(self, raw: list[str]) -> list[str]:
        return [self._HEADER_ALIASES.get(h.strip(), h.strip()) for h in raw]

    # ── 메인 임포트 ─────────────────────────────────────────
    def import_excel(self, file_bytes: bytes, user_id: int) -> dict:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        ws = wb.active

        headers: list[str] = []
        imported = skipped = 0
        errors: list[str] = []
        details: list[str] = []

        for row_idx, row in enumerate(ws.iter_rows(values_only=True), 1):
            if not headers:
                headers = self._normalize_headers([str(c or "") for c in row])
                continue

            if all(v is None or str(v).strip() == "" for v in row):
                continue

            rd = dict(zip(headers, row))
            title = str(rd.get("공고제목") or "").strip()
            if not title:
                skipped += 1
                continue

            announcement_no = str(rd.get("공고번호") or "").strip() or None

            # 중복 체크: 같은 사용자의 동일 공고번호
            if announcement_no:
                exists = self.db.query(MyBidRecord).filter(
                    MyBidRecord.user_id == user_id,
                    MyBidRecord.announcement_no == announcement_no,
                ).first()
                if exists:
                    skipped += 1
                    details.append(f"중복 건너뜀: {title[:40]} ({announcement_no})")
                    continue

            submitted_rate_raw = self._to_float(rd.get("제출투찰률"))
            if submitted_rate_raw is None:
                errors.append(f"행 {row_idx}: 제출투찰률 없음 — {title[:40]}")
                skipped += 1
                continue

            # 투찰률이 퍼센트 표기(예: 87.123)이면 /100
            submitted_rate = submitted_rate_raw / 100 if submitted_rate_raw > 1 else submitted_rate_raw

            result_raw = str(rd.get("결과") or "").strip()
            result = self.RESULT_MAP.get(result_raw, "pending")

            actual_winner_raw = self._to_float(rd.get("실제낙찰률"))
            actual_winner_rate = None
            if actual_winner_raw is not None:
                actual_winner_rate = actual_winner_raw / 100 if actual_winner_raw > 1 else actual_winner_raw

            rec_raw = self._to_float(rd.get("추천투찰률"))
            recommendation_rate = None
            if rec_raw is not None:
                recommendation_rate = rec_raw / 100 if rec_raw > 1 else rec_raw

            rate_diff = None
            if submitted_rate is not None and actual_winner_rate is not None:
                rate_diff = round(submitted_rate - actual_winner_rate, 6)

            try:
                rec = MyBidRecord(
                    user_id=user_id,
                    announcement_no=announcement_no,
                    title=title,
                    agency_name=str(rd.get("발주처") or "").strip() or None,
                    bid_date=self._to_date(rd.get("입찰일")),
                    base_amount=self._to_int(rd.get("기초금액")),
                    submitted_rate=submitted_rate,
                    recommendation_rate=recommendation_rate,
                    result=result,
                    actual_winner_rate=actual_winner_rate,
                    rate_diff=rate_diff,
                    note=str(rd.get("비고") or "").strip() or None,
                )
                self.db.add(rec)
                self.db.flush()
                MyBidFeedbackService(self.db).sync_outcome(rec)
                imported += 1
                details.append(f"등록: {title[:40]}")
            except Exception as exc:
                self.db.rollback()
                errors.append(f"행 {row_idx} 저장 실패: {exc}")
                skipped += 1

        self.db.commit()
        return {
            "imported": imported,
            "skipped": skipped,
            "competitors_added": 0,
            "errors": errors[:30],
            "details": details[:50],
        }


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




# ==================================================
# ② 패찰 원인 분석 (MyBidAnalysisService 확장)
# ==================================================

class DefeatAnalysisService:
    """
    패찰 이력에서 원인 분석:
    - 낙찰자 대비 얼마나 높게/낮게 입찰했는지
    - 발주처별 패턴
    - 시간 흐름에 따른 개선 추이
    """

    def __init__(self, db: Session):
        self.db = db

    def analyze(self, user_id: int) -> dict:
        from collections import defaultdict

        records = self.db.query(MyBidRecord).filter(
            MyBidRecord.user_id == user_id,
            MyBidRecord.result == "lost",
            MyBidRecord.actual_winner_rate.isnot(None),
            MyBidRecord.submitted_rate.isnot(None),
        ).order_by(MyBidRecord.bid_date.desc()).limit(500).all()

        if not records:
            return self._empty()

        # rate_diff (percentage point): winner_rate - submitted_rate
        diffs = []
        for r in records:
            if r.rate_diff is not None:
                d = float(r.rate_diff)
            else:
                d = (float(r.actual_winner_rate) - float(r.submitted_rate)) * 100
            diffs.append(d)

        arr = np.array(diffs)
        # 아웃라이어 제거 (|diff| > 5%)
        clean = arr[np.abs(arr) <= 5.0]

        miss_stats = self._compute_miss_stats(clean if len(clean) > 0 else arr)

        # 히스토그램 bins: -5 ~ +5, 0.2 단위
        bins = np.arange(-5.0, 5.2, 0.2)
        hist, edges = np.histogram(clean if len(clean) > 0 else arr, bins=bins)
        distribution = [
            {"from": round(float(edges[i]), 2), "to": round(float(edges[i+1]), 2), "count": int(hist[i])}
            for i in range(len(hist))
        ]

        # 발주처별 분석
        agency_map = defaultdict(list)
        for r, d in zip(records, diffs):
            if r.agency_name and abs(d) <= 5.0:
                agency_map[r.agency_name].append(d)

        agency_breakdown = []
        for name, ds in sorted(agency_map.items(), key=lambda x: len(x[1]), reverse=True)[:15]:
            a = np.array(ds)
            agency_breakdown.append({
                "agency_name": name,
                "count": len(ds),
                "avg_diff": round(float(np.mean(a)), 4),
                "direction": "too_low" if np.mean(a) > 0.15 else "too_high" if np.mean(a) < -0.15 else "balanced",
            })

        # 월별 추이
        monthly_map = defaultdict(list)
        for r, d in zip(records, diffs):
            if r.bid_date and abs(d) <= 5.0:
                key = r.bid_date.strftime("%Y-%m")
                monthly_map[key].append(d)

        trend = [
            {
                "year_month": k,
                "avg_diff": round(float(np.mean(monthly_map[k])), 4),
                "count": len(monthly_map[k]),
            }
            for k in sorted(monthly_map.keys())
        ]

        # 낙찰 구간 분석 (won 레코드)
        won_records = self.db.query(MyBidRecord).filter(
            MyBidRecord.user_id == user_id,
            MyBidRecord.result == "won",
            MyBidRecord.actual_winner_rate.isnot(None),
        ).all()
        win_zone = None
        if won_records:
            won_diffs = [float(r.rate_diff or 0) for r in won_records]
            win_zone = {
                "avg_diff": round(float(np.mean(won_diffs)), 4),
                "sample_count": len(won_diffs),
                "note": "낙찰 시 낙찰자 요율 대비 본인 요율 평균 차이",
            }

        return {
            "miss_stats": miss_stats,
            "distribution": distribution,
            "agency_breakdown": agency_breakdown,
            "trend": trend,
            "win_zone": win_zone,
            "total_analyzed": len(records),
        }

    def _compute_miss_stats(self, arr: np.ndarray) -> dict:
        if len(arr) == 0:
            return {}
        avg = float(np.mean(arr))
        return {
            "avg_diff_pct":      round(avg, 4),
            "median_diff_pct":   round(float(np.median(arr)), 4),
            "std_diff_pct":      round(float(np.std(arr)), 4),
            "pct_too_low":       round(float(np.mean(arr > 0.15)), 4),
            "pct_too_high":      round(float(np.mean(arr < -0.15)), 4),
            "pct_balanced":      round(float(np.mean(np.abs(arr) <= 0.15)), 4),
            "direction":         "too_low" if avg > 0.15 else "too_high" if avg < -0.15 else "balanced",
            "within_0_5pct":     round(float(np.mean(np.abs(arr) <= 0.5)), 4),
            "within_1pct":       round(float(np.mean(np.abs(arr) <= 1.0)), 4),
        }

    def _empty(self) -> dict:
        return {
            "miss_stats": {}, "distribution": [],
            "agency_breakdown": [], "trend": [],
            "win_zone": None, "total_analyzed": 0,
        }

    def get_gap_distribution(self, user_id: int) -> dict:
        """
        rate_diff 분포 분석 (0.005 버킷).
        diff = submitted_rate - actual_winner_rate (소수점 기준)
        양수 → 낙찰자보다 높게 투찰 (too_high), 음수 → 낙찰자보다 낮게 투찰 (too_low).
        """
        personal_bias = PersonalBiasAnalyzer().compute(self.db, user_id)

        records = (
            self.db.query(MyBidRecord)
            .filter(
                MyBidRecord.user_id == user_id,
                MyBidRecord.actual_winner_rate.isnot(None),
                MyBidRecord.submitted_rate.isnot(None),
            )
            .order_by(MyBidRecord.bid_date.desc())
            .limit(500)
            .all()
        )

        if not records:
            return self._gap_empty(personal_bias)

        OUTLIER = 0.05  # 5%p 이상 이상치 제거
        BUCKET = 0.005  # 소수점 기준 버킷 크기

        diffs = []
        for r in records:
            d = float(r.submitted_rate) - float(r.actual_winner_rate)
            if abs(d) <= OUTLIER:
                diffs.append(d)

        if not diffs:
            return self._gap_empty(personal_bias)

        arr = np.array(diffs)
        mean_diff = round(float(np.mean(arr)), 6)
        median_diff = round(float(np.median(arr)), 6)

        THRESHOLD = 0.0015  # 0.15%p
        if mean_diff > THRESHOLD:
            consistent_direction = "too_high"
        elif mean_diff < -THRESHOLD:
            consistent_direction = "too_low"
        else:
            consistent_direction = "mixed"

        win_if_lower_by = round(abs(mean_diff), 6) if consistent_direction == "too_high" else None

        bucket_counts: dict[float, int] = {}
        for d in diffs:
            key = round(math.floor(d / BUCKET) * BUCKET, 3)
            bucket_counts[key] = bucket_counts.get(key, 0) + 1

        buckets = [
            {
                "range_lo": lo,
                "range_hi": round(lo + BUCKET, 3),
                "count": cnt,
            }
            for lo, cnt in sorted(bucket_counts.items())
        ]

        return {
            "buckets": buckets,
            "mean_diff": mean_diff,
            "median_diff": median_diff,
            "win_if_lower_by": win_if_lower_by,
            "consistent_direction": consistent_direction,
            "personal_bias": personal_bias,
            "total_analyzed": len(diffs),
        }

    def _gap_empty(self, personal_bias: dict) -> dict:
        return {
            "buckets": [],
            "mean_diff": None,
            "median_diff": None,
            "win_if_lower_by": None,
            "consistent_direction": "mixed",
            "personal_bias": personal_bias,
            "total_analyzed": 0,
        }


# ==================================================
# 경쟁사 투찰 구간 분포 서비스
# ==================================================

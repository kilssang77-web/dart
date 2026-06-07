"""
백테스트 실행 및 리포트 생성.

모드:
  events     : feature_events 테이블 기반 (기본, --mode events)
  replay     : daily_bars에서 규칙 재적용 기반 백테스트 (--mode replay)
  thresholds : ML 확률 임계값(0.50~0.65)별 성과 비교 (--mode thresholds)
  ml_replay  : 훈련된 LightGBM 모델을 historical daily_bars에 직접 적용 (--mode ml_replay)

사용:
  python backtest_run.py --mode events --start 2023-01-01 --end 2024-12-31
  python backtest_run.py --mode thresholds --start 2023-01-01 --end 2024-12-31
  python backtest_run.py --mode ml_replay --start 2025-01-01 --end 2026-06-06 --threshold 0.273
"""
import argparse
import asyncio
import asyncpg
import os
import sys
import json
import logging
from datetime import date as date_type, timedelta
import pandas as pd
from pathlib import Path

sys.path.insert(0, "/app")
try:
    from backtest.engine import BacktestEngine
except ImportError:
    from ml.backtest.engine import BacktestEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backtest")


# ─── Signal loaders ────────────────────────────────────────────────────────────

async def load_signals_from_events(pool, start, end, event_type, min_score, ml_min_prob=0.0):
    start_d = date_type.fromisoformat(start)
    end_d   = date_type.fromisoformat(end)

    if ml_min_prob > 0:
        rows = await pool.fetch(
            """
            SELECT DISTINCT ON (fe.code, DATE(fe.detected_at))
                fe.code, DATE(fe.detected_at)::TEXT AS date, db.close, rec.success_prob
            FROM feature_events fe
            JOIN daily_bars db ON db.code=fe.code AND db.date=DATE(fe.detected_at)
            JOIN LATERAL (
                SELECT r.success_prob
                FROM recommendations r
                WHERE r.code = fe.code
                  AND r.created_at BETWEEN fe.detected_at - INTERVAL '1 hour'
                                       AND fe.detected_at + INTERVAL '4 hours'
                ORDER BY r.created_at DESC LIMIT 1
            ) rec ON true
            WHERE fe.event_type=$1
              AND fe.signal_score>=$2
              AND DATE(fe.detected_at) BETWEEN $3 AND $4
              AND rec.success_prob >= $5
            ORDER BY fe.code, DATE(fe.detected_at), fe.detected_at DESC
            """,
            event_type, min_score, start_d, end_d, ml_min_prob,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT DISTINCT ON (fe.code, DATE(fe.detected_at))
                fe.code, DATE(fe.detected_at)::TEXT AS date, db.close
            FROM feature_events fe
            JOIN daily_bars db ON db.code=fe.code AND db.date=DATE(fe.detected_at)
            WHERE fe.event_type=$1
              AND fe.signal_score>=$2
              AND DATE(fe.detected_at) BETWEEN $3 AND $4
            ORDER BY fe.code, DATE(fe.detected_at), fe.detected_at DESC
            """,
            event_type, min_score, start_d, end_d,
        )
    return pd.DataFrame([dict(r) for r in rows])


async def load_signals_replay(pool, start, end, rule: str, vol_ratio: float, min_amount: int):
    start_d = date_type.fromisoformat(start)
    end_d   = date_type.fromisoformat(end)
    if rule == "VOLUME_SURGE":
        rows = await pool.fetch(
            """
            WITH ma AS (
                SELECT code, date, close, volume, amount,
                       AVG(volume) OVER (
                           PARTITION BY code ORDER BY date
                           ROWS BETWEEN 21 PRECEDING AND 2 PRECEDING
                       ) AS avg_vol_20d
                FROM daily_bars
                WHERE code NOT IN ('0001','1001')
                  AND date BETWEEN ($1::date - INTERVAL '25 days')::date AND $2
            )
            SELECT code, date::TEXT AS date, close
            FROM ma
            WHERE date BETWEEN $1 AND $2
              AND avg_vol_20d > 0
              AND volume >= avg_vol_20d * $3
              AND amount >= $4
            ORDER BY date, code
            """,
            start_d, end_d, vol_ratio, min_amount,
        )
    elif rule == "BREAKOUT_52W":
        rows = await pool.fetch(
            """
            WITH hi AS (
                SELECT code, date, close,
                       MAX(high) OVER (
                           PARTITION BY code ORDER BY date
                           ROWS BETWEEN 260 PRECEDING AND 2 PRECEDING
                       ) AS high_52w
                FROM daily_bars
                WHERE code NOT IN ('0001','1001')
                  AND date BETWEEN ($1::date - INTERVAL '260 days')::date AND $2
            )
            SELECT code, date::TEXT AS date, close
            FROM hi
            WHERE date BETWEEN $1 AND $2
              AND high_52w > 0
              AND close > high_52w
            ORDER BY date, code
            """,
            start_d, end_d,
        )
    else:
        return pd.DataFrame()
    return pd.DataFrame([dict(r) for r in rows])


async def load_bars(pool, codes, start, end):
    start_d = date_type.fromisoformat(str(start))
    end_ext = date_type.fromisoformat(str(end)) + timedelta(days=22)
    rows = await pool.fetch(
        """
        SELECT code, date::TEXT, open, high, low, close, volume
        FROM daily_bars
        WHERE code=ANY($1) AND date BETWEEN $2 AND $3
        ORDER BY code, date
        """,
        codes, start_d, end_ext,
    )
    return pd.DataFrame([dict(r) for r in rows])


# ─── ML Replay helpers ─────────────────────────────────────────────────────────

async def _load_ml_replay_data(pool, start, end, max_codes: int = 500):
    """walk_forward_train.py 의 로딩 함수들을 재사용해 데이터 로드."""
    import importlib, types

    # walk_forward_train 함수들을 직접 임포트 (같은 /app 경로)
    try:
        import walk_forward_train as wft
    except ImportError:
        import importlib.util, os
        spec = importlib.util.spec_from_file_location(
            "walk_forward_train",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "walk_forward_train.py"),
        )
        wft = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(wft)

    # 거래대금 상위 codes 선택 (train 기간 2020~2023 기준 유동성)
    logger.info("Selecting liquid codes (train period 2020-2023)...")
    train_s = date_type.fromisoformat("2020-01-01")
    train_e = date_type.fromisoformat("2023-12-31")
    codes = await wft.get_liquid_codes(pool, train_s, train_e, max_codes)
    logger.info(f"Selected {len(codes)} codes")

    # lookback 60일 + ATR/BB 계산용으로 start 보다 90일 앞서서 로드
    start_d = date_type.fromisoformat(start)
    end_d   = date_type.fromisoformat(end)
    load_start_d = start_d - timedelta(days=90)

    logger.info(f"Loading daily_bars {load_start_d} ~ {end_d} ...")
    bars_raw = await wft.load_daily_bars(pool, load_start_d, end_d, codes)
    logger.info(f"Loaded {len(bars_raw)} rows")

    logger.info("Loading KOSPI index...")
    kospi_df = await wft.load_kospi(pool, load_start_d, end_d)

    logger.info("Loading disclosures...")
    disc_df = await wft.load_disclosures(pool, load_start_d, end_d)

    return wft, bars_raw, kospi_df, disc_df, codes


def _apply_entry_model(feat_df: pd.DataFrame, model_dir: str) -> pd.Series:
    """feat_df 에 entry model 적용 → success_prob 시리즈 반환."""
    import joblib
    import lightgbm as lgb
    from models.lgbm_predictor import FEATURE_COLUMNS

    mdl_path  = Path(model_dir) / "entry_model.lgb"
    cal_path  = Path(model_dir) / "entry_calibrator.pkl"
    feat_path = Path(model_dir) / "feature_columns.json"

    if not mdl_path.exists():
        raise FileNotFoundError(f"Entry model not found: {mdl_path}")

    model = lgb.Booster(model_file=str(mdl_path))

    cols = FEATURE_COLUMNS
    if feat_path.exists():
        with open(feat_path) as f:
            cols = json.load(f)

    missing = [c for c in cols if c not in feat_df.columns]
    if missing:
        logger.warning(f"Missing features (will fill 0): {missing}")
    X = feat_df.reindex(columns=cols, fill_value=0).astype("float32")

    raw_prob = model.predict(X)

    if cal_path.exists():
        calibrator = joblib.load(str(cal_path))
        if hasattr(calibrator, "predict_proba"):
            prob = calibrator.predict_proba(raw_prob.reshape(-1, 1))[:, 1]
        else:
            prob = calibrator.predict(raw_prob.reshape(-1, 1))
    else:
        prob = raw_prob

    return pd.Series(prob, index=feat_df.index, name="success_prob")


# ─── Run modes ─────────────────────────────────────────────────────────────────

async def run_events_mode(pool, args):
    event_types = [
        "VOLUME_SURGE", "BREAKOUT_52W", "LONG_WHITE_CANDLE",
        "SUPPLY_ANOMALY", "POST_DISCLOSURE_SURGE",
    ]
    results = {}
    for etype in event_types:
        signals = await load_signals_from_events(pool, args.start, args.end, etype, 0.6)
        if signals.empty:
            logger.info(f"{etype}: no signals")
            continue
        codes = signals["code"].unique().tolist()
        bars  = await load_bars(pool, codes, args.start, args.end)
        engine = BacktestEngine(
            stop_loss_pct=-args.stop_loss,
            target_pct=args.target,
            max_hold_days=args.hold,
        )
        result = engine.run(signals, bars)
        results[etype] = result.summary()
        logger.info(f"{etype}: {result.summary()}")
    return results


async def run_replay_mode(pool, args):
    vol_ratio  = float(os.environ.get("VOL_SURGE_RATIO", "5.0"))
    min_amount = int(os.environ.get("VOL_SURGE_MIN_AMOUNT", "1000000000"))

    rules = [("VOLUME_SURGE", vol_ratio), ("BREAKOUT_52W", None)]
    results = {}
    for rule, ratio in rules:
        signals = await load_signals_replay(
            pool, args.start, args.end, rule,
            vol_ratio=ratio or 5.0,
            min_amount=min_amount,
        )
        if signals.empty:
            logger.info(f"[replay] {rule}: no signals")
            continue
        codes = signals["code"].unique().tolist()
        bars  = await load_bars(pool, codes, args.start, args.end)
        engine = BacktestEngine(
            stop_loss_pct=-args.stop_loss,
            target_pct=args.target,
            max_hold_days=args.hold,
        )
        result = engine.run(signals, bars)
        results[rule] = result.summary()
        logger.info(f"[replay] {rule}: {result.summary()}")
    return results


async def run_threshold_mode(pool, args):
    """ML 확률 임계값(0.50, 0.55, 0.60, 0.65)별 성과 비교."""
    thresholds  = [0.0, 0.50, 0.55, 0.60, 0.65]
    event_types = ["VOLUME_SURGE", "BREAKOUT_52W", "LONG_WHITE_CANDLE"]
    engine = BacktestEngine(
        stop_loss_pct=-args.stop_loss,
        target_pct=args.target,
        max_hold_days=args.hold,
    )
    threshold_results = {}

    for thresh in thresholds:
        label = f"ml_prob_{thresh:.2f}" if thresh > 0 else "no_filter"
        threshold_results[label] = {}
        for etype in event_types:
            signals = await load_signals_from_events(
                pool, args.start, args.end, etype, 0.6, ml_min_prob=thresh
            )
            if signals.empty:
                logger.info(f"[thresholds] {label}/{etype}: no signals")
                threshold_results[label][etype] = {"signals": 0}
                continue
            codes = signals["code"].unique().tolist()
            bars  = await load_bars(pool, codes, args.start, args.end)
            result = engine.run(signals, bars)
            summary = result.summary()
            summary["signals"] = len(signals)
            threshold_results[label][etype] = summary
            logger.info(f"[thresholds] {label}/{etype}: n={len(signals)} win={summary['win_rate']}")

    return threshold_results


async def run_ml_replay_mode(pool, args):
    """
    훈련된 LightGBM entry model을 historical daily_bars에 직접 적용.
    - walk_forward_train.py 의 build_features() 재사용 (데이터 누수 없음)
    - success_prob >= threshold 인 날을 매수 신호로 처리
    - baseline (임계값 없음) 과 비교 리포트 출력
    """
    model_dir = os.environ.get("LGBM_MODEL_DIR", "/models/lgbm")
    threshold = args.threshold

    wft, bars_raw, kospi_df, disc_df, codes = await _load_ml_replay_data(
        pool, args.start, args.end
    )

    logger.info("Building features (this may take a few minutes)...")
    feat_df = wft.build_features(bars_raw, kospi_df, disc_df)
    logger.info(f"Features: {len(feat_df)} rows, {len(feat_df.columns)} cols")

    # 테스트 기간만 필터 (lookback 제외)
    start_ts = pd.Timestamp(args.start)
    end_ts   = pd.Timestamp(args.end)
    feat_df["__date"] = pd.to_datetime(feat_df["__date"])
    feat_df = feat_df[(feat_df["__date"] >= start_ts) & (feat_df["__date"] <= end_ts)].copy()
    logger.info(f"After date filter: {len(feat_df)} rows")

    if feat_df.empty:
        logger.error("No feature rows in the requested period — check daily_bars data coverage.")
        return {}

    logger.info(f"Applying entry model (threshold={threshold})...")
    feat_df["success_prob"] = _apply_entry_model(feat_df, model_dir)

    # Signals above threshold
    sig_df = feat_df[feat_df["success_prob"] >= threshold][["__code", "__date", "__close", "success_prob"]].copy()
    sig_df.columns = ["code", "date", "close", "success_prob"]
    sig_df["date"] = sig_df["date"].dt.strftime("%Y-%m-%d")

    logger.info(f"Signals (prob>={threshold}): {len(sig_df)}")

    engine = BacktestEngine(
        stop_loss_pct=-args.stop_loss,
        target_pct=args.target,
        max_hold_days=args.hold,
    )

    results = {}

    ml_result_obj = None
    if sig_df.empty:
        logger.warning(f"No signals at threshold {threshold}")
        results[f"ml_entry_{threshold}"] = {"signals": 0}
    else:
        sig_codes = sig_df["code"].unique().tolist()
        bars = await load_bars(pool, sig_codes, args.start, args.end)
        ml_result_obj = engine.run(sig_df, bars)
        summary = ml_result_obj.summary()
        summary["signals"]   = len(sig_df)
        summary["threshold"] = threshold
        results[f"ml_entry_{threshold}"] = summary
        logger.info(f"[ml_replay] threshold={threshold} n={len(sig_df)} "
                    f"win={ml_result_obj.win_rate:.3f} avg_ret={ml_result_obj.avg_return:.3f}%")

    # No-filter baseline
    all_signals = feat_df[["__code", "__date", "__close"]].copy()
    all_signals.columns = ["code", "date", "close"]
    all_signals["date"] = all_signals["date"].dt.strftime("%Y-%m-%d")
    all_codes = all_signals["code"].unique().tolist()
    all_bars = await load_bars(pool, all_codes, args.start, args.end)

    bl_result_obj = None
    if len(all_signals) > 0:
        bl_result_obj = engine.run(all_signals, all_bars)
        all_summary = bl_result_obj.summary()
        all_summary["signals"] = len(all_signals)
        results["baseline_no_filter"] = all_summary
        logger.info(f"[ml_replay] baseline (no filter) n={len(all_signals)} "
                    f"win={bl_result_obj.win_rate:.3f} avg_ret={bl_result_obj.avg_return:.3f}%")

    # Comparison table
    if ml_result_obj and bl_result_obj:
        logger.info("=" * 60)
        logger.info(f"{'':30s} {'ML(0.273)':>12s} {'Baseline':>12s}")
        logger.info(f"{'Signals':30s} {len(sig_df):>12d} {len(all_signals):>12d}")
        logger.info(f"{'Win Rate':30s} {ml_result_obj.win_rate:>12.3f} {bl_result_obj.win_rate:>12.3f}")
        logger.info(f"{'Avg Return (%)':30s} {ml_result_obj.avg_return:>12.3f} {bl_result_obj.avg_return:>12.3f}")
        logger.info(f"{'Profit Factor':30s} {ml_result_obj.profit_factor:>12.3f} {bl_result_obj.profit_factor:>12.3f}")
        logger.info(f"{'Max Drawdown (%)':30s} {ml_result_obj.max_drawdown:>12.3f} {bl_result_obj.max_drawdown:>12.3f}")
        logger.info(f"{'Sharpe':30s} {ml_result_obj.sharpe:>12.3f} {bl_result_obj.sharpe:>12.3f}")
        logger.info("=" * 60)

    return results


# ─── Main ──────────────────────────────────────────────────────────────────────

async def main(args):
    pool = await asyncpg.create_pool(
        dsn=os.environ["POSTGRES_DSN"].replace("+asyncpg", ""),
    )

    if args.mode == "replay":
        results = await run_replay_mode(pool, args)
        mode_key = "replay_results"
    elif args.mode == "thresholds":
        results = await run_threshold_mode(pool, args)
        mode_key = "threshold_results"
    elif args.mode == "ml_replay":
        results = await run_ml_replay_mode(pool, args)
        mode_key = "ml_replay_results"
    else:
        results = await run_events_mode(pool, args)
        mode_key = "event_results"

    out = Path("output")
    out.mkdir(exist_ok=True)

    report_path = out / "backtest_report.json"
    existing = {}
    if report_path.exists():
        try:
            with open(report_path) as f:
                existing = json.load(f)
        except Exception:
            pass

    existing.update({
        "updated_at": str(date_type.today()),
        "period":     {"start": args.start, "end": args.end},
        "params": {
            "stop_loss": args.stop_loss,
            "target":    args.target,
            "hold_days": args.hold,
        },
        mode_key: results,
    })

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    logger.info(f"Report saved to {report_path}")
    await pool.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode",      choices=["events", "replay", "thresholds", "ml_replay"], default="events")
    parser.add_argument("--start",     default="2025-01-01")
    parser.add_argument("--end",       default="2026-06-06")
    parser.add_argument("--stop-loss", type=float, default=0.05)
    parser.add_argument("--target",    type=float, default=0.10)
    parser.add_argument("--hold",      type=int,   default=10)
    parser.add_argument("--threshold", type=float, default=0.273, help="ML entry prob threshold (ml_replay mode)")
    asyncio.run(main(parser.parse_args()))
#!/usr/bin/env python3
"""
ML 모델 자동 재학습 서비스.

스케줄: 매월 말 (28일, 00:00 KST) 실행.
  - 새 모델을 /models/lgbm_new 에 학습
  - 새 AUC >= 기존 AUC - 0.02 AND >= MIN_AUC_THRESHOLD 이면 배포
  - 그 외 롤백, 기존 모델 유지

docker-compose.yml 에 ml-autoretrain 서비스로 등록.
환경변수:
  POSTGRES_DSN, REDIS_URL, LGBM_MODEL_DIR (기본 /models/lgbm)
  ML_MIN_AUC_THRESHOLD (기본 0.57)
  ML_RETRAIN_TRAIN_YEARS (학습 기간 연도 수, 기본 6)
  ML_RETRAIN_VAL_MONTHS (검증 기간 월 수, 기본 12)
"""
import asyncio
import json
import logging
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("auto_retrain")

_KST = timezone(timedelta(hours=9))

_MIN_AUC     = float(os.environ.get("ML_MIN_AUC_THRESHOLD",  "0.57"))
_TRAIN_YEARS = int(os.environ.get("ML_RETRAIN_TRAIN_YEARS",  "6"))
_VAL_MONTHS  = int(os.environ.get("ML_RETRAIN_VAL_MONTHS",   "12"))
_MODEL_DIR   = os.environ.get("LGBM_MODEL_DIR", "/models/lgbm")
_TMP_DIR     = _MODEL_DIR + "_new"
_HISTORY_FILE = "/models/retrain_history.json"

# 재학습 트리거: 매월 28일 00:00 KST
_RETRAIN_DAY  = int(os.environ.get("ML_RETRAIN_DAY", "28"))
_RETRAIN_HOUR = int(os.environ.get("ML_RETRAIN_HOUR", "0"))


def _load_metrics(model_dir: str) -> dict:
    path = Path(model_dir) / "model_metrics.json"
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _append_history(record: dict):
    history = []
    try:
        if os.path.exists(_HISTORY_FILE):
            with open(_HISTORY_FILE) as f:
                history = json.load(f)
    except Exception:
        pass
    history.append(record)
    # 최근 24개월 이력만 보관
    history = history[-24:]
    try:
        with open(_HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2, default=str)
    except Exception as e:
        logger.warning(f"이력 저장 실패: {e}")


async def run_retrain() -> bool:
    """재학습 실행. 배포 성공 시 True 반환."""
    now = datetime.now(_KST)
    logger.info(f"=== 자동 재학습 시작: {now.strftime('%Y-%m-%d %H:%M KST')} ===")

    # 날짜 범위 계산
    test_end   = now.date()
    test_start = (now - timedelta(days=90)).date()          # 최근 3개월 = 테스트
    val_end    = test_start - timedelta(days=1)
    val_start  = (now - timedelta(days=90 + _VAL_MONTHS * 30)).date()
    train_end  = val_start - timedelta(days=1)
    train_start = (now - timedelta(days=365 * _TRAIN_YEARS)).date()

    logger.info(
        f"학습: {train_start}~{train_end}  "
        f"검증: {val_start}~{val_end}  "
        f"테스트: {test_start}~{test_end}"
    )

    # 기존 모델 AUC 로드
    current_metrics = _load_metrics(_MODEL_DIR)
    current_auc     = float(current_metrics.get("auc", 0.0))
    logger.info(f"현재 모델 AUC: {current_auc:.4f}")

    # 임시 디렉토리 초기화
    Path(_TMP_DIR).mkdir(parents=True, exist_ok=True)

    # walk_forward_train.py 를 subprocess로 실행
    import subprocess
    cmd = [
        sys.executable, "walk_forward_train.py",
        "--train-start", str(train_start),
        "--train-end",   str(train_end),
        "--val-start",   str(val_start),
        "--val-end",     str(val_end),
        "--test-start",  str(test_start),
        "--test-end",    str(test_end),
        "--smote",
        "--max-codes",   "800",
        "--model-dir",   _TMP_DIR,
        "--label-mode",  "relative",   # 상대 레이블 사용 (walk_forward_train에 --label-mode 추가 필요)
    ]
    logger.info(f"학습 명령: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True,
            text=True,
            timeout=7200,  # 2시간 제한
        )
        if result.returncode != 0:
            logger.error(f"학습 실패 (returncode={result.returncode}):\n{result.stderr[-2000:]}")
            _append_history({
                "date": str(now.date()), "status": "train_failed",
                "current_auc": current_auc, "new_auc": None,
            })
            return False
        logger.info("학습 완료")
        if result.stdout:
            logger.info(f"학습 출력 (마지막 500자):\n{result.stdout[-500:]}")
    except subprocess.TimeoutExpired:
        logger.error("학습 타임아웃 (2시간 초과)")
        _append_history({
            "date": str(now.date()), "status": "timeout",
            "current_auc": current_auc, "new_auc": None,
        })
        return False
    except Exception as e:
        logger.error(f"학습 실행 오류: {e}")
        return False

    # 새 모델 AUC 확인
    new_metrics = _load_metrics(_TMP_DIR)
    new_auc     = float(new_metrics.get("auc", 0.0))
    logger.info(f"새 모델 AUC: {new_auc:.4f}  (기준: min={_MIN_AUC}, prev={current_auc:.4f})")

    # 배포 결정: 새 AUC >= 임계값 AND >= 기존 AUC - 0.02
    deploy = new_auc >= _MIN_AUC and new_auc >= current_auc - 0.02
    status = "deployed" if deploy else "rollback"

    if deploy:
        # 기존 모델 백업
        backup_dir = _MODEL_DIR + f"_backup_{now.strftime('%Y%m%d')}"
        if Path(_MODEL_DIR).exists():
            shutil.copytree(_MODEL_DIR, backup_dir, dirs_exist_ok=True)
            logger.info(f"기존 모델 백업: {backup_dir}")
        # 새 모델 배포
        shutil.copytree(_TMP_DIR, _MODEL_DIR, dirs_exist_ok=True)
        logger.info(f"새 모델 배포 완료: AUC {current_auc:.4f} → {new_auc:.4f}")
    else:
        logger.warning(
            f"롤백: new_auc={new_auc:.4f} < "
            f"threshold={_MIN_AUC} or < prev-0.02={current_auc - 0.02:.4f}. "
            "기존 모델 유지."
        )

    # 이력 저장
    _append_history({
        "date":        str(now.date()),
        "status":      status,
        "current_auc": current_auc,
        "new_auc":     new_auc,
        "train_start": str(train_start),
        "train_end":   str(train_end),
        "deployed":    deploy,
    })

    # 임시 디렉토리 정리
    try:
        shutil.rmtree(_TMP_DIR)
    except Exception:
        pass

    return deploy


def _seconds_until_next_retrain() -> float:
    """다음 재학습 시각(매월 _RETRAIN_DAY일 _RETRAIN_HOUR:00 KST)까지 대기 초."""
    now = datetime.now(_KST)
    # 이번 달 트리거 시각
    try:
        trigger = now.replace(
            day=_RETRAIN_DAY, hour=_RETRAIN_HOUR, minute=0, second=0, microsecond=0
        )
    except ValueError:
        # 해당 월에 28일이 없는 경우 (2월) → 말일로
        import calendar
        last_day = calendar.monthrange(now.year, now.month)[1]
        trigger  = now.replace(
            day=min(_RETRAIN_DAY, last_day),
            hour=_RETRAIN_HOUR, minute=0, second=0, microsecond=0
        )

    if now >= trigger:
        # 이미 지났으면 다음 달
        if now.month == 12:
            trigger = trigger.replace(year=now.year + 1, month=1)
        else:
            trigger = trigger.replace(month=now.month + 1)

    return (trigger - now).total_seconds()


async def main():
    while True:
        wait = _seconds_until_next_retrain()
        next_dt = datetime.now(_KST) + timedelta(seconds=wait)
        logger.info(
            f"다음 재학습 예정: {next_dt.strftime('%Y-%m-%d %H:%M KST')} "
            f"({wait / 3600:.1f}시간 후)"
        )
        await asyncio.sleep(wait)
        await run_retrain()
        # 재학습 직후 1시간 대기 (중복 실행 방지)
        await asyncio.sleep(3600)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--now", action="store_true", help="즉시 재학습 실행 (스케줄 무시)")
    args = parser.parse_args()

    if args.now:
        asyncio.run(run_retrain())
    else:
        asyncio.run(main())

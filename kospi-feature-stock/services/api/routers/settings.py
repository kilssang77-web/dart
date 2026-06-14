import os
import json
from datetime import datetime
from pathlib import Path
import orjson
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from deps import get_redis
import redis.asyncio as redis_lib

MODEL_DIR = Path(os.environ.get("MODEL_DIR", "/models/lgbm"))

REDIS_KEY = "telegram:config"

DEFAULT_CONFIG = {
    "enabled":             True,
    "min_prob":            0.22,
    "max_risk":            0.60,
    "min_risk_reward":     2.0,
    "disclosure_keywords": ["무상증자"],
}


async def _load(redis: redis_lib.Redis) -> dict:
    raw = await redis.get(REDIS_KEY)
    if raw:
        try:
            return orjson.loads(raw)
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


async def _save(redis: redis_lib.Redis, cfg: dict) -> None:
    await redis.set(REDIS_KEY, orjson.dumps(cfg))


class TelegramConfig(BaseModel):
    enabled:             bool         = Field(True)
    min_prob:            float        = Field(0.22, ge=0.0, le=1.0)
    max_risk:            float        = Field(0.60, ge=0.0, le=1.0)
    min_risk_reward:     float        = Field(2.0, ge=0.0)
    disclosure_keywords: list[str]   = Field(default_factory=lambda: ["무상증자"])


router = APIRouter()


@router.get("/telegram", response_model=TelegramConfig)
async def get_telegram_config(redis: redis_lib.Redis = Depends(get_redis)):
    return await _load(redis)


@router.put("/telegram", response_model=TelegramConfig)
async def update_telegram_config(
    body: TelegramConfig,
    redis: redis_lib.Redis = Depends(get_redis),
):
    cfg = body.model_dump()
    await _save(redis, cfg)
    return cfg


@router.post("/telegram/keywords", response_model=TelegramConfig)
async def add_keyword(
    keyword: str,
    redis: redis_lib.Redis = Depends(get_redis),
):
    cfg = await _load(redis)
    kws: list = cfg.setdefault("disclosure_keywords", [])
    kw = keyword.strip()
    if kw and kw not in kws:
        kws.append(kw)
    await _save(redis, cfg)
    return cfg


@router.delete("/telegram/keywords/{keyword}", response_model=TelegramConfig)
async def remove_keyword(
    keyword: str,
    redis: redis_lib.Redis = Depends(get_redis),
):
    cfg = await _load(redis)
    kws: list = cfg.get("disclosure_keywords", [])
    cfg["disclosure_keywords"] = [k for k in kws if k != keyword]
    await _save(redis, cfg)
    return cfg


@router.get("/model-status")
async def model_status():
    """ML 모델 학습 상태 반환. 모델 파일 없으면 rule_based 모드."""
    entry_model = MODEL_DIR / "entry_model.lgb"
    risk_model  = MODEL_DIR / "risk_model.lgb"
    metrics_file = MODEL_DIR / "model_metrics.json"
    feature_file = MODEL_DIR / "feature_columns.json"

    model_exists = entry_model.exists() and risk_model.exists()
    mode = "lgbm" if model_exists else "rule_based"

    result: dict = {
        "mode":           mode,
        "model_exists":   model_exists,
        "entry_model":    str(entry_model),
        "trained_at":     None,
        "feature_count":  None,
        "metrics":        {},
        "warning":        None if model_exists else "리스크 기반 규칙 모드로 운영 중 (모델 미학습)",
    }

    if metrics_file.exists():
        try:
            with metrics_file.open() as f:
                m = json.load(f)
            result["metrics"] = {
                "auc":           m.get("auc"),
                "f1":            m.get("f1"),
                "precision":     m.get("precision"),
                "recall":        m.get("recall"),
                "opt_threshold": m.get("optimal_threshold"),
            }
            result["trained_at"] = m.get("trained_at")
        except Exception:
            pass

    if feature_file.exists():
        try:
            with feature_file.open() as f:
                cols = json.load(f)
            result["feature_count"] = len(cols)
        except Exception:
            pass

    if model_exists:
        try:
            mtime = entry_model.stat().st_mtime
            result["file_mtime"] = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass

    return result
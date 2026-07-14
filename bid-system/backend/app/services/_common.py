"""
공통 헬퍼 함수 — services 패키지 전체에서 공유.
"""
import logging
import numpy as np
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..models import IndustryFilter

logger = logging.getLogger(__name__)


def _compute_yega_ml_features(pos_weights) -> dict:
    """pos_weights(15개 위치별 가중치) → ML 피처 3개 계산."""
    if pos_weights is None:
        return {"top3_freq": None, "entropy": None, "mode_bucket": None}
    w = np.array(pos_weights, dtype=float)
    top3_freq    = float(np.sort(w)[-3:].sum())
    entropy      = float(-np.sum(w * np.log(np.maximum(w, 1e-9))))
    mode_idx     = int(np.argmax(w))
    mode_bucket  = 1 if mode_idx < 5 else (3 if mode_idx >= 10 else 2)
    return {"top3_freq": top3_freq, "entropy": entropy, "mode_bucket": mode_bucket}


def get_active_industry_ids(db: Session):
    """활성화된 공종 ID 목록 반환.
    industry_filters 테이블이 비어있으면 None(전체 허용) 반환.
    설정이 있으면 is_active=True인 ID 목록만 반환."""
    filters = db.query(IndustryFilter).all()
    if not filters:
        return None  # 필터 미설정 = 전체 허용
    return [f.industry_id for f in filters if f.is_active]


def _build_ind_sql(active_ids, alias: str = "b") -> str:
    """활성 공종 SQL WHERE 조건 문자열 생성."""
    if active_ids is None:
        return ""
    if not active_ids:
        return "AND 1=0"
    ids_str = ",".join(map(str, active_ids))
    return f"AND {alias}.industry_id IN ({ids_str})"

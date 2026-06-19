"""
금융 뉴스/공시 감성 분석.
우선순위: KR-FinBERT (로컬 트랜스포머) → 키워드 기반 fallback
환경변수:
  SENTIMENT_MODEL: HuggingFace 모델명 (기본: snunlp/KR-FinBert-SC)
  USE_BERT_SENTIMENT: "true"/"false" (기본: true)
  MODEL_CACHE_DIR: 모델 캐시 경로 (기본: /models)
"""
import logging
import os
import re
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

_MODEL_NAME  = os.environ.get("SENTIMENT_MODEL", "snunlp/KR-FinBert-SC")
_CACHE_DIR   = os.environ.get("MODEL_CACHE_DIR", "/models")
_USE_BERT    = os.environ.get("USE_BERT_SENTIMENT", "true").lower() == "true"
_MAX_LEN     = 128   # KR-FinBERT max input
_SENTIMENT_POS_THR = float(os.environ.get("SENTIMENT_POS_THR", "0.15"))
_SENTIMENT_NEG_THR = float(os.environ.get("SENTIMENT_NEG_THR", "-0.15"))


# ── 키워드 fallback (원본 로직 유지) ─────────────────────────────────────────
POSITIVE = {
    "급등": 0.35, "신고가": 0.35, "어닝서프라이즈": 0.35, "FDA승인": 0.40,
    "임상성공": 0.35, "수주": 0.28, "흑자전환": 0.30, "독점계약": 0.32,
    "상승": 0.15, "호실적": 0.22, "실적개선": 0.22, "목표주가상향": 0.20,
    "매수추천": 0.18, "공급계약": 0.20, "수출": 0.15, "특허": 0.15,
    "성장": 0.12, "확대": 0.10, "증가": 0.10, "개선": 0.12,
    "MOU": 0.08, "협력": 0.07, "협약": 0.07, "기대": 0.06,
    "긍정적": 0.08, "호조": 0.10, "전망": 0.05,
}
NEGATIVE = {
    "급락": -0.35, "하한가": -0.40, "횡령": -0.45, "상장폐지": -0.50,
    "부도": -0.45, "파산": -0.45, "관리종목": -0.40, "손실급증": -0.30,
    "하락": -0.15, "실적부진": -0.22, "목표주가하향": -0.20,
    "매도추천": -0.18, "유상증자": -0.20, "전환사채": -0.15,
    "적자": -0.18, "감소": -0.10, "부진": -0.15, "우려": -0.10,
    "리스크": -0.08, "불확실": -0.07, "주의": -0.06,
    "하향": -0.10, "위축": -0.08,
}
_REVERSAL_PATTERNS = [
    (r"(하락|손실|적자)\s*(?:에서|에서의|을|를)?\s*(?:반전|탈피|극복|회복)", 0.15),
    (r"(?:우려|악재)\s*(?:해소|완화|극복)", 0.12),
    (r"(?:최저|저점)\s*(?:탈출|탈피|돌파)", 0.12),
]


def _keyword_analyze(title: str, content: str = "") -> dict:
    text_weighted = title + " " + title + " " + content[:1000]
    text_raw      = title + " " + content[:1000]
    score, matched = 0.0, []
    for kw, w in POSITIVE.items():
        if kw in text_weighted:
            score += w; matched.append(kw)
    for kw, w in NEGATIVE.items():
        if kw in text_weighted:
            score += w; matched.append(kw)
    for pat, bonus in _REVERSAL_PATTERNS:
        if re.search(pat, text_raw):
            score += bonus
    score = round(max(-1.0, min(1.0, score)), 3)
    label = "positive" if score >= _SENTIMENT_POS_THR else ("negative" if score <= _SENTIMENT_NEG_THR else "neutral")
    return {"sentiment_score": score, "label": label, "matched": matched[:10], "model": "keyword"}


# ── BERT 파이프라인 ───────────────────────────────────────────────────────────

# KR-FinBert-SC label mapping (labels may vary by model version)
_LABEL_MAP = {
    "positive": 1, "LABEL_2": 1,
    "negative": -1, "LABEL_0": -1,
    "neutral": 0, "LABEL_1": 0,
    # monologg/koelectra variants
    "긍정": 1, "부정": -1, "중립": 0,
}


@lru_cache(maxsize=1)
def _load_pipeline():
    if not _USE_BERT:
        logger.info("[Sentiment] BERT disabled by env (USE_BERT_SENTIMENT=false)")
        return None
    try:
        from transformers import pipeline as hf_pipeline
        pipe = hf_pipeline(
            "text-classification",
            model=_MODEL_NAME,
            cache_dir=_CACHE_DIR,
            device=-1,          # CPU; GPU: device=0
            truncation=True,
            max_length=_MAX_LEN,
        )
        logger.info(f"[Sentiment] BERT model loaded: {_MODEL_NAME}")
        return pipe
    except Exception as e:
        logger.warning(f"[Sentiment] BERT load failed: {e} — using keyword fallback")
        return None


def analyze(title: str, content: str = "") -> dict:
    """
    감성 분석 메인 진입점.
    Returns: {"sentiment_score": float[-1,1], "label": str, "matched": list, "model": str}
    """
    pipe = _load_pipeline()
    if pipe is not None:
        try:
            text   = (title + " " + content[:300]).strip()
            text   = text[:512]   # transformer max
            result = pipe(text)[0]
            polarity  = _LABEL_MAP.get(result["label"], _LABEL_MAP.get(result["label"].lower(), 0))
            confidence = float(result["score"])
            signed    = round(polarity * confidence, 3)
            label     = "positive" if polarity > 0 else ("negative" if polarity < 0 else "neutral")
            return {
                "sentiment_score": signed,
                "label":   label,
                "matched": [result["label"]],
                "model":   _MODEL_NAME,
            }
        except Exception as e:
            logger.warning(f"[Sentiment] BERT inference error: {e}")

    return _keyword_analyze(title, content)

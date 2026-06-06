import re
import logging

logger = logging.getLogger(__name__)

# ── 금융 도메인 감성 키워드 (가중치) ─────────────────────────────────────────
POSITIVE = {
    # 강한 긍정
    "급등": 0.35, "신고가": 0.35, "어닝서프라이즈": 0.35, "FDA승인": 0.40,
    "임상성공": 0.35, "수주": 0.28, "흑자전환": 0.30, "독점계약": 0.32,
    # 중간 긍정
    "상승": 0.15, "호실적": 0.22, "실적개선": 0.22, "목표주가상향": 0.20,
    "매수추천": 0.18, "공급계약": 0.20, "수출": 0.15, "특허": 0.15,
    "성장": 0.12, "확대": 0.10, "증가": 0.10, "개선": 0.12,
    # 약한 긍정
    "MOU": 0.08, "협력": 0.07, "협약": 0.07, "기대": 0.06,
    "긍정적": 0.08, "호조": 0.10, "전망": 0.05,
}

NEGATIVE = {
    # 강한 부정
    "급락": -0.35, "하한가": -0.40, "횡령": -0.45, "상장폐지": -0.50,
    "부도": -0.45, "파산": -0.45, "관리종목": -0.40, "손실급증": -0.30,
    # 중간 부정
    "하락": -0.15, "실적부진": -0.22, "목표주가하향": -0.20,
    "매도추천": -0.18, "유상증자": -0.20, "전환사채": -0.15,
    "적자": -0.18, "감소": -0.10, "부진": -0.15, "우려": -0.10,
    # 약한 부정
    "리스크": -0.08, "불확실": -0.07, "주의": -0.06,
    "하향": -0.10, "위축": -0.08,
}

# 부정 반전 패턴: "하락 반전" 같은 경우 긍정으로 전환
_REVERSAL_PATTERNS = [
    (r"(하락|손실|적자)\s*(?:에서|에서의|을|를)?\s*(?:반전|탈피|극복|회복)", 0.15),
    (r"(?:우려|악재)\s*(?:해소|완화|극복)", 0.12),
    (r"(?:최저|저점)\s*(?:탈출|탈피|돌파)", 0.12),
]


def analyze(title: str, content: str = "") -> dict:
    """
    제목 + 본문 기반 뉴스 감성 점수 계산.
    Returns: {"sentiment_score": float, "label": str, "matched": list}
    """
    # 제목에 2배 가중치
    text_weighted = title + " " + title + " " + content[:1000]
    text_raw = title + " " + content[:1000]

    score = 0.0
    matched = []

    for kw, weight in POSITIVE.items():
        if kw in text_weighted:
            score += weight
            matched.append(kw)

    for kw, weight in NEGATIVE.items():
        if kw in text_weighted:
            score += weight  # weight는 이미 음수
            matched.append(kw)

    # 반전 패턴 보정
    for pattern, bonus in _REVERSAL_PATTERNS:
        if re.search(pattern, text_raw):
            score += bonus

    score = round(max(-1.0, min(1.0, score)), 3)

    if score >= 0.15:
        label = "positive"
    elif score <= -0.15:
        label = "negative"
    else:
        label = "neutral"

    return {"sentiment_score": score, "label": label, "matched": matched[:10]}

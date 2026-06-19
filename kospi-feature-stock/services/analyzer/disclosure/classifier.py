import re
import os
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

_USD_KRW = float(os.environ.get("USD_KRW_RATE", "1400"))
_POS_THR = float(os.environ.get("DISCLOSURE_POS_THR", "0.10"))
_NEG_THR = float(os.environ.get("DISCLOSURE_NEG_THR", "-0.10"))

# ── 호재 키워드 (3단계 가중치) ───────────────────────────────────────────────
FAVORABLE_T1 = {  # 0.35 — 강한 호재
    "FDA승인", "EMA승인", "신약승인", "임상성공", "임상3상성공",
    "자기주식소각", "자사주소각", "어닝서프라이즈", "독점계약", "글로벌계약",
}
FAVORABLE_T2 = {  # 0.20 — 중간 호재
    "공급계약", "수주", "특허취득", "특허등록", "기술이전", "기술수출",
    "흑자전환", "실적개선", "실적호전", "자기주식취득", "자사주매입",
    "배당확대", "특별배당", "수출계약", "해외진출", "IPO", "상장예비심사",
    "정부과제", "국책사업", "신규사업", "핵심기술취득",
}
FAVORABLE_T3 = {  # 0.10 — 약한 호재
    "MOU", "업무협약", "협력협약", "전략적제휴", "R&D과제", "과제선정",
    "증자없는자금조달", "무담보사채", "이익잉여금", "자산재평가",
}

# ── 악재 키워드 (3단계 가중치) ───────────────────────────────────────────────
UNFAVORABLE_T1 = {  # -0.40 — 강한 악재
    "횡령", "배임", "사기", "형사고발", "금융감독원조사",
    "관리종목", "상장폐지", "거래정지", "자본잠식", "부도", "파산",
    "감사의견", "한정의견", "부적정", "의견거절",
}
UNFAVORABLE_T2 = {  # -0.22 — 중간 악재
    "유상증자", "주주배정", "일반공모증자", "제3자배정",
    "전환사채", "CB발행", "신주인수권부사채", "BW발행",
    "최대주주변경", "대주주변경", "경영권분쟁",
    "영업정지", "사업취소", "계약해지", "계약취소",
    "부채급증", "당기순손실",
}
UNFAVORABLE_T3 = {  # -0.10 — 약한 악재
    "전환청구", "주식전환",
    "공매도증가", "신용잔고급증", "담보부족",
}

# ── 공시 유형별 기본 점수 ─────────────────────────────────────────────────────
TYPE_BASE = {
    "주요사항보고": 0.0,
    "공급계약":    0.15,
    "수주":        0.15,
    "유상증자":   -0.18,
    "전환사채":   -0.12,
    "최대주주변경": -0.08,
    "신약":        0.20,
    "임상":        0.15,
    "횡령":       -0.45,
    "관리종목":   -0.40,
    "상장폐지":   -0.50,
    # 추가 공시 유형
    "주주명부폐쇄":            0.08,   # 배당 기준일 설정 → 배당 지급 예정
    "기준일설정":              0.06,
    "배당":                    0.12,   # 배당 발표
    "증권발행실적보고서":     -0.10,   # 증자 완료 → 희석화 실현
    "대량보유상황보고서":      0.10,   # 5%+ 지분 취득 → 관심 증가
    "주식대량취득":            0.12,
    "자기주식취득결과":        0.10,   # 자사주 매입 완료 → 우호적
    "자기주식처분결과":       -0.10,   # 자사주 처분 → 희석
    "유상감자":               -0.20,
    "무상감자":               -0.25,
    "주식병합":               -0.12,
    "전환청구권행사":         -0.10,   # CB 전환 → 주식 희석
    "신주인수권행사":         -0.10,
    "파생결합사채":           -0.08,   # ELS/DLS 발행 관련
    "단일판매·공급계약체결":   0.15,
    "계약체결":                0.10,
    "합병":                    0.05,   # 합병은 중립 → 내용 분석 필요
    "분할":                   -0.05,
    "기업설명회":              0.06,   # IR = 주주친화
    "영업(잠정)실적":          0.05,   # 실적 발표 (내용에 따라 변동)
    "감사보고서(적정)":        0.05,
    "한정의견":               -0.35,
    "부적정":                 -0.45,
    "의견거절":               -0.50,
}

# ── 부정 맥락 패턴 (해당 시 점수 차감) ──────────────────────────────────────
_NEGATIVE_CONTEXT = [
    (r"계약\s*(취소|해지|철회|실패)", -0.25),
    (r"(손실|적자|결손)\s*로\s*인한\s*유상증자", -0.15),
    (r"(전환|행사)\s*청구\s*완료", -0.10),
    (r"(소송|소제기|손해배상)\s*청구", -0.12),
    (r"부도\s*위기|워크아웃|법정관리", -0.35),
    (r"계열사\s*(지원|지급보증)", -0.08),
]

# ── 긍정 맥락 패턴 (부정어 무효화 — "계약해지 가능성 없음" 등) ────────────────
# 패턴: (부정어 무효화 패턴, 상쇄 점수)
# 이 패턴이 매칭되면 해당 부정 키워드 점수를 상쇄함
_NEGATION_NEUTRALIZE = [
    # "~가 아님", "~이 없음", "~할 가능성 없음" 등 부정어가 붙은 악재 키워드
    (r"(계약해지|계약취소|계약실패)\s*(가능성|우려|위험)?\s*(없|아니|부인|해소|해결|완료)", +0.20),
    (r"(소송|분쟁)\s*(해결|종료|취하|화해|승소)", +0.15),
    (r"(관리종목|상장폐지)\s*(해제|탈피|벗어|회피)", +0.30),
    (r"(유상증자|CB발행)\s*(철회|취소|없음|미실시)", +0.15),
    (r"(횡령|배임)\s*(혐의\s*)?(없음|무죄|무혐의|기각)", +0.25),
    (r"(부도|파산)\s*(위기\s*)?(없음|해소|극복|정상화)", +0.20),
    # 실적 관련 긍정 맥락
    (r"(적자|손실)\s*(폭\s*)?(축소|감소|개선|전환)", +0.15),
    (r"(흑자|이익)\s*(전환|달성|확대|증가)", +0.20),
    # 규제 이슈 해소
    (r"(금융감독원|금감원)\s*(조사|검사)\s*(종료|완료|이상\s*없음)", +0.15),
]

# ── 미래 불확실성 할인 패턴 (호재 키워드가 있어도 점수 할인) ──────────────────
# "예정", "검토 중", "추진 중" 등은 확정 호재보다 약함
_UNCERTAINTY_DISCOUNT = [
    (r"(수주|계약|흑자전환)\s*(예정|검토|추진\s*중|협의\s*중)", -0.08),
    (r"임상\s*(1상|전임상|개시)", -0.05),  # 초기 임상은 불확실
    (r"MOU|업무협약.*체결\s*예정", -0.05),
]

AMOUNT_PATTERNS = [
    (r"(\d[\d,]*)\s*조\s*원",                  1_000_000_000_000),
    (r"(\d[\d,]*(?:\.\d+)?)\s*억\s*원",        100_000_000),
    (r"(\d[\d,]*)\s*만\s*원",                  10_000),
    (r"(\d[\d,]*)\s*원",                        1),
    (r"USD\s*([\d,]+(?:\.\d+)?)\s*(?:백만|M)",  1_000_000),
    (r"USD\s*([\d,]+(?:\.\d+)?)",               1),
]


class DisclosureClassifier:

    @staticmethod
    def _normalize(text: str) -> str:
        """한글 단어 사이 공백 제거 — '유상 증자' → '유상증자' 매칭 지원."""
        import re
        return re.sub(r"(?<=[가-힣])\s+(?=[가-힣])", "", text)

    def classify(self, title: str, content: str = "", disclosure_type: str = "") -> dict:
        raw = f"{title} {content[:2000]}"
        text = self._normalize(raw)
        matched_kw: list[str] = []
        score = 0.0

        # 공시 유형 기본 점수
        for type_kw, base in TYPE_BASE.items():
            if type_kw in (disclosure_type or title):
                score += base
                break

        # 임원·대주주 특정증권 소유상황보고서 — 취득 vs 처분 구분
        if "임원" in title or "주요주주" in title or "소유상황" in title:
            has_acquire = any(kw in text for kw in ("취득", "매수", "장내매수", "증가"))
            has_dispose = any(kw in text for kw in ("처분", "매도", "장내매도", "감소"))
            if has_acquire and not has_dispose:
                score += 0.10; matched_kw.append("임원취득")
            elif has_dispose and not has_acquire:
                score -= 0.08; matched_kw.append("임원처분")

        # 호재 키워드
        for kw in FAVORABLE_T1:
            if kw in text:
                matched_kw.append(kw)
                score += 0.35
        for kw in FAVORABLE_T2:
            if kw in text:
                matched_kw.append(kw)
                score += 0.20
        for kw in FAVORABLE_T3:
            if kw in text:
                matched_kw.append(kw)
                score += 0.10

        # 악재 키워드
        for kw in UNFAVORABLE_T1:
            if kw in text:
                matched_kw.append(kw)
                score -= 0.40
        for kw in UNFAVORABLE_T2:
            if kw in text:
                matched_kw.append(kw)
                score -= 0.22
        for kw in UNFAVORABLE_T3:
            if kw in text:
                matched_kw.append(kw)
                score -= 0.10

        # 부정 맥락 패턴
        for pattern, penalty in _NEGATIVE_CONTEXT:
            if re.search(pattern, text):
                score += penalty

        # 긍정 맥락 패턴 (부정어 무효화)
        for pattern, offset in _NEGATION_NEUTRALIZE:
            if re.search(pattern, text):
                score += offset

        # 미래 불확실성 할인
        for pattern, discount in _UNCERTAINTY_DISCOUNT:
            if re.search(pattern, text):
                score += discount

        # 금액 규모 보정: 규모가 클수록 긍정 방향으로 보정 (큰 조건 먼저 검사)
        amount, _ = self.extract_amount(text)
        if amount >= 1_000_000_000_000 and score > 0:    # 1조 이상
            score += 0.10
        elif amount >= 100_000_000_000 and score > 0:    # 1000억 이상
            score += 0.05
        elif amount > 0 and amount < 1_000_000_000 and score > 0:  # 10억 미만 소규모
            score *= 0.7  # 소규모 계약은 호재 강도 30% 할인

        score = round(max(-1.0, min(1.0, score)), 3)

        if score >= _POS_THR:
            category = "favorable"
        elif score <= _NEG_THR:
            category = "unfavorable"
        else:
            category = "neutral"

        return {
            "category":        category,
            "sentiment_score": score,
            "keywords":        matched_kw[:15],
        }

    def extract_amount(self, text: str) -> tuple[int, str]:
        for pattern, multiplier in AMOUNT_PATTERNS:
            m = re.search(pattern, text)
            if m:
                try:
                    raw = float(m.group(1).replace(",", ""))
                    if "USD" in pattern:
                        raw *= _USD_KRW
                    return int(raw * multiplier), m.group(0)
                except Exception:
                    continue
        return 0, ""

    def extract_counterparty(self, text: str) -> str:
        patterns = [
            r"계약상대방\s*[:：]\s*(.+?)(?:\n|,|\.|\(|$)",
            r"거래상대방\s*[:：]\s*(.+?)(?:\n|,|\.|\(|$)",
            r"매수인\s*[:：]\s*(.+?)(?:\n|,|\.|\(|$)",
            r"공급받는자\s*[:：]\s*(.+?)(?:\n|,|\.|\(|$)",
            r"(?:납품처|발주처)\s*[:：]\s*(.+?)(?:\n|,|\.|\(|$)",
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                return m.group(1).strip()[:200]
        return ""

    def extract_contract_period(self, text: str) -> str:
        patterns = [
            r"계약기간\s*[:：]\s*(.+?)(?:\n|$)",
            r"이행기간\s*[:：]\s*(.+?)(?:\n|$)",
            r"(\d{4}[-\.]\d{1,2}[-\.]\d{1,2}.{1,10}~.{1,10}\d{4}[-\.]\d{1,2}[-\.]\d{1,2})",
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                return m.group(1).strip()[:100]
        return ""


# ── KR-FinBERT 기반 공시 분류기 ───────────────────────────────────────────────

_BERT_MODEL      = os.environ.get("SENTIMENT_MODEL", "snunlp/KR-FinBert-SC")
_BERT_CACHE      = os.environ.get("MODEL_CACHE_DIR", "/models")
_USE_BERT        = os.environ.get("USE_BERT_SENTIMENT", "true").lower() == "true"
_BERT_WEIGHT     = float(os.environ.get("DISCLOSURE_BERT_WEIGHT", "0.90"))   # 0.65→0.90
_BERT_CONF_THR   = float(os.environ.get("DISCLOSURE_BERT_CONF_THR", "0.55")) # 이하면 keyword-only
_BERT_LABEL_MAP = {
    "positive": 1, "LABEL_2": 1,
    "negative": -1, "LABEL_0": -1,
    "neutral": 0, "LABEL_1": 0,
    "긍정": 1, "부정": -1, "중립": 0,
}


@lru_cache(maxsize=1)
def _load_bert_pipeline():
    if not _USE_BERT:
        return None
    try:
        from transformers import pipeline as hf_pipeline
        pipe = hf_pipeline(
            "text-classification",
            model=_BERT_MODEL,
            cache_dir=_BERT_CACHE,
            device=-1,
            truncation=True,
            max_length=128,
        )
        logger.info(f"[DisclosureBERT] 모델 로드 완료: {_BERT_MODEL}")
        return pipe
    except Exception as e:
        logger.warning(f"[DisclosureBERT] 로드 실패: {e} — keyword fallback 사용")
        return None


class DisclosureBERTClassifier:
    """KR-FinBERT 주도 분류기 (키워드는 저신뢰도 fallback).

    BERT confidence >= _BERT_CONF_THR(0.55) 이면 BERT 결과에 _BERT_WEIGHT(0.90) 비중을 부여.
    confidence < 0.55 이면 BERT 무시 — 키워드 분류기만 사용.
    BERT 자체가 로드 불가인 경우에도 키워드 분류기로 안전하게 fallback.
    """

    def __init__(self):
        self._kw_clf = DisclosureClassifier()

    def classify(self, title: str, content: str = "", disclosure_type: str = "") -> dict:
        kw_result = self._kw_clf.classify(title, content, disclosure_type)
        kw_score  = kw_result["sentiment_score"]

        bert_score: float | None = None
        bert_confidence: float = 0.0
        model_used = "keyword"

        pipe = _load_bert_pipeline()
        if pipe is not None:
            try:
                text = (title + " " + content[:300]).strip()[:512]
                result = pipe(text)[0]
                polarity        = _BERT_LABEL_MAP.get(result["label"],
                                  _BERT_LABEL_MAP.get(result["label"].lower(), 0))
                bert_confidence = float(result["score"])
                bert_score      = round(polarity * bert_confidence, 4)
                model_used      = _BERT_MODEL
            except Exception as e:
                logger.warning(f"[DisclosureBERT] 추론 오류: {e}")

        if bert_score is not None and bert_confidence >= _BERT_CONF_THR:
            # 고신뢰도: BERT 90% + 키워드 10%
            w        = _BERT_WEIGHT * bert_confidence
            combined = w * bert_score + (1.0 - w) * kw_score
        else:
            # 저신뢰도 또는 BERT 불가: 키워드 전용
            combined = kw_score
            if bert_score is not None:
                logger.debug(
                    f"[DisclosureBERT] confidence={bert_confidence:.3f} < {_BERT_CONF_THR} "
                    "— keyword fallback"
                )

        combined = round(max(-1.0, min(1.0, combined)), 3)

        if combined >= _POS_THR:
            category = "favorable"
        elif combined <= _NEG_THR:
            category = "unfavorable"
        else:
            category = "neutral"

        return {
            "category":        category,
            "sentiment_score": combined,
            "bert_score":      bert_score,
            "bert_confidence": round(bert_confidence, 4),
            "kw_score":        kw_score,
            "keywords":        kw_result["keywords"],
            "model":           model_used,
        }

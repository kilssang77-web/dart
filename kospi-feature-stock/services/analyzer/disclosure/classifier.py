import re
import os
import logging

logger = logging.getLogger(__name__)

_USD_KRW = float(os.environ.get("USD_KRW_RATE", "1400"))
_POS_THR = float(os.environ.get("DISCLOSURE_POS_THR", "0.20"))
_NEG_THR = float(os.environ.get("DISCLOSURE_NEG_THR", "-0.20"))

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

AMOUNT_PATTERNS = [
    (r"(\d[\d,]*)\s*조\s*원",                  1_000_000_000_000),
    (r"(\d[\d,]*(?:\.\d+)?)\s*억\s*원",        100_000_000),
    (r"(\d[\d,]*)\s*만\s*원",                  10_000),
    (r"(\d[\d,]*)\s*원",                        1),
    (r"USD\s*([\d,]+(?:\.\d+)?)\s*(?:백만|M)",  1_000_000),
    (r"USD\s*([\d,]+(?:\.\d+)?)",               1),
]


class DisclosureClassifier:

    def classify(self, title: str, content: str = "", disclosure_type: str = "") -> dict:
        text = f"{title} {content[:2000]}"
        matched_kw: list[str] = []
        score = 0.0

        # 공시 유형 기본 점수
        for type_kw, base in TYPE_BASE.items():
            if type_kw in (disclosure_type or title):
                score += base
                break

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

        # 금액 규모 보정: 1000억 이상이면 긍정 방향으로 소폭 보정
        amount, _ = self.extract_amount(text)
        if amount >= 100_000_000_000 and score > 0:   # 1000억 이상
            score += 0.05
        elif amount >= 1_000_000_000_000 and score > 0:  # 1조 이상
            score += 0.10

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

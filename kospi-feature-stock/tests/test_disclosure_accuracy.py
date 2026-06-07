"""
공시 분류 정확도 측정 테스트.
목표: 85% 이상

실행: python -m pytest tests/test_disclosure_accuracy.py -v
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "analyzer"))

from disclosure.classifier import DisclosureClassifier

clf = DisclosureClassifier()

# ── 라벨링된 테스트 데이터 (70건) ──────────────────────────────────────────────
# (title, content_snippet, expected_category)
TEST_CASES = [
    # ── 호재 (favorable) ─────────────────────────────────────────────────────
    ("FDA 신약 승인 획득", "당사는 FDA로부터 신약 승인을 획득하였습니다.", "favorable"),
    ("임상3상성공 및 신약승인 신청", "글로벌 임상3상성공으로 FDA 신약승인을 신청했습니다.", "favorable"),
    ("자기주식소각 결정", "이사회에서 자기주식소각 결정을 의결하였습니다.", "favorable"),
    ("어닝서프라이즈 3분기 실적", "영업이익이 시장 전망치를 크게 상회하는 어닝서프라이즈를 달성했습니다.", "favorable"),
    ("독점계약 체결", "국내 독점계약을 체결하고 독점 공급권을 확보했습니다.", "favorable"),
    ("글로벌계약 5000억 수주", "해외 글로벌계약을 체결하여 5000억원 규모의 수주를 달성하였습니다.", "favorable"),
    ("공급계약 체결 3년", "500억원 규모의 공급계약을 체결하였습니다.", "favorable"),
    ("특허취득 핵심기술", "핵심기술에 대한 특허취득이 완료되었습니다.", "favorable"),
    ("흑자전환 달성", "당분기 흑자전환에 성공하여 영업이익 200억원을 기록했습니다.", "favorable"),
    ("자사주매입 결정", "500억원 규모의 자기주식취득(자사주매입)을 결정했습니다.", "favorable"),
    ("기술이전 계약 1000억", "해외 제약사와 1000억원 기술이전 계약을 체결하였습니다.", "favorable"),
    ("특별배당 결정", "특별배당 500원을 결정하였습니다.", "favorable"),
    ("정부 국책사업 선정", "산업부 국책사업에 선정되어 300억원 과제를 수행합니다.", "favorable"),
    ("수출계약 2000억 체결", "동남아시아 수출계약 2000억원을 체결했습니다.", "favorable"),
    ("EMA승인 EU 신약", "유럽의약품청(EMA)으로부터 신약 EMA승인을 받았습니다.", "favorable"),
    ("실적호전 영업익 급증", "실적호전 지속으로 영업이익이 전년 대비 150% 성장했습니다.", "favorable"),
    ("IPO 상장예비심사 통과", "코스닥 IPO 상장예비심사 승인을 받았습니다.", "favorable"),
    ("임상성공 2상 완료", "임상성공 — 2상 완료 후 유효성 확인.", "favorable"),
    ("신규사업 AI 반도체", "AI 반도체 신규사업 진출을 결정했습니다.", "favorable"),
    ("기술수출 미국 500억", "미국 기업에 핵심 기술수출 계약 500억원을 체결하였습니다.", "favorable"),
    ("수주잔고 1조 달성", "수주잔고가 1조원을 돌파했습니다.", "favorable"),
    ("배당확대 주당 1000원", "주당 배당금을 500원에서 1000원으로 배당확대 결정.", "favorable"),
    ("핵심기술취득 M&A", "경쟁사 핵심기술취득을 위한 M&A 완료.", "favorable"),
    ("과제선정 R&D 200억", "정부 R&D과제에 선정되어 200억 지원 예정.", "favorable"),
    ("MOU 대형 건설사", "대형 건설사와 전략적 MOU를 체결했습니다.", "favorable"),

    # ── 악재 (unfavorable) ────────────────────────────────────────────────────
    ("대표이사 횡령 혐의 검찰 수사", "대표이사가 회사 자금 횡령 혐의로 검찰에 기소되었습니다.", "unfavorable"),
    ("배임 혐의로 경찰 조사", "임원 배임 혐의로 경찰 조사를 받고 있습니다.", "unfavorable"),
    ("관리종목 지정 예고", "연속 적자로 관리종목 지정 예고 통보를 받았습니다.", "unfavorable"),
    ("상장폐지 사유 발생", "실질심사 대상으로 상장폐지 위기에 처했습니다.", "unfavorable"),
    ("자본잠식 50% 초과", "자본잠식이 50%를 초과하여 관리종목 지정 위기입니다.", "unfavorable"),
    ("부도 위기 워크아웃 신청", "부도 위기로 채권단에 워크아웃을 신청했습니다.", "unfavorable"),
    ("감사의견 거절", "외부감사인으로부터 감사의견 거절을 통보받았습니다.", "unfavorable"),
    ("한정의견 재무제표 수정", "감사인이 한정의견을 표명하였습니다.", "unfavorable"),
    ("유상증자 300억 주주배정", "300억원 규모의 유상증자(주주배정 방식)를 결정했습니다.", "unfavorable"),
    ("전환사채 CB발행 200억", "이사회에서 전환사채(CB) 200억원 발행을 결의하였습니다.", "unfavorable"),
    ("최대주주변경 경영권분쟁", "최대주주변경으로 경영권분쟁이 발생했습니다.", "unfavorable"),
    ("영업정지 처분", "금융당국으로부터 영업정지 처분을 받았습니다.", "unfavorable"),
    ("계약해지 통보 수령", "주요 거래처로부터 계약해지 통보를 받았습니다.", "unfavorable"),
    ("형사고발 당하다", "회사 임원이 형사고발을 당했습니다.", "unfavorable"),
    ("금융감독원조사 착수", "금융감독원이 분식회계 의혹으로 조사에 착수했습니다.", "unfavorable"),
    ("신주인수권부사채 BW발행 500억", "500억원 규모의 신주인수권부사채(BW) 발행을 결정했습니다.", "unfavorable"),
    ("당기순손실 적자전환", "당기순손실로 적자전환, 영업이익 -150억원 기록.", "unfavorable"),
    ("부도 파산 신청", "법원에 파산 신청을 하였습니다.", "unfavorable"),
    ("사기 피해 소송", "대규모 사기 피해로 소송이 제기되었습니다.", "unfavorable"),
    ("거래정지 처분", "거래정지 처분을 받아 즉시 거래가 정지되었습니다.", "unfavorable"),
    ("제3자배정 유상증자 희석", "제3자배정 유상증자로 지분 희석이 예상됩니다.", "unfavorable"),
    ("계약취소 손해배상 청구", "계약취소로 인한 손해배상 청구를 받았습니다.", "unfavorable"),

    # ── 중립 (neutral) ────────────────────────────────────────────────────────
    ("대표이사 변경 공시", "대표이사가 변경되었습니다.", "neutral"),
    ("본사 이전 결정", "본사 사무실 이전을 결정했습니다.", "neutral"),
    ("사업보고서 제출", "2024년 사업보고서를 제출하였습니다.", "neutral"),
    ("분기 실적 발표 예고", "3분기 실적 발표 일정을 공고합니다.", "neutral"),
    ("주주총회 소집 공고", "2025년 정기 주주총회를 소집합니다.", "neutral"),
    ("임원 변경 등기", "이사회 구성원 변경에 따른 등기를 완료했습니다.", "neutral"),
    ("자회사 설립 결정", "100% 자회사 설립을 결정했습니다.", "neutral"),
    ("5% 이상 주주 변동", "5% 이상 주주의 보유 주식 변동을 신고합니다.", "neutral"),
    ("협력협약 체결 소규모", "소규모 협력협약을 체결하였습니다.", "neutral"),
    ("전환청구 완료", "전환사채의 전환 청구가 완료되었습니다.", "neutral"),
    ("채무 조기 상환", "회사채 조기 상환을 완료하였습니다.", "neutral"),
    ("3분기 실적 컨센서스 부합", "시장 전망치에 부합하는 실적을 기록하였습니다.", "neutral"),
    ("주식 액면분할 결정", "1주당 5주로 주식 액면분할을 결정했습니다.", "neutral"),
    ("감사위원회 위원 선임", "감사위원회 위원 선임을 의결했습니다.", "neutral"),
    ("ESG 보고서 발간", "2024 ESG 보고서를 발간합니다.", "neutral"),
    ("공장 증설 계획 발표", "생산 능력 확대를 위한 공장 증설을 검토하겠습니다.", "neutral"),
    ("분할 합병 계획 발표", "자회사 분할 합병 절차를 진행할 예정입니다.", "neutral"),
    ("MOU 중소업체", "중소기업과 MOU를 체결하여 협력을 강화합니다.", "neutral"),

    # ── 엣지 케이스 ─────────────────────────────────────────────────────────
    ("계약 취소 — 당초 공급계약 해지", "공급 차질로 인해 계약 취소를 통보받았습니다.", "unfavorable"),
    ("손실에서 회복 전환 성공", "누적 손실에서 회복하여 흑자전환에 성공했습니다.", "favorable"),
]


@pytest.mark.parametrize("title,content,expected", TEST_CASES)
def test_classification(title: str, content: str, expected: str):
    result = clf.classify(title=title, content=content)
    actual = result["category"]
    assert actual == expected, (
        f"\n제목: {title!r}\n"
        f"기대: {expected}, 실제: {actual}, 점수: {result['sentiment_score']:.3f}"
    )


def test_accuracy_threshold():
    """전체 정확도 85% 이상인지 확인."""
    correct = 0
    errors  = []

    for title, content, expected in TEST_CASES:
        result = clf.classify(title=title, content=content)
        actual = result["category"]
        if actual == expected:
            correct += 1
        else:
            errors.append({
                "title":    title,
                "expected": expected,
                "actual":   actual,
                "score":    result["sentiment_score"],
                "keywords": result.get("keywords", []),
            })

    total    = len(TEST_CASES)
    accuracy = correct / total

    # 클래스별 분석
    by_class: dict[str, dict] = {}
    for title, content, expected in TEST_CASES:
        result = clf.classify(title=title, content=content)
        actual = result["category"]
        cls = by_class.setdefault(expected, {"tp": 0, "fp": 0, "fn": 0})
        if actual == expected:
            cls["tp"] += 1
        else:
            cls["fn"] += 1
            by_class.setdefault(actual, {"tp": 0, "fp": 0, "fn": 0})["fp"] += 1

    print(f"\n{'='*60}")
    print(f"공시 분류 정확도 결과")
    print(f"{'='*60}")
    print(f"전체: {correct}/{total} = {accuracy:.1%}")

    for cls_name, counts in by_class.items():
        tp = counts["tp"]
        fp = counts.get("fp", 0)
        fn = counts.get("fn", 0)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall    = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        print(f"  {cls_name:12s}: P={precision:.2f} R={recall:.2f} F1={f1:.2f}")

    if errors:
        print(f"\n오분류 {len(errors)}건:")
        for e in errors[:10]:
            print(f"  [{e['expected']}→{e['actual']}] {e['title']!r} (score={e['score']:.3f})")

    print(f"{'='*60}\n")

    assert accuracy >= 0.85, (
        f"정확도 {accuracy:.1%} < 목표 85%\n"
        f"오분류 사례:\n" + "\n".join(
            f"  {e['title']} (기대: {e['expected']}, 실제: {e['actual']}, 점수: {e['score']:.3f})"
            for e in errors
        )
    )


if __name__ == "__main__":
    correct = sum(
        1 for t, c, e in TEST_CASES
        if clf.classify(title=t, content=c)["category"] == e
    )
    print(f"정확도: {correct}/{len(TEST_CASES)} = {correct/len(TEST_CASES):.1%}")

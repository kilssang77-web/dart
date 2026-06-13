import logging
import re
import httpx
from datetime import datetime, timedelta
from tenacity import retry, stop_after_attempt, wait_exponential

try:
    from bs4 import BeautifulSoup
    _BS4_AVAILABLE = True
except ImportError:
    _BS4_AVAILABLE = False

logger = logging.getLogger(__name__)

# 가중치 기반 호재 키워드 (score += weight, 최대 1.0 클립)
FAVORABLE_WEIGHTS: dict[str, float] = {
    # 고가중 호재
    "FDA승인": 0.90, "임상성공": 0.85, "임상3상성공": 0.90,
    "흑자전환": 0.80, "어닝서프라이즈": 0.80,
    # 계약/수주
    "공급계약": 0.70, "수주": 0.65, "장기공급계약": 0.75,
    "기술수출": 0.75, "기술이전": 0.70, "독점계약": 0.75,
    "특허등록": 0.60, "특허취득": 0.60, "특허출원": 0.35,
    # 자사주
    "자기주식취득": 0.65, "자사주매입": 0.65, "자기주식소각": 0.70,
    # 성장
    "신사업": 0.40, "신제품": 0.40, "시판승인": 0.60,
    "MOU": 0.30, "업무협약": 0.28, "전략적제휴": 0.35, "협력협약": 0.28,
    "정부과제": 0.45, "국책사업": 0.50, "과제선정": 0.45,
    "실적개선": 0.40, "실적호전": 0.45, "영업이익증가": 0.50,
    "IPO": 0.35, "코스닥상장": 0.40, "코스피상장": 0.40,
    "합병": 0.30, "인수": 0.30,
    # 저가중
    "R&D": 0.20, "과제수주": 0.35, "수출": 0.20,
}

# 가중치 기반 악재 키워드 (score += weight, 최소 -1.0 클립)
UNFAVORABLE_WEIGHTS: dict[str, float] = {
    # 최고위험
    "횡령": -0.90, "배임": -0.90, "상장폐지": -0.95, "파산": -0.90,
    "부도": -0.90, "자본잠식": -0.85, "의견거절": -0.85,
    # 고위험
    "관리종목": -0.80, "거래정지": -0.75, "투자주의": -0.65,
    "감사의견": -0.60, "한정의견": -0.70, "부적정": -0.75,
    "소송패소": -0.65, "영업정지": -0.70, "사업취소": -0.60,
    "대규모손실": -0.70, "손실": -0.30,
    # 희석
    "유상증자": -0.55, "주주배정": -0.45, "일반공모증자": -0.50,
    "제3자배정": -0.50, "전환사채": -0.45, "CB발행": -0.50,
    "신주인수권부사채": -0.45, "BW발행": -0.50,
    "전환청구": -0.35, "주식전환": -0.35, "전환권행사": -0.40,
    # 지배구조
    "최대주주변경": -0.40, "대주주변경": -0.40, "경영권변경": -0.35,
    # 저위험
    "계약해지": -0.50, "부채급증": -0.45,
    "사기": -0.60, "고발": -0.50, "피의자": -0.55,
}

# 하위호환 목록 (기존 코드에서 직접 참조하는 경우 대비)
FAVORABLE_KEYWORDS = list(FAVORABLE_WEIGHTS.keys())
UNFAVORABLE_KEYWORDS = list(UNFAVORABLE_WEIGHTS.keys())


class DARTClient:
    BASE_URL = "https://opendart.fss.or.kr/api"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = httpx.AsyncClient(timeout=30)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20))
    async def get_recent_disclosures(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        page: int = 1,
    ) -> dict:
        if not start_date:
            start_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y%m%d")

        resp = await self._client.get(
            f"{self.BASE_URL}/list.json",
            params={
                "crtfc_key": self.api_key,
                "bgn_de": start_date,
                "end_de": end_date,
                "last_reprt_at": "Y",
                "page_no": page,
                "page_count": 100,
            },
        )
        resp.raise_for_status()
        return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20))
    async def get_disclosure_detail(self, rcept_no: str) -> dict:
        resp = await self._client.get(
            f"{self.BASE_URL}/document.json",
            params={"crtfc_key": self.api_key, "rcept_no": rcept_no},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_disclosure_body(self, rcept_no: str, max_chars: int = 2000) -> str:
        """DART 공시 본문 텍스트 추출 (HTML 파싱). 실패 시 빈 문자열."""
        if not _BS4_AVAILABLE:
            return ""
        url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
        try:
            resp = await self._client.get(url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            # iframe src 추출 → 실제 본문 문서 URL
            iframe = soup.find("iframe", {"id": "ifrm"}) or soup.find("iframe")
            if iframe and iframe.get("src"):
                doc_url = iframe["src"]
                if not doc_url.startswith("http"):
                    doc_url = "https://dart.fss.or.kr" + doc_url
                try:
                    doc_resp = await self._client.get(doc_url, timeout=15)
                    doc_resp.raise_for_status()
                    soup = BeautifulSoup(doc_resp.text, "html.parser")
                except Exception:
                    pass  # iframe 실패 시 메인 페이지 텍스트 사용

            for tag in soup(["script", "style", "head", "nav", "header", "footer"]):
                tag.decompose()
            text = re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True))
            return text[:max_chars]
        except Exception as e:
            logger.debug(f"Disclosure body fetch error {rcept_no}: {e}")
            return ""

    def extract_contract_amount(self, title: str, body: str = "") -> int | None:
        """제목/본문에서 계약 금액 추출 (원 단위 정수 반환)."""
        text = (title + " " + (body or "")[:1000])
        amounts: list[int] = []

        # '수주금액', '계약금액', '거래금액' 등 특정 컨텍스트 연소 우선
        context_area = text
        for ctx_kw in ["수주금액", "계약금액", "거래금액", "계약규모", "기술료"]:
            idx = text.find(ctx_kw)
            if idx >= 0:
                context_area = text[idx: idx + 80]
                break

        patterns: list[tuple[str, float]] = [
            (r"(\d[\d,]*)\s*조\s*원",           1_000_000_000_000),
            (r"(\d[\d,]*)\s*청억\s*원",      100_000_000_000),
            (r"(\d[\d,]*)\s*백억\s*원",      10_000_000_000),
            (r"(\d[\d,]*)\s*십억\s*원",      1_000_000_000),
            (r"(\d[\d,]*)\s*억\s*원",            100_000_000),
            (r"(\d[\d,]*)\s*백만\s*원",      1_000_000),
            (r"(\d[\d,]*)\s*만\s*원",            10_000),
        ]
        for pat, multiplier in patterns:
            for m in re.findall(pat, context_area):
                try:
                    amounts.append(int(int(m.replace(",", "")) * multiplier))
                except (ValueError, AttributeError):
                    pass

        return max(amounts) if amounts else None

    def classify(self, title: str, body: str = "") -> tuple[str, float]:
        """
        가중치 기반 감성 분류.
        호재·악재 키워드가 다수 발견되면 합산 스코어로 중립 비율 감소.
        score > 0.3 → favorable, score < -0.3 → unfavorable, else neutral
        """
        text = (title + " " + (body or "")[:600]).strip()
        fav_score = 0.0
        unf_score = 0.0

        for kw, w in FAVORABLE_WEIGHTS.items():
            if kw in text:
                fav_score = max(fav_score, w)

        for kw, w in UNFAVORABLE_WEIGHTS.items():
            if kw in text:
                unf_score = min(unf_score, w)  # w는 음수

        # 복합 문서: 호재와 악재가 함께 있으면 순합산
        if fav_score > 0 and unf_score < 0:
            score = round(fav_score + unf_score, 3)
        elif fav_score > 0:
            score = round(fav_score, 3)
        else:
            score = round(unf_score, 3)

        score = max(-1.0, min(1.0, score))

        if score > 0.3:
            return "favorable", score
        elif score < -0.3:
            return "unfavorable", score
        else:
            return "neutral", score

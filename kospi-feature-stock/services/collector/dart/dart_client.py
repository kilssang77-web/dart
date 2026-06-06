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

FAVORABLE_KEYWORDS = [
    "공급계약", "수주", "MOU", "업무협약", "협력협약", "전략적제휴",
    "특허등록", "특허취득", "기술이전", "기술수출", "기술계약",
    "정부과제", "국책사업", "R&D", "과제선정", "과제수주",
    "흑자전환", "실적개선", "실적호전", "영업이익증가",
    "자기주식취득", "자사주매입", "자기주식소각",
    "IPO", "상장예비심사", "코스닥상장", "코스피상장",
    "신사업", "신제품", "시판승인", "임상성공", "FDA승인",
]

UNFAVORABLE_KEYWORDS = [
    "전환사채", "CB발행", "신주인수권부사채", "BW발행",
    "유상증자", "주주배정", "일반공모증자", "제3자배정",
    "전환청구", "주식전환", "전환권행사",
    "최대주주변경", "대주주변경", "경영권변경",
    "횡령", "배임", "사기", "고발", "피의자",
    "관리종목", "상장폐지", "거래정지", "투자주의",
    "감사의견", "한정의견", "부적정", "의견거절",
    "영업정지", "사업취소", "계약해지", "소송패소",
    "대규모손실", "자본잠식", "부채급증",
]


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

    def classify(self, title: str) -> tuple[str, float]:
        for kw in FAVORABLE_KEYWORDS:
            if kw in title:
                return "favorable", 0.7
        for kw in UNFAVORABLE_KEYWORDS:
            if kw in title:
                return "unfavorable", -0.7
        return "neutral", 0.0

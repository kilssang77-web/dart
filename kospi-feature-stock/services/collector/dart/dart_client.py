import logging
import httpx
from datetime import datetime, timedelta
from tenacity import retry, stop_after_attempt, wait_exponential

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

    def classify(self, title: str) -> tuple[str, float]:
        for kw in FAVORABLE_KEYWORDS:
            if kw in title:
                return "favorable", 0.7
        for kw in UNFAVORABLE_KEYWORDS:
            if kw in title:
                return "unfavorable", -0.7
        return "neutral", 0.0

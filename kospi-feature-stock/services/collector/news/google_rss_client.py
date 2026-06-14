"""
Google News RSS 클라이언트 (인증 불필요).
URL 형식: https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko
반환 link는 Google redirect URL을 그대로 사용 (실제 URL 리다이렉트 추적 불필요).
"""
import logging
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

_RSS_BASE = "https://news.google.com/rss/search"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def _parse_rss_date(pub_date: str) -> str:
    """RSS pubDate (RFC 2822) → ISO 8601.

    예: 'Mon, 20 Nov 2023 10:00:00 GMT' → '2023-11-20T10:00:00+00:00'
    파싱 실패 시 현재 KST 시각 반환.
    """
    try:
        return parsedate_to_datetime(pub_date).isoformat()
    except Exception:
        return datetime.now(KST).isoformat()


class GoogleNewsRSS:
    """인증 불필요 Google News RSS 피드 클라이언트.

    Google News RSS는 별도 API 키 없이 사용 가능.
    반환 URL은 Google 리다이렉트 URL이며 실제 원문 URL 추적은 수행하지 않음.
    """

    async def get_news(self, query: str, max_items: int = 10) -> list[dict]:
        """Google News RSS에서 뉴스 기사 목록 반환.

        Args:
            query:     검색어 (종목명 또는 키워드)
            max_items: 반환할 최대 기사 수

        Returns:
            list of dict — 각 항목:
            {
                "title":        str,        # 기사 제목
                "url":          str,        # Google 리다이렉트 URL
                "published_at": str,        # ISO 8601 날짜 문자열
                "description":  str,        # 기사 요약 (없으면 빈 문자열)
                "source":       "google_rss"
            }
        """
        url = f"{_RSS_BASE}?q={quote(query)}&hl=ko&gl=KR&ceid=KR:ko"

        try:
            async with httpx.AsyncClient(
                timeout=10.0,
                follow_redirects=True,
                headers=_HEADERS,
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                xml_text = resp.text
        except httpx.HTTPStatusError as e:
            logger.warning(
                f"[GoogleNewsRSS] HTTP 오류 {e.response.status_code} "
                f"(query={query!r}): {e}"
            )
            return []
        except Exception as e:
            logger.warning(f"[GoogleNewsRSS] 요청 실패 (query={query!r}): {e}")
            return []

        try:
            soup = BeautifulSoup(xml_text, "xml")
        except Exception:
            # lxml-xml 파서가 없는 경우 html.parser 로 폴백
            soup = BeautifulSoup(xml_text, "html.parser")

        items = []
        for item_tag in soup.find_all("item")[:max_items]:
            title_tag = item_tag.find("title")
            link_tag  = item_tag.find("link")
            date_tag  = item_tag.find("pubDate")

            # <source> 태그 — 있으면 미디어 이름
            source_tag = item_tag.find("source")

            title = title_tag.get_text(strip=True) if title_tag else ""
            # Google RSS <link> 는 태그 사이 텍스트가 아닌 다음 형제 노드에 URL이 있는 경우가 있음
            if link_tag:
                link_url = link_tag.get_text(strip=True)
                # BeautifulSoup html.parser 는 <link> 를 self-closing 으로 처리할 수 있음
                if not link_url:
                    # NavigableString 형제에서 추출
                    sib = link_tag.next_sibling
                    link_url = str(sib).strip() if sib else ""
            else:
                link_url = ""

            pub_date = _parse_rss_date(date_tag.get_text(strip=True) if date_tag else "")

            # description — Google RSS 는 종종 없음
            desc_tag = item_tag.find("description")
            description = desc_tag.get_text(strip=True) if desc_tag else ""

            if not title or not link_url:
                continue

            items.append({
                "title":        title,
                "url":          link_url,
                "published_at": pub_date,
                "description":  description,
                "source":       "google_rss",
            })

        logger.debug(f"[GoogleNewsRSS] {query!r} → {len(items)}건")
        return items

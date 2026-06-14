"""
Naver 공식 검색 API 클라이언트.
무료 할당: 25,000건/일. 인증 헤더(X-Naver-Client-Id / X-Naver-Client-Secret) 사용.
환경변수: NAVER_CLIENT_ID, NAVER_CLIENT_SECRET
"""
import logging
import os
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

import httpx

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


def _parse_naver_date(pub_date: str) -> str:
    """pubDate RFC 2822 형식 → ISO 8601 문자열.

    예: 'Mon, 20 Nov 2023 10:00:00 +0900' → '2023-11-20T10:00:00+09:00'
    파싱 실패 시 현재 KST 시각 반환.
    """
    try:
        dt = parsedate_to_datetime(pub_date)
        return dt.isoformat()
    except Exception:
        return datetime.now(KST).isoformat()


def _strip_html(text: str) -> str:
    """Naver API description 필드에 포함된 <b> 태그 등 제거."""
    import re
    return re.sub(r"<[^>]+>", "", text).strip()


class NaverNewsAPI:
    """Naver 공식 뉴스 검색 API.

    사용 전 환경변수 설정 필요:
        NAVER_CLIENT_ID     — 네이버 개발자 센터에서 발급
        NAVER_CLIENT_SECRET — 네이버 개발자 센터에서 발급
    """

    BASE = "https://openapi.naver.com/v1/search/news.json"

    def __init__(self) -> None:
        self.client_id = os.getenv("NAVER_CLIENT_ID", "")
        self.client_secret = os.getenv("NAVER_CLIENT_SECRET", "")

    @property
    def available(self) -> bool:
        """클라이언트 ID/시크릿이 모두 설정된 경우에만 True."""
        return bool(self.client_id and self.client_secret)

    async def search(self, query: str, display: int = 10) -> list[dict]:
        """뉴스 검색 결과 반환.

        Args:
            query:   검색어 (종목명 또는 키워드)
            display: 반환할 최대 기사 수 (최대 100)

        Returns:
            list of dict — 각 항목:
            {
                "title":        str,       # 기사 제목 (HTML 태그 제거됨)
                "url":          str,       # 원문 URL
                "published_at": str,       # ISO 8601 날짜 문자열
                "description":  str,       # 기사 요약 (HTML 태그 제거됨)
                "source":       "naver_api"
            }
        """
        if not self.available:
            logger.debug("[NaverNewsAPI] 자격증명 미설정 — 스킵")
            return []

        headers = {
            "X-Naver-Client-Id":     self.client_id,
            "X-Naver-Client-Secret": self.client_secret,
        }
        params = {
            "query":   query,
            "display": min(display, 100),
            "sort":    "date",   # 최신순
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(self.BASE, headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning(
                f"[NaverNewsAPI] HTTP 오류 {e.response.status_code} "
                f"(query={query!r}): {e}"
            )
            return []
        except Exception as e:
            logger.warning(f"[NaverNewsAPI] 요청 실패 (query={query!r}): {e}")
            return []

        items = []
        for raw in data.get("items", []):
            title = _strip_html(raw.get("title", ""))
            desc  = _strip_html(raw.get("description", ""))
            url   = raw.get("originallink") or raw.get("link", "")
            pub   = _parse_naver_date(raw.get("pubDate", ""))

            if not title or not url:
                continue

            items.append({
                "title":        title,
                "url":          url,
                "published_at": pub,
                "description":  desc,
                "source":       "naver_api",
            })

        logger.debug(f"[NaverNewsAPI] {query!r} → {len(items)}건")
        return items

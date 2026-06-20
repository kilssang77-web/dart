-- 뉴스 URL 중복 제거 및 UNIQUE 제약 추가
-- url이 같은 뉴스 중 id가 가장 작은(최초 수집) 건만 남기고 나머지 삭제

DELETE FROM news
WHERE id NOT IN (
    SELECT MIN(id)
    FROM news
    WHERE url IS NOT NULL
    GROUP BY url
)
AND url IS NOT NULL;

-- UNIQUE 인덱스 추가 (NULL url은 UNIQUE 대상 제외 — PostgreSQL 기본 동작)
CREATE UNIQUE INDEX IF NOT EXISTS idx_news_url_unique ON news(url)
WHERE url IS NOT NULL;

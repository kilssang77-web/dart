---
description: 현재 MCP 설정을 보여주고 추천·추가·제거를 도와줍니다
---

신규 `/a2m_mcp` 명령입니다.
`.mcp.json`의 MCP 서버 설정을 관리합니다.

---

## Step 1 — 현황 표시

`.mcp.json`을 열어 현재 설정을 카테고리별로 따로 정리하라.

**활성 MCP:**

| 이름 | 용도 |
|------|------|
| filesystem | 파일 시스템 접근 |
| git | Git 조작 |
| sequential-thinking | 추론 보조 |
| context7 | 라이브러리 문서 조회 |
| fetch | URL 콘텐츠 조회 |
| memory | 세션 메모리 |

**비활성 MCP** (`_disabled_mcpServers` 항목을 따로 출력하되, 필요 환경변수가 있는 항목은 현재 환경변수 설정 여부를 확인):

| 이름 | 카테고리 | 용도 | 필요 환경변수 | 충족 |
|------|---------|------|-------------|------|
| playwright | 브라우저 | E2E/브라우저 | 없음 | ✅ |
| postgres | DB | PostgreSQL | DATABASE_URL | {확인} |
| mysql | DB | MySQL/MariaDB | MYSQL_HOST 등 | {확인} |
| ... | ... | ... | ... | ... |

환경변수 충족 여부는 `echo $ENV_VAR_NAME`으로 확인하라.

---

## Step 2 — 추천 카탈로그

아래 추천 MCP 목록을 카테고리별로 보여주고 추가 여부를 선택하게 하라:

| 카테고리 | 이름 | 용도 | 필요 환경변수 |
|---------|------|------|-------------|
| 브라우저 | playwright | E2E·DOM 디버깅 | 없음 |
| 브라우저 | chrome-devtools | 네트워크·콘솔 분석 | 없음 |
| RDBMS | postgres | PostgreSQL 스키마·쿼리 | DATABASE_URL |
| RDBMS | mysql | MySQL / MariaDB 스키마·쿼리 | MYSQL_HOST 등 |
| RDBMS | oracle | Oracle DB 스키마·쿼리 | ORACLE_CONNECTION_STRING 등 |
| NoSQL | mongodb | MongoDB 컬렉션·집계 | MONGODB_URI |
| NoSQL | redis | Redis 키 조회·캐시 디버깅 | REDIS_URL |
| NoSQL | elasticsearch | Elasticsearch 인덱스·검색 | ELASTICSEARCH_URL 등 |
| VCS | gitlab | GitLab MR·이슈·CI | GITLAB_TOKEN |
| VCS | github | GitHub PR·이슈 | GITHUB_TOKEN |
| 프로젝트 관리 | jira-confluence | Jira 이슈 + Confluence 페이지 | ATLASSIAN_API_TOKEN 등 |
| 프로젝트 관리 | notion | Notion 페이지·DB | NOTION_API_KEY |
| 프로젝트 관리 | linear | Linear 이슈·타임라인 | LINEAR_API_KEY |
| 커뮤니케이션 | slack | Slack 메시지·채널 | SLACK_BOT_TOKEN |
| 커뮤니케이션 | mattermost | Mattermost 메시지·채널 | MATTERMOST_URL, MATTERMOST_TOKEN |
| 커뮤니케이션 | discord | Discord 메시지·채널 | DISCORD_BOT_TOKEN |
| 커뮤니케이션 | teams | Microsoft Teams 메시지 | TEAMS_WEBHOOK_URL |
| 모니터링 | sentry | 오류·성능 이슈 조회 | SENTRY_AUTH_TOKEN |
| 모니터링 | datadog | 메트릭·로그·APM | DATADOG_API_KEY 등 |

> 같은 DB에 여러 역할을 연결하는 경우 이름을 `postgres-main`, `postgres-replica` 등으로 구분하여 항목을 복제하고 각각 다른 환경변수를 사용하세요. 세부 방법은 `.harness/docs/MCP_GUIDE.md` 참고.

---

## Step 3 — 활성화 및 비활성화

사용자가 항목을 선택하면:

**활성화 시**:
1. `.mcp.json`의 `_disabled_mcpServers`에서 `mcpServers`로 이동
2. 필요한 환경변수가 없으면 설정 방법 안내:
   ```bash
   # .env 파일에 추가 (Claude Code가 자동으로 읽음)
   GITLAB_TOKEN=your-token-here
   ```
3. 설치 명령 안내:
   ```bash
   # 패키지 설치 확인
   npx <패키지명> --version
   ```

**비활성화 시**:
1. `.mcp.json`의 `mcpServers`에서 `_disabled_mcpServers`로 이동 (내용 삭제 아님)

---

## Step 4 — 커스텀 MCP 추가

> "추가하고 싶은 MCP 서버가 있나요?
> 이름, 설치 명령(command + args), 필요한 환경변수를 알려주세요."

입력받아 사용자로 `.mcp.json`의 `mcpServers`에 추가.

---

## Step 5 — 파일 저장 및 재시작 안내

설정된 `.mcp.json`을 저장하며:
> "MCP 설정이 업데이트되었습니다.
> 변경사항을 적용하려면 Claude Code를 재시작하거나 `/restart`를 실행하세요.
> 세부 가이드: .harness/docs/MCP_GUIDE.md"

---

## MCP JSON 형식 참고

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/allowed/dir"]
    },
    "gitlab": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-gitlab"],
      "env": { "GITLAB_TOKEN": "${GITLAB_TOKEN}" }
    }
  },
  "_disabled_mcpServers": {
    "postgres": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres"],
      "env": { "DATABASE_URL": "${DATABASE_URL}" }
    }
  }
}
```

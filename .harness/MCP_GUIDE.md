# MCP 가이드

> Claude Code는 `.mcp.json`의 MCP(Model Context Protocol) 서버를 통해 파일 시스템, Git, DB, 이슈 트래커, 메시지 도구 등 외부 시스템과 상호작용합니다.
> 이 문서는 각 MCP의 용도와 설정 방법을 설명합니다.

---

## 기본 활성 MCP

프로젝트 시작 시 자동 활성화되어 있습니다. 별도 설정이 필요 없습니다.

| 이름 | 용도 |
|------|------|
| `filesystem` | 로컬 파일 읽기·쓰기 |
| `git` | git 명령 실행 (status, diff, log, commit 등) |
| `sequential-thinking` | 복잡한 문제를 단계별로 구조화해 추론 품질 향상 |
| `context7` | Spring Boot, React 등 라이브러리 최신 공식 문서 실시간 조회 |
| `fetch` | URL에서 HTML/마크다운 콘텐츠 가져오기 |
| `memory` | 세션 간 정보(결정사항, 선호 등)를 Key-Value로 기억 |

---

## 선택 MCP (필요 시 활성화)

`.mcp.json`의 `_disabled_mcpServers` 섹션에서 `mcpServers` 섹션으로 이동하면 활성화됩니다.
`/a2m_mcp` 명령으로 대화형으로 설정할 수도 있습니다.

---

### 브라우저 / 테스트

#### playwright
- **용도**: 브라우저 자동화, E2E 테스트, 스크린샷, 폼 조작
- **패키지**: `@playwright/mcp`
- **추가 설치**: `npx playwright install` (브라우저 바이너리 다운로드)
- **활성화 시점**: E2E 테스트 작성, UI 자동 검증 시

#### chrome-devtools
- **용도**: Chrome DevTools 직접 접근, 네트워크 요청 분석, 콘솔 로그 확인
- **패키지**: `@modelcontextprotocol/server-chrome`
- **필요 조건**: Chrome 설치

---

### 데이터베이스

> 같은 DBMS를 두 개 이상 연결할 때는 키 이름으로 구분합니다.
>
> ```json
> "postgres-main":      { "env": { "DATABASE_URL": "${DATABASE_URL_MAIN}" } },
> "postgres-analytics": { "env": { "DATABASE_URL": "${DATABASE_URL_ANALYTICS}" } }
> ```
>
> `.env` 파일에도 각각 다른 이름으로 등록합니다:
> ```bash
> DATABASE_URL_MAIN=postgresql://user:pass@main-db:5432/board
> DATABASE_URL_ANALYTICS=postgresql://user:pass@analytics-db:5432/stats
> ```

#### postgres
- **용도**: PostgreSQL 스키마 조회, 쿼리 실행 (공식 MCP)
- **패키지**: `@modelcontextprotocol/server-postgres`
- **환경변수**: `DATABASE_URL` — `postgresql://user:pass@localhost:5432/dbname`
- **주의**: 운영 DB는 읽기 전용 계정 사용 권장

#### mysql
- **용도**: MySQL / MariaDB 스키마 조회, 쿼리 실행. MariaDB는 MySQL 호환이므로 동일 패키지 사용 가능
- **패키지**: `@benborla29/mcp-server-mysql`
- **환경변수**:
  ```bash
  MYSQL_HOST=localhost
  MYSQL_PORT=3306
  MYSQL_USER=myuser
  MYSQL_PASS=mypassword
  MYSQL_DB=mydb
  ```

#### oracle
- **용도**: Oracle DB 스키마 조회, 쿼리 실행
- **패키지**: `@oracle/mcp-server-oracle` (Oracle 공식, 사용 전 최신 버전 확인 권장)
- **환경변수**:
  ```bash
  ORACLE_CONNECTION_STRING=localhost:1521/XEPDB1
  ORACLE_USER=myuser
  ORACLE_PASSWORD=mypassword
  ```

#### mongodb
- **용도**: MongoDB 컬렉션 조회, 집계 파이프라인 실행 (MongoDB 공식 MCP)
- **패키지**: `mongodb-mcp-server`
- **환경변수**: `MONGODB_URI` — `mongodb://user:pass@localhost:27017/mydb`

#### redis
- **용도**: Redis 키 조회·명령 실행. 캐시 내용 확인, Pub/Sub 디버깅
- **패키지**: `mcp-server-redis`
- **환경변수**: `REDIS_URL` — `redis://localhost:6379`

#### elasticsearch
- **용도**: Elasticsearch 인덱스 조회, 검색 쿼리 실행 (Elastic 공식 MCP)
- **패키지**: `@elastic/mcp-server-elasticsearch`
- **환경변수**:
  ```bash
  ELASTICSEARCH_URL=http://localhost:9200
  ELASTICSEARCH_API_KEY=your-api-key
  ```

---

### VCS / 코드 리뷰

#### gitlab
- **용도**: GitLab MR 생성·조회, 이슈 관리, CI 파이프라인 상태 확인 (공식 MCP)
- **패키지**: `@modelcontextprotocol/server-gitlab`
- **환경변수**:
  ```bash
  GITLAB_TOKEN=glpat-xxxx   # Personal Access Token, api 스코프
  GITLAB_URL=https://gitlab.example.com   # self-hosted인 경우
  ```

#### github
- **용도**: GitHub PR 생성·조회, 이슈 관리 (공식 MCP). GitLab 사용 시 gitlab으로 대체
- **패키지**: `@modelcontextprotocol/server-github`
- **환경변수**: `GITHUB_TOKEN` — Personal Access Token

---

### 프로젝트 관리

#### jira-confluence
- **용도**: Jira 이슈·스프린트 조회·생성, Confluence 페이지 읽기·쓰기. Atlassian Cloud와 Server(온프레미스) 모두 지원
- **패키지**: `mcp-atlassian` — **Python 환경 필요** (`pip install uv` 또는 `pip install mcp-atlassian`)
- **실행 방식**: `uvx mcp-atlassian` (npx 대신 uvx 사용)
- **환경변수**:
  ```bash
  JIRA_URL=https://mycompany.atlassian.net
  CONFLUENCE_URL=https://mycompany.atlassian.net/wiki
  ATLASSIAN_EMAIL=myname@company.com
  ATLASSIAN_API_TOKEN=xxxx   # Atlassian API Token
  ```

#### notion
- **용도**: Notion 페이지·데이터베이스 읽기·쓰기 (Notion 공식 MCP)
- **패키지**: `@notionhq/notion-mcp-server`
- **환경변수**: `NOTION_API_KEY` — Notion Integration Token (`https://www.notion.so/my-integrations`에서 생성)
- **주의**: 연동하려는 페이지/DB에 Integration을 연결(Share)해야 접근 가능

#### linear
- **용도**: Linear 이슈·프로젝트·사이클 조회 및 생성 (Linear 공식 MCP)
- **패키지**: `@linear/mcp-server`
- **환경변수**: `LINEAR_API_KEY` — `https://linear.app/settings/api`에서 생성

---

### 커뮤니케이션

#### slack
- **용도**: 메시지 전송, 채널 조회, 스레드 읽기 (공식 MCP)
- **패키지**: `@modelcontextprotocol/server-slack`
- **환경변수**:
  ```bash
  SLACK_BOT_TOKEN=xoxb-xxxx   # Bot Token, chat:write 스코프 필요
  SLACK_TEAM_ID=T0XXXXXXX
  ```
- **설정**: `https://api.slack.com/apps`에서 앱 생성 → Bot Token 발급

#### mattermost
- **용도**: Mattermost 메시지 전송·채널 조회. 사내 설치형 Mattermost에 적합
- **패키지**: `mcp-server-mattermost` (커뮤니티, 사용 전 최신 패키지명 확인 권장)
- **환경변수**:
  ```bash
  MATTERMOST_URL=https://mattermost.mycompany.com
  MATTERMOST_TOKEN=xxxx   # Personal Access Token 또는 Bot Token
  ```

#### discord
- **용도**: Discord 메시지 전송·채널 조회. 개발팀 Discord 서버 연동 시 유용
- **패키지**: `discord-mcp` (커뮤니티, 사용 전 최신 패키지명 확인 권장)
- **환경변수**: `DISCORD_BOT_TOKEN` — Discord Developer Portal에서 Bot 생성 후 발급
- **주의**: Bot을 서버에 초대하고 메시지 읽기 권한 부여 필요

#### teams
- **용도**: Microsoft Teams 채널에 메시지 전송. Incoming Webhook 방식
- **패키지**: `mcp-server-teams` (커뮤니티, 사용 전 최신 패키지명 확인 권장)
- **환경변수**: `TEAMS_WEBHOOK_URL` — Teams 채널 → 커넥터 → Incoming Webhook URL

---

### 모니터링 / 운영

#### sentry
- **용도**: Sentry 에러·성능 이슈 조회, 스택 트레이스 분석. 에러 원인 추적 시 유용 (공식 MCP)
- **패키지**: `@sentry/mcp-server`
- **환경변수**:
  ```bash
  SENTRY_AUTH_TOKEN=xxxx   # User Auth Token (project:read 스코프)
  SENTRY_ORG=myorg
  ```

#### datadog
- **용도**: Datadog 메트릭·로그·APM 데이터 조회. 운영 이상 분석 시 유용
- **패키지**: `mcp-server-datadog` (커뮤니티, 사용 전 최신 패키지명 확인 권장)
- **환경변수**:
  ```bash
  DATADOG_API_KEY=xxxx
  DATADOG_APP_KEY=xxxx
  DATADOG_SITE=datadoghq.com   # 또는 datadoghq.eu 등
  ```

---

## MCP 활성화 방법

### /a2m_mcp 명령으로 (권장)

Claude Code에서 `/a2m_mcp`를 실행하면 대화형으로 안내를 받을 수 있습니다.

### 직접 편집

1. `.mcp.json`에서 `_disabled_mcpServers`의 항목을 `mcpServers`로 이동
2. 필요한 환경변수를 `.env` 파일에 추가
3. Claude Code를 재시작

---

## 환경변수 설정

```bash
# 프로젝트 루트의 .env 파일에 추가 (Claude Code가 자동으로 읽음)
# .gitignore에 .env가 포함되어 있는지 반드시 확인

GITLAB_TOKEN=glpat-xxxxxxxxxxxx
DATABASE_URL=postgresql://user:pass@localhost:5432/board
SLACK_BOT_TOKEN=xoxb-xxxxxxxxxxxx
```

> `.env`는 절대 버전 관리에 커밋하지 마세요. `.gitignore`에 `.env`가 포함되어 있는지 확인하세요.

---

## 참고

- 커뮤니티 패키지로 표기된 항목은 패키지명이 변경될 수 있습니다. 활성화 전 npm/npx로 최신 버전을 확인하세요.
- `jira-confluence`는 Python 환경(`uvx`)이 필요합니다. Python이 없다면 먼저 설치가 필요합니다.
- 운영 DB 연결 시에는 반드시 읽기 전용 계정을 사용하세요.

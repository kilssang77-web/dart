# 배포 순서 가이드

> Phase 0 체크리스트 완료 후 아래 순서대로 진행하세요.

---

## Step 1 — Supabase 스키마 적용

1. https://supabase.com → 프로젝트 선택
2. 좌측 메뉴 → **SQL Editor**
3. `deploy/supabase/init_supabase.sql` 전체 내용 복사 → 붙여넣기 → **Run**
4. 완료 메시지 확인: `Quant Eye Supabase DB initialized successfully`

---

## Step 2 — GitHub Secrets 등록

Settings → Secrets and variables → Actions → New repository secret

```
필수 Secrets (16개):
────────────────────────────────────────────────────────────
POSTGRES_DSN          postgresql://postgres:[PW]@db.[ID].supabase.co:5432/postgres
REDIS_URL             rediss://default:[TOKEN]@[HOST].upstash.io:6379
KIS_APP_KEY           (한국투자증권 App Key)
KIS_APP_SECRET        (한국투자증권 App Secret)
KIS_ACCOUNT_NO        (한국투자증권 계좌번호 ex: 50123456-01)
KIS_BASE_URL          https://openapi.koreainvestment.com:9443
DART_API_KEY          (DART Open API 인증키)
TELEGRAM_TOKEN        (텔레그램 봇 토큰 — GitHub Actions·Fly.io collector 전용)
TELEGRAM_CHAT_ID      (텔레그램 채팅 ID)
DISCORD_WEBHOOK       https://discord.com/api/webhooks/xxx/xxx
HF_TOKEN              (HuggingFace Access Token)
HF_REPO_ID            username/quant-eye-ml
HF_ML_URL             https://username-quant-eye-ml.hf.space
R2_ACCOUNT_ID         (Cloudflare Account ID)
R2_ACCESS_KEY         (R2 API Access Key)
R2_SECRET_KEY         (R2 API Secret Key)
────────────────────────────────────────────────────────────
```

> ⚠️ `TELEGRAM_TOKEN`은 GitHub Actions / Fly.io 수집 데몬 전용입니다.
> API 서버는 별도로 `TELEGRAM_BOT_TOKEN`을 Fly.io secrets에 등록합니다 (Step 6).

---

## Step 3 — GitHub Actions 워크플로 복사

```powershell
# .github/workflows 디렉토리 생성 후 워크플로 파일 복사
New-Item -ItemType Directory -Force ".github\workflows"
Copy-Item "kospi-feature-stock\deploy\github-actions\*.yml" ".github\workflows\"
git add .github/workflows/
git commit -m "chore(ci): GitHub Actions 워크플로 추가"
git push
```

---

## Step 4 — HF Spaces ML 서비스 배포

1. https://huggingface.co → New Space
2. 설정:
   - **Space name**: `quant-eye-ml`
   - **SDK**: Docker
   - **Visibility**: Public (무료 16GB 사용 조건)
3. Space 생성 후 파일 업로드:
   ```bash
   # HuggingFace CLI 설치
   pip install huggingface_hub

   # 로그인
   huggingface-cli login

   # 파일 업로드
   python - <<'EOF'
   from huggingface_hub import HfApi
   api = HfApi()
   repo_id = "YOUR_USERNAME/quant-eye-ml"

   api.upload_file(
       path_or_fileobj="kospi-feature-stock/deploy/hf-spaces/Dockerfile",
       path_in_repo="Dockerfile",
       repo_id=repo_id, repo_type="space",
   )
   api.upload_file(
       path_or_fileobj="kospi-feature-stock/deploy/hf-spaces/app.py",
       path_in_repo="app.py",
       repo_id=repo_id, repo_type="space",
   )
   EOF
   ```
4. Space Variables 설정:
   - `POSTGRES_DSN` = Supabase DSN
   - `LGBM_MODEL_DIR` = `/app/models/lgbm`
   - `EMBEDDING_MODEL_NAME` = `jhgan/ko-sroberta-multitask`

---

## Step 5 — Fly.io 수집 데몬 배포

```powershell
# Fly.io 로그인
flyctl auth login

# 앱 생성 (최초 1회)
flyctl launch --config kospi-feature-stock\deploy\flyio\fly.toml --no-deploy

# Secrets 등록
flyctl secrets set `
  POSTGRES_DSN="postgresql://postgres:[PW]@db.[ID].supabase.co:5432/postgres" `
  REDIS_URL="rediss://default:[TOKEN]@[HOST].upstash.io:6379" `
  KIS_APP_KEY="..." `
  KIS_APP_SECRET="..." `
  KIS_ACCOUNT_NO="..." `
  KIS_BASE_URL="https://openapi.koreainvestment.com:9443" `
  DART_API_KEY="..." `
  API_URL="https://quant-eye-api.fly.dev" `
  TELEGRAM_TOKEN="..." `
  TELEGRAM_CHAT_ID="..."

# 배포
flyctl deploy --config kospi-feature-stock\deploy\flyio\fly.toml

# 상태 확인
flyctl status --config kospi-feature-stock\deploy\flyio\fly.toml

# 로그 실시간 확인
flyctl logs --config kospi-feature-stock\deploy\flyio\fly.toml
```

---

## Step 6 — Fly.io API 배포

> ℹ️ Render.com 750h/월 무료 한도는 g2b 시스템 전용으로 사용합니다.
> quant-eye API는 Fly.io 3번째 256MB VM에 배포합니다.

```powershell
# API 디렉토리로 이동
Set-Location kospi-feature-stock\services\api

# 앱 생성 (최초 1회 — 앱 이름은 quant-eye-api 로 고정)
flyctl launch --name quant-eye-api --no-deploy

# Secrets 등록
flyctl secrets set `
  POSTGRES_DSN="postgresql://postgres:[PW]@db.[ID].supabase.co:5432/postgres" `
  REDIS_URL="rediss://default:[TOKEN]@[HOST].upstash.io:6379" `
  ML_SERVICE_URL="https://[USERNAME]-quant-eye-ml.hf.space" `
  R2_ACCOUNT_ID="[Cloudflare Account ID]" `
  R2_ACCESS_KEY="[R2 API Access Key]" `
  R2_SECRET_KEY="[R2 API Secret Key]" `
  JWT_SECRET_KEY="[랜덤 32자 이상 문자열]" `
  DEFAULT_ADMIN_USERNAME="admin" `
  DEFAULT_ADMIN_PASSWORD="[강력한 비밀번호]" `
  DEFAULT_ADMIN_DISPLAY_NAME="관리자" `
  TELEGRAM_BOT_TOKEN="[텔레그램 봇 토큰]" `
  TELEGRAM_CHAT_ID="[텔레그램 채팅 ID]" `
  CORS_ORIGINS="https://quant-eye.pages.dev"

# 배포
flyctl deploy

# 상태 확인
flyctl status
flyctl logs
```

배포 완료 후 API URL: `https://quant-eye-api.fly.dev`

---

## Step 7 — Cloudflare Pages 프론트엔드 배포

1. Cloudflare Dashboard → Pages → Create a project
2. GitHub 연결 → 레포 선택
3. Build 설정:
   - Root directory: `kospi-feature-stock/frontend`
   - Build command: `npm run build`
   - Output: `dist`
4. Environment Variables:
   - `VITE_API_URL` = `https://quant-eye-api.fly.dev`
5. Save and Deploy

---

## Step 8 — UptimeRobot 설정

1. https://uptimerobot.com → Add New Monitor (2개)

| # | Type | Name | URL | Interval |
|---|---|---|---|---|
| 1 | HTTPS | Fly.io API | https://quant-eye-api.fly.dev/health | 5분 |
| 2 | HTTPS | HF Spaces ML | https://username-quant-eye-ml.hf.space/health | 5분 |

2. Alert Contacts → Add → Email 또는 Discord Webhook

---

## Step 9 — Discord 운영 알림 설정

1. Discord 서버 → 채널 설정 → Integrations → Webhooks → New Webhook
2. Webhook URL 복사 → GitHub Secrets `DISCORD_WEBHOOK`에 등록
3. GitHub Actions 실패 시 자동 Discord 알림 발송 (ml-retrain.yml, collector-daily.yml)

---

## Step 10 — R2 히스토리 데이터 내보내기 (최초 1회)

```powershell
# 필요 패키지 설치 (pyarrow 불필요 — JSON.gz 직접 생성)
pip install asyncpg pandas boto3 python-dotenv

# 환경변수 설정 (기존 로컬 TimescaleDB → Supabase 이전 전에 실행)
$env:POSTGRES_DSN   = "postgresql://stockuser:StrongPass123!@localhost:5432/feature_stock"
$env:R2_ACCOUNT_ID  = "..."
$env:R2_ACCESS_KEY  = "..."
$env:R2_SECRET_KEY  = "..."
$env:R2_BUCKET      = "quant-eye-history"

# 전체 이력 내보내기 (5년치, daily_bars 테이블)
# 출력 경로: daily_bars/{code}/{year}.json.gz
Set-Location kospi-feature-stock
python deploy/r2/export_to_r2.py --years 5
```

---

## 완료 후 확인 체크리스트

```
[ ] https://quant-eye.pages.dev 접속 → 로그인 화면 표시
[ ] admin 계정으로 로그인 성공
[ ] 대시보드에 종목 데이터 표시
[ ] UptimeRobot 모니터 2개 모두 UP 상태
[ ] Fly.io 수집 데몬 로그에서 "스캔 완료" 메시지 확인
[ ] Fly.io API /health 응답 200
[ ] Telegram으로 테스트 알림 수신
[ ] Discord에 GitHub Actions 실행 알림 수신
```

---

## Fly.io VM 배정 현황

| VM | 앱 이름 | 역할 | 메모리 |
|---|---|---|---|
| VM 1 | quant-eye-collector | KIS 실시간 수집 + 패턴 탐지 | 256MB |
| VM 2 | quant-eye-api | FastAPI REST API | 256MB |
| VM 3 | (g2b 시스템 전용) | — | 256MB |

---

## 서비스 URL 정리

| 서비스 | URL |
|---|---|
| 프론트엔드 | https://quant-eye.pages.dev |
| API 서버 | https://quant-eye-api.fly.dev |
| ML 서비스 | https://username-quant-eye-ml.hf.space |
| Fly.io 수집 데몬 | (내부 서비스, 외부 URL 없음) |
| Supabase | https://app.supabase.com |

---

## 환경변수 서비스별 배정 요약

| 변수 | GitHub Actions | Fly.io collector | Fly.io API |
|------|:--------------:|:----------------:|:----------:|
| POSTGRES_DSN | ✓ | ✓ | ✓ |
| REDIS_URL | ✓ | ✓ | ✓ |
| KIS_APP_KEY | ✓ | ✓ | — |
| KIS_APP_SECRET | ✓ | ✓ | — |
| KIS_ACCOUNT_NO | ✓ | ✓ | — |
| KIS_BASE_URL | ✓ | ✓ | — |
| DART_API_KEY | ✓ | ✓ | — |
| TELEGRAM_TOKEN | ✓ | ✓ | — |
| TELEGRAM_BOT_TOKEN | — | — | ✓ |
| TELEGRAM_CHAT_ID | ✓ | ✓ | ✓ |
| DISCORD_WEBHOOK | ✓ | — | — |
| HF_TOKEN | ✓ | — | — |
| HF_REPO_ID | ✓ | — | — |
| HF_ML_URL | ✓ | — | — |
| ML_SERVICE_URL | — | — | ✓ |
| R2_ACCOUNT_ID | — | — | ✓ |
| R2_ACCESS_KEY | — | — | ✓ |
| R2_SECRET_KEY | — | — | ✓ |
| JWT_SECRET_KEY | — | — | ✓ |
| DEFAULT_ADMIN_* | — | — | ✓ |
| CORS_ORIGINS | — | — | ✓ |
| API_URL | — | ✓ | — |

# Phase 0 — 사전 준비 체크리스트

> 이 파일의 모든 항목을 완료한 뒤 Phase 1(Supabase 적용)을 진행하세요.
> 각 항목 완료 시 [ ] → [x] 로 변경하세요.

---

## 1. 계정 생성 (8개 서비스)

| # | 서비스 | URL | 무료 플랜 | 신용카드 |
|---|---|---|---|---|
| [ ] | **Supabase** | https://supabase.com | 500MB PostgreSQL + pgvector | 불필요 |
| [ ] | **Cloudflare** | https://cloudflare.com | Pages + R2 10GB | 불필요 |
| [ ] | **Fly.io** | https://fly.io | 256MB VM 상시기동 | **필요** (청구 없음) |
| [ ] | **Render.com** | https://render.com | 512MB Web Service | 불필요 |
| [ ] | **Upstash** | https://upstash.com | Redis 10K cmd/일 | 불필요 |
| [ ] | **Hugging Face** | https://huggingface.co | Spaces Docker 16GB | 불필요 |
| [ ] | **UptimeRobot** | https://uptimerobot.com | 50 모니터, 5분 간격 | 불필요 |
| [ ] | **Discord** | https://discord.com | Webhook 무료 | 불필요 |

---

## 2. CLI 도구 설치

```powershell
# Fly.io CLI (flyctl)
winget install Flyio.flyctl

# Cloudflare CLI (wrangler)
npm install -g wrangler

# 설치 확인
flyctl version
wrangler --version
```

- [ ] flyctl 설치 완료
- [ ] wrangler 설치 완료

---

## 3. GitHub 레포지토리 준비

> GitHub Actions 무제한 분(minutes) 사용을 위해 **공개(Public) 레포**가 필요합니다.
> API 키는 코드에 포함되지 않으며 GitHub Secrets에만 저장됩니다.

```
현재: D:\a2m\atom-harness-base-Dart (Private 또는 Local)
목표: GitHub Public Repository로 push
```

**주의사항:**
- `.env` 파일이 `.gitignore`에 포함되어 있는지 확인
- `models/` 디렉토리 (ML 모델 파일)는 Git LFS 또는 별도 업로드 필요
- 민감 정보가 코드에 하드코딩되어 있지 않은지 확인

```bash
# .gitignore 필수 항목 확인
cat .gitignore | grep -E "\.env|models/"
```

- [ ] .gitignore에 .env 포함 확인
- [ ] .gitignore에 models/ 포함 확인
- [ ] GitHub Public 레포 생성 및 코드 push

---

## 4. 기존 환경변수 수집

> `.env` 파일에서 다음 값들을 별도 메모장에 복사해두세요.
> (Phase 3~7에서 각 서비스에 등록할 예정)

```
필수 수집 항목:
─────────────────────────────────────────
KIS_APP_KEY          = (한국투자증권 앱키)
KIS_APP_SECRET       = (한국투자증권 시크릿)
KIS_ACCOUNT_NO       = (계좌번호)
KIS_ACCOUNT_TYPE     = (계좌유형: 01)
KIS_BASE_URL         = https://openapi.koreainvestment.com:9443

DART_API_KEY         = (DART Open API 키)

TELEGRAM_TOKEN       = (텔레그램 봇 토큰)
TELEGRAM_CHAT_ID     = (텔레그램 채팅 ID)

DEFAULT_ADMIN_USERNAME   = (관리자 계정명)
DEFAULT_ADMIN_PASSWORD   = (관리자 비밀번호)
DEFAULT_ADMIN_DISPLAY_NAME = (관리자 표시명)

EMBEDDING_MODEL_NAME = jhgan/ko-sroberta-multitask
─────────────────────────────────────────
```

- [ ] 환경변수 목록 별도 저장 완료

---

## 5. ML 모델 파일 위치 확인

```powershell
# 모델 파일 존재 여부 확인
ls "D:\a2m\atom-harness-base-Dart\kospi-feature-stock\services\ml\models\lgbm\"
```

수집 필요 파일:
- [ ] `entry_model.lgb` 파일 위치 확인
- [ ] `risk_model.lgb` 파일 위치 확인
- [ ] `calibrators` 파일 위치 확인

---

## 6. Supabase 프로젝트 생성

1. https://supabase.com 로그인
2. "New Project" 클릭
3. 설정:
   - **Name**: `quant-eye`
   - **Database Password**: 강력한 비밀번호 설정 및 메모
   - **Region**: `Northeast Asia (Seoul)` 선택
4. 생성 후 다음 값 복사:

```
Project URL   : https://xxxxxxxxxxxx.supabase.co
anon key      : eyJhbGciO...
service_role  : eyJhbGciO...  (비공개, 서버에서만 사용)
Database URL  : postgresql://postgres:[PASSWORD]@db.xxxxxxxxxxxx.supabase.co:5432/postgres
```

- [ ] Supabase 프로젝트 생성 완료
- [ ] Project URL, anon key, Database URL 메모 완료

---

## 7. Cloudflare 설정

### 7-1. Pages 프로젝트 연결
1. Cloudflare Dashboard → Pages → "Create a project"
2. GitHub 연결 → `kospi-feature-stock/frontend` 선택
3. Build 설정:
   - Framework: `Vite`
   - Build command: `npm run build`
   - Build output: `dist`

### 7-2. R2 버킷 생성
1. Cloudflare Dashboard → R2 → "Create bucket"
2. Bucket name: `quant-eye-history`
3. Region: Automatic

```
R2 Bucket Name : quant-eye-history
Account ID     : (Dashboard 우측 상단)
R2 Access Key  : (R2 → Manage R2 API tokens → Create)
R2 Secret Key  : (위와 동일)
```

- [ ] R2 버킷 `quant-eye-history` 생성 완료
- [ ] R2 API Token 생성 및 메모

---

## 8. Upstash Redis 생성

1. https://upstash.com 로그인
2. "Create Database" → Redis
3. 설정:
   - **Name**: `quant-eye-cache`
   - **Region**: `ap-northeast-1 (Tokyo)` (한국과 가장 가까움)
   - **Type**: Regional (무료)

```
UPSTASH_REDIS_REST_URL : https://xxx.upstash.io
UPSTASH_REDIS_REST_TOKEN : AXxx...
REDIS_URL (for Python) : rediss://default:xxx@xxx.upstash.io:6379
```

- [ ] Upstash Redis 생성 완료
- [ ] REDIS_URL 메모 완료

---

## 완료 확인

모든 항목 완료 후 아래 정보가 준비되어 있는지 최종 확인:

```
[ ] Supabase Database URL
[ ] Cloudflare R2 Access Key + Secret + Bucket Name
[ ] Upstash REDIS_URL
[ ] KIS API Key/Secret/Account
[ ] DART API Key
[ ] Telegram Token + Chat ID
[ ] ML 모델 파일 위치
[ ] GitHub Public 레포 URL
```

**→ 모두 완료되면 Phase 1 진행 (Supabase 스키마 적용)**

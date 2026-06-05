# 프로젝트 구조

---

## 레포 전략

- 전략: 모노레포
- 이유: FastAPI 백엔드 + React 프론트엔드를 단일 저장소에서 관리. 배포·의존성 동기화 용이.
- 구성: `bid-system/backend/` + `bid-system/frontend/` + `.harness/` (하네스 런타임)

---

## 전체 디렉토리 트리

```
atom-harness-g2b/
├── bid-system/
│   ├── backend/
│   │   ├── app/
│   │   │   ├── api/v1/               # FastAPI 라우터 (비즈니스 로직 금지)
│   │   │   │   ├── auth.py           # 로그인, JWT 발급
│   │   │   │   ├── bids.py           # 공고 CRUD + 북마크
│   │   │   │   ├── recommend.py      # AI 추천 v1/v2 + 예가 분석
│   │   │   │   ├── statistics.py     # 대시보드 통계, 사정율 분포
│   │   │   │   ├── agencies.py       # 발주처 목록·분석
│   │   │   │   ├── competitors.py    # 경쟁사 분석·비교
│   │   │   │   ├── my_bids.py        # 내 투찰 이력·정확도
│   │   │   │   ├── admin.py          # 관리자 기능
│   │   │   │   ├── keywords.py       # 키워드 관리
│   │   │   │   └── router.py         # 라우터 통합 include
│   │   │   ├── ml/                   # ML 추론 엔진 (Router 직접 호출 금지)
│   │   │   │   ├── engine.py         # 하이브리드 앙상블 진입점
│   │   │   │   ├── assessment.py     # 사정율 예측 모델
│   │   │   │   ├── competition.py    # 낙찰확률 계산
│   │   │   │   ├── simulation.py     # Monte Carlo 시뮬레이션 (실증분포 지원)
│   │   │   │   ├── rank_model.py     # inpo21c 실증분포 기반 경쟁사 샘플링
│   │   │   │   ├── personal.py       # 사용자 투찰 편향 보정 엔진
│   │   │   │   └── yega.py           # 예가 빈도 분석 (Prism형)
│   │   │   ├── collector/            # 나라장터 수집 서브시스템 (mvp 단계 추가)
│   │   │   │   ├── client.py         # NarajangterClient (G2B OpenAPI, 재시도 3회)
│   │   │   │   ├── service.py        # collect_notices/collect_results (upsert)
│   │   │   │   ├── scheduler.py      # APScheduler (06:00 공고, 18:00 결과+연계, 월 02:00 inpo21c)
│   │   │   │   └── inpo21c.py        # inpo21c 전 참여자 스크래퍼 + 쿠키 유효성 검증
│   │   │   ├── common/
│   │   │   │   └── security.py       # JWT 인증, 권한 검사
│   │   │   ├── main.py               # FastAPI 앱 진입점, CORS, exception handler
│   │   │   ├── models.py             # SQLAlchemy ORM 모델
│   │   │   ├── schemas.py            # Pydantic Request/Response DTO
│   │   │   ├── services.py           # 비즈니스 로직 (DB commit/rollback 위치)
│   │   │   ├── database.py           # DB 연결, Session 팩토리
│   │   │   ├── config.py             # 환경변수 설정 (pydantic-settings)
│   │   │   └── seed.py               # 개발용 초기 데이터
│   │   ├── requirements.txt
│   │   └── .env                      # 비밀값 (gitignore, .env.example만 커밋)
│   │
│   └── frontend/
│       ├── src/
│       │   ├── api/
│       │   │   ├── client.ts         # axios 인스턴스 (baseURL, 인터셉터)
│       │   │   └── index.ts          # 도메인별 API 함수 모음
│       │   ├── components/
│       │   │   ├── ui/               # shadcn 컴포넌트 + 커스텀 시각화
│       │   │   │   ├── WinProbGauge.tsx
│       │   │   │   ├── StrategyCompareChart.tsx
│       │   │   │   ├── SrateRangeViz.tsx
│       │   │   │   └── RiskCard.tsx
│       │   │   └── layout/
│       │   │       └── AppLayout.tsx  # 사이드바 + 메인 레이아웃
│       │   ├── pages/                # 라우트 페이지 (URL 1:1)
│       │   │   ├── DashboardPage.tsx
│       │   │   ├── BidsPage.tsx
│       │   │   ├── BidDetailPage.tsx
│       │   │   ├── RecommendPage.tsx
│       │   │   ├── MyBidsPage.tsx
│       │   │   ├── StatisticsPage.tsx
│       │   │   ├── AgenciesPage.tsx
│       │   │   ├── AgencyDetailPage.tsx
│       │   │   ├── CompetitorPage.tsx
│       │   │   ├── JointBidPage.tsx
│       │   │   ├── QualificationPage.tsx
│       │   │   ├── YegaPage.tsx
│       │   │   ├── KeywordsPage.tsx
│       │   │   └── AdminPage.tsx
│       │   ├── store/
│       │   │   └── auth.ts           # Zustand 인증 상태 (user, token)
│       │   ├── types/
│       │   │   └── index.ts          # 전역 TypeScript 타입 정의 (any 금지)
│       │   ├── lib/utils.ts
│       │   ├── App.tsx               # React Router 라우팅
│       │   └── main.tsx              # React 진입점
│       ├── package.json
│       └── vite.config.ts
│
└── .harness/                         # 하네스 런타임 메타
    ├── docs/                         # 프로젝트 설계 문서
    ├── phases/                       # 실행 이력 (run별 step 관리)
    ├── release-notes/                # 릴리즈 노트
    ├── scripts/                      # 하네스 스크립트
    └── profile.json                  # 프로젝트 단계·기술스택 설정
```

---

## 빌드 · 실행 명령

### 사전 요구사항

- Python 3.12+
- Node.js 22+
- PostgreSQL 16+ (또는 Docker)

### Backend

```bash
# 의존성 설치
pip install -r requirements.txt

# 개발 서버 실행 (bid-system/backend/)
uvicorn app.main:app --reload --port 8000

# 테스트
pytest

# 린트
ruff check . && ruff format .
```

### Frontend

```bash
# 의존성 설치 (bid-system/frontend/)
npm install

# 개발 서버 실행
npm run dev

# 프로덕션 빌드
npm run build

# 린트
npm run lint
```

### Docker (로컬 인프라)

```bash
# PostgreSQL 실행
docker compose up -d

# 중지
docker compose down
```

---

## 환경변수

### Backend (`bid-system/backend/.env`)

| 변수 | 설명 | 예시값 |
|------|------|--------|
| `DATABASE_URL` | PostgreSQL 연결 URL | `postgresql://user:pass@localhost:5432/bid_db` |
| `SECRET_KEY` | JWT 서명 키 (256bit+) | `(secret)` |
| `ALGORITHM` | JWT 알고리즘 | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 토큰 만료 시간(분) | `1440` |
| `G2B_API_KEY` | 나라장터 OpenAPI 인증키 | `(secret)` |
| `INPO21C_COOKIE` | inpo21c 세션 쿠키 (`INFO21CSESSID=...`) | `(secret)` |
| `COLLECT_ENABLED` | 수집 스케줄러 활성화 여부 | `true` |

### Frontend (`bid-system/frontend/.env.local`)

| 변수 | 설명 | 예시값 |
|------|------|--------|
| `VITE_API_BASE_URL` | 백엔드 API URL | `http://localhost:8000` |

---

## 브랜치 전략

| 브랜치 | 용도 | merge 대상 |
|--------|------|-----------|
| `main` | 배포 기준 | — |
| `feat/<name>` | 기능 개발 | `main` |
| `fix/<name>` | 버그 수정 | `main` |
| `feat/<task>-<runId>` | 하네스 자동 생성 브랜치 | `main` |

PR 규칙:
- 최소 1인 승인 필요
- 스켈레톤 배너·플레이스홀더 없을 것

# 아키텍처

---

## 개요

단일 모놀리스 + 모노레포 구조.  
FastAPI 백엔드와 React 18 프론트엔드가 `bid-system/` 루트 아래 공존한다.  
나라장터 OpenAPI 데이터 수집은 별도 `collector/` 스케줄러가 담당한다.

---

## 디렉토리 구조

```
atom-harness-g2b/
├── bid-system/
│   ├── backend/                   # FastAPI 애플리케이션
│   │   ├── app/
│   │   │   ├── api/v1/            # REST 라우터 (auth, bids, recommend, ...)
│   │   │   ├── common/            # security.py (JWT 유틸)
│   │   │   ├── ml/                # ML 엔진
│   │   │   │   ├── engine.py      # LightGBM 모델 로드 / 예측
│   │   │   │   ├── simulation.py  # Monte Carlo 복수예가 시뮬레이션
│   │   │   │   ├── assessment.py  # 낙찰하한율 이동평균
│   │   │   │   └── competition.py # 경쟁사 분포 분석
│   │   │   ├── models.py          # SQLAlchemy ORM 모델
│   │   │   ├── schemas.py         # Pydantic Request/Response DTO
│   │   │   ├── services.py        # 비즈니스 로직 (유스케이스)
│   │   │   ├── database.py        # DB 세션 팩토리
│   │   │   └── main.py            # FastAPI 앱 진입점
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   ├── frontend/                  # React 18 + Vite SPA
│   │   └── src/
│   │       ├── api/               # axios 클라이언트 + TanStack Query 훅
│   │       ├── components/        # 공통 UI (layout/, ui/)
│   │       ├── pages/             # 라우트 페이지 컴포넌트
│   │       ├── store/             # Zustand 전역 상태 (auth)
│   │       └── types/             # API 응답 타입 정의
│   ├── collector/                 # 나라장터 OpenAPI 스케줄러
│   ├── docker-compose.yml
│   └── infra/
├── .harness/                      # 개발 하네스 (docs, scripts, phases)
└── CLAUDE.md
```

---

## 레이어 의존성

```
Router (api/v1/)
  └── Service (services.py)
       ├── Repository (models.py + SQLAlchemy Session)
       └── ML Engine (ml/)
```

- Router는 Request 파싱·Response 직렬화만 담당한다.
- 비즈니스 로직은 `services.py`에서만 작성한다.
- ML 추론(`ml/`)은 서비스 레이어에서 호출하고, 라우터에서 직접 호출하지 않는다.

---

## 주요 컴포넌트

각 컴포넌트의 역할과 책임 범위를 정리한다.

### Backend

| 컴포넌트 | 역할 |
|---------|------|
| `api/v1/recommend.py` | 입단가 추천 API 진입점 |
| `services.py::recommend_v2` | Monte Carlo 시뮬레이션 실행 + 전략 구성 |
| `ml/simulation.py` | 복수예가 15→4 추첨 모사, 낙찰 확률 계산 |
| `ml/engine.py` | LightGBM 모델 기반 낙찰가율 예측 |
| `ml/assessment.py` | 낙찰하한율 20건 이동평균 산출 |
| `ml/competition.py` | 경쟁사 입찰 패턴 분포 조회 |
| `common/security.py` | JWT 발급·검증, 역할 기반 접근 제어 |
| `collector/` | 나라장터 OpenAPI 주기적 수집 (별도 프로세스) |

### Frontend

| 컴포넌트 | 역할 |
|---------|------|
| `api/` | axios 래퍼 + TanStack Query 훅 (서버 상태 관리) |
| `pages/RecommendPage.tsx` | 입단가 추천 화면 |
| `pages/BidsPage.tsx` | 입찰 공고 목록 조회 |
| `pages/MyBidsPage.tsx` | 낙찰 이력 관리 |
| `pages/CompetitorPage.tsx` | 경쟁사 분석 |
| `pages/DashboardPage.tsx` | 종합 대시보드 |
| `store/auth.ts` | Zustand — JWT 토큰·사용자 정보 전역 상태 |

---

## 데이터 흐름 — 입단가 추천

```
사용자 입력 (bid_id, 전략 선택)
  → RecommendPage.tsx
  → api/recommend.ts (TanStack Query mutation)
  → POST /api/v1/recommend/v2
  → recommend_v2() in services.py
       ├── ML Engine: 낙찰가율 예측 범위 산출
       ├── Monte Carlo: 복수예가 30,000회 시뮬레이션
       └── 4전략 WinProb 계산 → RecommendV2Response
  ← JSON 응답
  ← UI: 전략별 낙찰 확률 카드 렌더링
```

---

## 인프라

| 환경 | 구성 |
|------|------|
| 로컬 개발 | `docker-compose.yml` (PostgreSQL + backend + frontend + collector) |
| 이미지 | Dockerfile per service |
| DB 마이그레이션 | Alembic (`alembic upgrade head`) |

---

> 이 단계(prototype)에서는 캐싱 레이어(Redis), 메시지 브로커, 분산 트레이싱은 생략한다.

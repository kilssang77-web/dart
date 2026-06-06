# KOSPI/KOSDAQ 실시간 특징주 분석 시스템

실시간 공시·시세·거래량·수급·뉴스를 수집하고, 과거 유사사례를 분석하여 매수/매도 타이밍을 추천하는 시스템.

**핵심 원칙: 상용 AI API 의존 없음 — 완전 로컬 동작**

---

## 아키텍처 개요

```
KIS Open API (WebSocket/REST) ──┐
DART Open API                   ├──▶ Kafka ──▶ Detector ──▶ ML ──▶ Recommender
뉴스 크롤러                      ┘             Analyzer           FastAPI (8000)
                                               ↕
                              PostgreSQL + TimescaleDB + pgvector
                              Redis (캐시 / Pub-Sub)
```

## 주요 기능

| 기능 | 설명 |
|---|---|
| 특징주 탐지 | 거래량급증·신고가·VI·장대양봉·수급이상·공시후급등 |
| 공시 분석 | DART 공시 수집, 호재/악재 자동 분류, 금액 추출 |
| 유사사례 검색 | pgvector 기반 과거 패턴 유사도 검색 |
| 매매 추천 | 진입가·익절가·손절가·성공확률·리스크 점수 |
| 백테스트 | 과거 시그널 검증, 수익률·승률·Sharpe 계산 |

## 빠른 시작

```bash
# 1. 환경변수 설정
cp .env.example .env
# .env 파일에 API 키 입력

# 2. 서비스 시작
docker compose up -d

# 3. 종목 리스트 로드
make load-stocks

# 4. 통계 초기화
make stats

# 5. API 확인
curl http://localhost:8000/health
```

## API 엔드포인트

| Method | Endpoint | 설명 |
|---|---|---|
| GET | `/api/v1/features` | 오늘의 특징주 목록 |
| GET | `/api/v1/features/today/summary` | 오늘 탐지 요약 |
| GET | `/api/v1/features/{id}/similar` | 유사 과거사례 |
| GET | `/api/v1/recommendations/buy` | BUY 추천 목록 |
| GET | `/api/v1/disclosures/favorable` | 호재 공시 |
| POST | `/api/v1/backtest/run` | 백테스트 실행 |
| WS  | `/ws/realtime` | 실시간 이벤트 스트림 |
| GET | `/health` | 헬스 체크 |
| GET | `/metrics` | 운영 메트릭 |

## 운영 일정

```
09:00  장 시작 → WebSocket 구독, 실시간 탐지
15:30  장 마감 → 일봉 수집
16:00  수급/공매도 수집
16:30  make stats  (Redis 통계 갱신)
매주일  make train  (모델 재학습)
```

## 기술 스택

- **Python 3.12** + FastAPI + asyncpg + aiokafka
- **PostgreSQL 16** + TimescaleDB + pgvector
- **Redis 7** (캐시 + Pub/Sub)
- **Kafka** (실시간 스트리밍)
- **LightGBM** (예측 모델)
- **sentence-transformers** `jhgan/ko-sroberta-multitask` (로컬 임베딩)
- **Docker Compose** (단일 명령 배포)

## 보안 주의사항

- `.env` 파일은 절대 커밋하지 마세요
- API 키는 환경변수로만 관리합니다
- `.env.example`에는 키 값이 없습니다

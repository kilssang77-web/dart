# PRD: KOSPI 특징주 탐지 시스템 (kospi-feature-stock)

---

## 목표

KIS OpenAPI 실시간 데이터를 수집·분석하여 KOSPI/KOSDAQ 특징주 신호를 자동 탐지하고, LightGBM ML 모델로 BUY/WAIT/SKIP을 판정해 투자자에게 실시간 추천 신호를 제공한다.

---

## 사용자

| 페르소나 | 설명 | 주요 니즈 |
|---------|------|----------|
| 개인 투자자 | 실시간 특징주 모니터링이 필요한 트레이더 | BUY 신호 실시간 알림, 진입가·목표가·손절가 즉시 확인 |
| 운영자 | 시스템 관리 및 모델 성능 모니터링 | ML 모델 AUC/Brier score 추적, 백테스트 결과 확인 |

---

## 핵심 기능

1. 실시간 체결 데이터를 수집하여 VOLUME_SURGE, BREAKOUT_52W, MORNING_STAR, VI_TRIGGERED 패턴을 탐지한다
2. LightGBM 43피처 모델(AUC 0.75+)로 BUY 성공 확률을 산출하고 Isotonic Calibration으로 보정한다
3. BUY 판정 시 진입가·목표가(+10%)·손절가(-5%)를 자동 계산하고 signal-generated 토픽에 발행한다
4. 매주 일요일 02:00 KST 자동 재학습으로 모델을 최신 데이터에 적응시킨다
5. 장 마감 후 전체 종목(3,967개) 수급 데이터를 수집하여 다음 모델 재학습에 반영한다
6. REST API(`GET /api/v1/recommendations`)로 추천 내역을 외부에 제공한다

---

## MVP 제외 사항

- 실시간 알림 서비스 (signal-generated 토픽 소비 → Push 알림)
- Grafana 대시보드 (모델 성능·추천 통계 시각화)
- 프론트엔드 UI
- 외부 인증/인가 (현재 내부망 전용)
- 소수종목 거래 실행 자동화

---

## 성공 지표 (mvp 기준)

| 지표 | 목표 | 현황 |
|------|------|------|
| Entry 모델 AUC | ≥ 0.70 | 0.7546 ✅ |
| BREAKOUT_52W 백테스트 승률 | ≥ 35% | 40.3% ✅ |
| Recovery 중복 처리 | 0건/재시작 | 0건 ✅ |
| pattern_vector 채움률 | 100% | 144/144 ✅ |
| pytest 단위 테스트 | 통과 | 27/27 ✅ |

---

## 단계별 로드맵

| 단계 | 범위 |
|------|------|
| prototype | 데이터 수집 파이프라인, 기본 패턴 탐지, rule-based 추천 |
| **mvp (현재)** | ML 모델 통합, FastAPI 서비스 분리, 확률 보정, 백테스트 검증 |
| production | 알림 서비스, Grafana 대시보드, 외부 인증, 커버리지 70%+, 보안 스캔 |

---

## 기술 스택

| 영역 | 기술 |
|------|------|
| 언어 | Python 3.12 |
| API 프레임워크 | FastAPI + uvicorn |
| 메시지 브로커 | Apache Kafka (aiokafka) |
| 데이터베이스 | PostgreSQL 16 + TimescaleDB + pgvector |
| DB 클라이언트 | asyncpg |
| ML | LightGBM + scikit-learn (IsotonicRegression) |
| 컨테이너 | Docker Compose |
| 외부 데이터 | KIS OpenAPI (한국투자증권) |

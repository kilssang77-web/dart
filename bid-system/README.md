# 건설 입찰 분석 시스템

> **상용 AI 없이** 로컬 ML(XGBoost + LightGBM + SHAP)로 구동되는  
> 건설 입찰 투찰율 추천 및 수주 전략 분석 시스템

---

## 빠른 시작 (Windows PC)

### 사전 조건

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) 설치

### 설치 및 실행

```bat
1. install.bat  (관리자 권한으로 실행) — 최초 1회
2. start.bat    — 이후 시작
3. stop.bat     — 종료
```

브라우저에서 **http://localhost:3001** 접속

| 항목 | 값 |
|------|----|
| 초기 계정 | admin@bid.local |
| 초기 비밀번호 | admin1234 |

---

## 시스템 구성

```
bid-system/
├── backend/     FastAPI + XGBoost/LightGBM/SHAP
├── frontend/    React 18 + TailwindCSS
├── collector/   나라장터 API/크롤러 (선택)
└── infra/       Nginx + PostgreSQL
```

### AI 모델 (상용 AI 완전 미사용)

| 역할 | 기술 |
|------|------|
| 투찰률 범위 예측 | XGBoost Quantile Regression |
| 낙찰확률 예측 | LightGBM Classification |
| 추천 설명 | SHAP TreeExplainer |
| 데이터 부족 시 폴백 | 규칙 기반 알고리즘 |

---

## 주요 기능

| 화면 | 기능 |
|------|------|
| 대시보드 | KPI 요약, 월별 트렌드, 기관별 건수 |
| 입찰 현황 | 이력 조회, 투찰률 분포 차트 |
| AI 추천 | 투찰률 범위 + 낙찰확률 + SHAP 설명 + 유사 사례 |
| 경쟁사 분석 | 행동 패턴, 레이더 차트, 동시 참여 분석 |
| 통계 | 기관별/공종별 낙찰률, 히트맵 |

---

## 나라장터 실데이터 연동 (선택)

`.env` 파일에서:
```
G2B_API_KEY=<공공데이터포털 발급 키>
COLLECT_ENABLED=true
```

→ 매일 오전 9시, 오후 3시 자동 수집

---

## 운영 명령

```bat
# 서비스 상태 확인
docker compose ps

# 로그 확인
docker compose logs backend -f

# ML 모델 재학습 (데이터 추가 후)
# → 웹 UI 추천 화면 → [모델 재학습] 버튼 (관리자만)

# 데이터 초기화 (주의)
docker compose down -v
```

---

## 포트 사용

| 서비스 | 포트 |
|--------|------|
| 웹 UI  | 3001 |
| API    | 8000 |
| PostgreSQL | 5432 |
| Redis  | 6379 |

# BidAI Pro — 버전 스냅샷
> 작성일: 2026-06-08  
> 복구 기준점으로 사용. 아래 Git 커밋으로 체크아웃하면 해당 시점으로 완전 복구 가능.

---

## 1. Git 기준점

| 항목 | 값 |
|------|-----|
| **복구용 커밋 SHA (Full)** | `50f51fc86f2b45127c0b1a8828f64878b236caf1` |
| **커밋 Short** | `50f51fc` |
| **브랜치** | `master` |
| **커밋 메시지** | `feat(layout): 사이드바 메뉴 디자인 개선` |

### 복구 방법 (Git)
```bash
# 현재 작업 백업 후 해당 커밋으로 이동
git stash
git checkout 50f51fc86f2b45127c0b1a8828f64878b236caf1

# 또는 새 브랜치로 복구
git checkout -b restore-20260608 50f51fc86f2b45127c0b1a8828f64878b236caf1
```

---

## 2. 최근 커밋 이력 (Top 20)

```
50f51fc feat(layout): 사이드바 메뉴 디자인 개선
ee73a0d feat(ui): 전체 페이지 shadcn/ui 기반 프로페셔널 리디자인
70c4b78 feat(win-rate-boost): E1~E7 수주율 최적화 엔진 전체 구현 — 40/40 API 통과
7320473 fix(bids): /bookmarks 라우트를 /{bid_id} 앞으로 이동 (422 버그 수정)
2671da8 feat(inpo21c-enhance): 9개 개선항목 전체 구현
fd53672 fix: 3 bugs found during full feature test
bab53c0 feat(excel-export): step 3+4 - 통계 CSV 내보내기 + MANUAL v2.3
ecb0cd7 feat(excel-export): step 2 — 최종 추천 레포트 PDF 출력
d3e4dd4 feat(excel-export): step 1 — 투찰 이력 Excel 내보내기
ec2229e docs(smart-notify): step 6 — MANUAL.md v2.2 + 릴리즈 노트
150608e feat(smart-notify): step 5 — 알림 목록 페이지 + 읽음 처리
2d571aa feat(smart-notify): step 4 — Notification API + 헤더 알림 뱃지 UI
22e0cae feat(smart-notify): step 3 — 사정율 급변 알림 자동 생성
c1376f2 feat(smart-notify): step 2 — 키워드 매칭 공고 알림 자동 생성
c5a4a14 feat(smart-notify): step 1 — Notification 모델 + 알림 생성 서비스
088020e test: unit test spec sync
b654f0d docs(win-rate-boost): step 11 — MANUAL.md v2.1 + 릴리즈 노트
d5dbfae feat(win-rate-boost): step 10 — agency yega pattern tab
8cbfbb5 feat(win-rate-boost): step 9 — pos_weights(inpo21c) applied to yega simulation
1b56153 feat(win-rate-boost): step 8 — srate source badge + confidence bar UI
```

---

## 3. Docker 이미지 버전

| 이미지 | Image ID | 빌드 시각 | 크기 |
|--------|----------|-----------|------|
| `bid-system-frontend:latest` | `d43735243deb` | 2026-06-07 22:07 | 95.6MB |
| `bid-system-backend:latest` | `a4b618c45f37` | 2026-06-07 18:06 | 2.42GB |
| `bid-system-collector:latest` | `9bc65f840805` | 2026-06-06 11:49 | 1.76GB |
| `postgres:16-alpine` | `16bc17c64a57` | 2026-05-15 | 396MB |
| `redis:7-alpine` | `6ab0b6e73817` | 2026-05-08 | 57.8MB |
| `nginx:alpine` | `2f07d83bf561` | 2026-05-20 | 93.6MB |

### Docker 이미지 복구 방법
```bash
# 현재 이미지로 재빌드 (소스 기준)
cd bid-system
docker compose build
docker compose up -d

# 특정 이미지 ID로 태그 복원
docker tag d43735243deb bid-system-frontend:latest
docker tag a4b618c45f37 bid-system-backend:latest
docker tag 9bc65f840805 bid-system-collector:latest
```

---

## 4. 백엔드 런타임 환경

| 항목 | 버전 |
|------|------|
| **Python** | 3.11.15 |
| **FastAPI** | 0.111.0 |
| **SQLAlchemy** | 2.0.30 |
| **XGBoost** | 2.0.3 |
| **LightGBM** | 4.3.0 |
| **Pydantic** | 2.7.1 |
| **Uvicorn** | 0.29.0 |
| **SHAP** | 0.45.1 |
| **NumPy** | 1.26.4 |
| **Pandas** | 2.2.2 |
| **scikit-learn** | 1.4.2 |
| **Redis-py** | 5.0.4 |
| **APScheduler** | 3.10.4 |
| **Alembic** | 1.13.1 |

전체 의존성: `bid-system/backend/requirements.txt`

---

## 5. 프론트엔드 환경

| 항목 | 버전 |
|------|------|
| **React** | ^18.3.1 |
| **TypeScript** | ^5.4.5 |
| **Vite** | ^5.3.1 |
| **TanStack Query** | ^5.40.0 |
| **React Router** | ^6.23.1 |
| **Zustand** | ^4.5.2 |
| **Tailwind CSS** | ^3.4.4 |
| **Recharts** | ^2.12.7 |
| **Lucide React** | ^0.395.0 |
| **Radix UI (Avatar)** | ^1.1.11 |
| **Radix UI (Tabs)** | ^1.1.13 |
| **Axios** | ^1.7.2 |

전체 의존성: `bid-system/frontend/package.json`

---

## 6. 데이터베이스 현황 (2026-06-08 기준)

| 테이블 | 레코드 수 |
|--------|----------|
| `bids` | **128,476건** |
| `bid_results` | **45,849건** |
| `competitors` | **26,347건** |
| `inpo21c_participants` | **31,810건** |
| `inpo21c_bids` | 324건 |
| `my_bid_records` | **618건** |
| `users` | 1건 |
| `notifications` | 0건 |

**총 테이블 수**: 34개

### DB 전체 백업
```bash
# 덤프 생성
docker exec bid_postgres pg_dump -U biduser biddb > backup_20260608.sql

# 복구
docker exec -i bid_postgres psql -U biduser biddb < backup_20260608.sql
```

---

## 7. 서비스 접근 정보

| 서비스 | 주소 |
|--------|------|
| **웹 UI** | http://localhost:3001 |
| **백엔드 API** | http://localhost:8100/api/v1 |
| **API 문서** | http://localhost:8100/docs |
| **관리자 계정** | admin@bid.local / admin1234 |

---

## 8. 주요 구현 기능 목록

### ML 엔진 (8개)
- **E1** 입찰 선택 (GO/WATCH/NO-GO) — 점수 기반 자동 분류
- **E2** 적격 심사 계산기 — 로컬/중앙 조달 규칙 기반
- **E3** 사정율 예측 — XGBoost 회귀 + FeatureStore
- **E4** 경쟁사 분석 — HHI, 공격성 지수, 시장압력
- **E5** 단일 최적 투찰률 추천 — Monte Carlo + EV 최대화
- **E6** 피드백 루프 — 실제 결과 수집 후 자동 재훈련
- **E7** 포트폴리오 최적화 — 0-1 냅색 DP (보증한도 제약)
- **E8** KPI 대시보드 — 일/주/월별 스냅샷

### 프론트엔드 페이지 (25개)
- 오늘의 입찰, 대시보드, 추천 공고, 전체 공고, 관심 공고
- 입찰 선택, AI 투찰 추천(V1/V2), 적격 심사, 경쟁사 분석
- 예가 분석, 파트너 탐색, 수주 현황, KPI 대시보드
- 투찰 이력, 통계 분석, 시장 인텔리전스, 발주기관
- 키워드 설정, 회사 프로파일, 알림, 관리자 등

---

## 9. 설정 파일 위치

| 파일 | 설명 |
|------|------|
| `bid-system/docker-compose.yml` | 컨테이너 구성 |
| `bid-system/backend/requirements.txt` | Python 의존성 |
| `bid-system/frontend/package.json` | Node 의존성 |
| `.claude/settings.json` | Claude Code 권한 설정 |
| `bid-system/.env` | 환경변수 (DB/Redis/JWT 등) |

---

*이 파일은 복구 기준점 기록용입니다. 코드 변경 금지.*

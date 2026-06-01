# Architecture Decision Records

---

## 철학

작동하는 최소 구현 우선. 나라장터 입찰 도메인 특성(복수예가 메커니즘, 낙찰하한율)을 코드에 명시적으로 반영한다. 팀이 모두 이해할 수 있는 기술 선택.

---

### ADR-001: FastAPI + Python 3.12 채택

- **결정**: 백엔드 런타임으로 FastAPI(Python 3.12, Uvicorn)를 선택한다.
- **이유**:
  - ML 라이브러리(LightGBM, NumPy)와 동일 언어 생태계 — 별도 Python 런타임 없이 모델 서빙 가능
  - 비동기 I/O(async/await)로 나라장터 OpenAPI 다중 호출 처리에 적합
  - Pydantic 기반 자동 OpenAPI 문서화로 프론트엔드 연동 비용 절감
- **트레이드오프**:
  - Java/Kotlin 대비 정적 타입 안전성이 낮음 → Pydantic + mypy 엄격 모드로 완화
  - Spring의 성숙한 엔터프라이즈 기능(트랜잭션 AOP 등) 부재 → SQLAlchemy 세션 관리로 대체

---

### ADR-002: Monte Carlo 시뮬레이션 기반 복수예가 낙찰 확률 추정

- **결정**: 복수예가 메커니즘(15개 예가 중 4개 무작위 추첨 → 평균 = 예정가격)을 Monte Carlo(n=30,000회)로 모사하여 낙찰 확률을 추정한다.
- **이유**:
  - 나라장터 복수예가는 해석적 확률 계산이 불가(C(15,4) = 1365 경우의 수 × 경쟁사 분포)
  - 30,000회 시뮬레이션 시 표준오차 < 0.3%p로 실용적 정확도 확보
  - 낙찰하한율 차등 적용(전기·정통·소방 86.745% / 나머지 87.745%) 반영 가능
- **트레이드오프**:
  - 요청당 CPU 연산 비용 → 캐싱 또는 백그라운드 작업 고려 필요 (현재 prototype에서는 동기 처리)
  - 경쟁사 실제 입찰 가격 분포를 히스토리 데이터로 근사 — 신규 경쟁사는 평균 분포 사용

---

### ADR-003: React 18 + Vite + React Router v6 + TanStack Query v5

- **결정**: 프론트엔드 스택을 React 18 + Vite(CSR) + React Router v6 + TanStack Query v5로 구성한다.
- **이유**:
  - Vite: 개발 서버 즉시 기동, HMR 속도 우수 — prototype 이터레이션에 최적
  - TanStack Query: 서버 상태 캐싱·재검색·낙관적 업데이트를 선언적으로 관리
  - CSR: 입찰 데이터는 인증 후에만 접근 — SEO 불필요, SSR 오버헤드 없음
- **트레이드오프**:
  - SSR 부재로 초기 로딩 번들 크기 관리 필요 → 라우트별 코드 스플리팅 적용

---

### ADR-004: shadcn/ui (Radix UI + Tailwind CSS) 컴포넌트 시스템

- **결정**: UI 컴포넌트 시스템으로 shadcn/ui (Radix UI 프리미티브 + Tailwind CSS)를 사용한다.
- **이유**:
  - 접근성 기본 보장(Radix UI ARIA)
  - 소스 복사 방식 — 빌드 결과에 미사용 컴포넌트가 포함되지 않음
  - Tailwind 유틸리티 클래스로 디자인 일관성 유지 용이
- **트레이드오프**:
  - 업스트림 컴포넌트 변경 시 수동 업데이트 필요 (shadcn `add` 재실행)

---

### ADR-005: JWT 단일 Access Token 인증 (prototype)

- **결정**: 인증은 JWT Access Token 단일 방식으로 구현한다. Refresh Token 순환은 prototype에서 생략한다.
- **이유**:
  - 사내 도구(b2b_internal) 성격 — 세션 탈취 위험 낮음
  - prototype 단계에서 토큰 순환 복잡도를 배제하고 기능 검증에 집중
- **트레이드오프**:
  - 토큰 만료 후 재로그인 필요 — mvp 단계에서 Refresh Token 순환 추가 예정
  - Revocation List 없음 — 로그아웃 후 만료 전 토큰 재사용 가능

---

> ADR은 결정 시점의 컨텍스트를 보존합니다. 번복 시 새 ADR을 추가하고 이전 ADR에 "superseded by ADR-XXX"를 기재합니다.

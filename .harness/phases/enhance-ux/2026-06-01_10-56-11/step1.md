---
relevant_docs: ["UI_GUIDE", "ARCHITECTURE"]
relevant_references: ["infose_info21c"]
---

# Step 4: AI 추천 UI 시각화 강화

## 목표
추천 결과를 숫자가 아닌 시각적 컴포넌트로 직관적으로 이해할 수 있도록 RecommendPage를 전면 개선한다.

## 작업 내용 (Frontend 전용)

### 신규 컴포넌트
1. `bid-system/frontend/src/components/ui/WinProbGauge.tsx`
   - 반원형 Gauge (0~100%)
   - Recharts `PieChart` 2개 slice (달성/미달성) + 중앙 숫자 텍스트
   - 색상: 70%+ green, 40~70% amber, ~40% red

2. `bid-system/frontend/src/components/ui/StrategyCompareChart.tsx`
   - 4전략 수평 바차트 (공격형·균형형·안정형·회피형)
   - X축: 낙찰 확률(%), 각 바에 전략명 + 목표 낙찰가율 레이블
   - 현재 선택 전략 강조 (진한 색)

3. `bid-system/frontend/src/components/ui/SrateRangeViz.tsx`
   - 사정율 예측 범위 시각화
   - 수평 슬라이더 형태: p10 ← [p25 ─ p50 ─ p75] → p90
   - 신뢰구간 색상 그라디언트

4. `bid-system/frontend/src/components/ui/RiskCard.tsx`
   - LOW: 초록 테두리 + 체크 아이콘
   - MEDIUM: 노란 테두리 + 경고 아이콘
   - HIGH: 빨간 테두리 + X 아이콘
   - 리스크 점수 프로그레스 바 포함

### RecommendPage.tsx 레이아웃 재구성
5. 결과 영역 2-column 레이아웃:
   - 좌: `WinProbGauge` (균형전략 기준) + 최종 권장 낙찰가율 (대형 폰트)
   - 우: `RiskCard` + 경쟁강도 지표 (예상 경쟁사수, 시장압박지수)
6. `StrategyCompareChart` — 4전략 한눈 비교 섹션
7. `SrateRangeViz` — 사정율 예측 범위 섹션
8. SHAP 요인 카드 — 각 요인 방향(↑긍정/↓부정) 아이콘 + 색상 강조
9. 입력 폼 개선:
   - 기관명 자동완성 (meta API debounce 검색)
   - 기초금액 천 단위 구분 표시 (1,000,000원)
   - 최근 추천 이력 드롭다운 (재사용 편의)

## Acceptance Criteria
- [ ] WinProbGauge가 추천 결과의 균형전략 win_prob을 표시
- [ ] StrategyCompareChart에서 4전략 확률 나란히 비교 가능
- [ ] SrateRangeViz에서 신뢰구간 시각화 표시
- [ ] RiskCard LOW/MEDIUM/HIGH 색상 분기 동작
- [ ] 기관명 자동완성 debounce 동작 (300ms)
- [ ] 빌드 오류 없음

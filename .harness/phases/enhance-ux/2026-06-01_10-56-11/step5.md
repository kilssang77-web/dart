---
relevant_docs: ["ARCHITECTURE", "PRD"]
relevant_references: ["infose_info21c"]
---

# Step 3: 경쟁사 투찰성향 분석 강화

## 목표
경쟁사의 금액대별 투찰 패턴과 성향 지표를 시각화하고, 2개 경쟁사 비교 기능을 추가한다.

## 작업 내용

### Backend
1. `GET /competitors/{id}/pattern` — 투찰성향 분석 API 신규
   - 파일: `bid-system/backend/app/api/v1/competitors.py` 엔드포인트 추가
   - `bid-system/backend/app/services.py` `CompetitorService.get_pattern()` 신규
   - 반환 구조:
     ```
     {
       radar: {
         aggression: 0~10,    # 공격성 (낮은 가격 투찰 빈도)
         consistency: 0~10,   # 일관성 (std 역수 기반)
         concentration: 0~10, # 집중도 (특정 기관 집중 여부)
         risk: 0~10,          # 위험도 (하한율 이하 투찰 비율)
         activity: 0~10       # 활동성 (월 평균 입찰 건수)
       },
       amount_pattern: [
         { bucket: "1억 미만", bid_count, win_count, avg_rate, win_rate }
         { bucket: "1~3억", ... }
         { bucket: "3~10억", ... }
         { bucket: "10억 이상", ... }
       ],
       recent_trend: { direction: "aggressive|stable|defensive", change_pct }
     }
     ```
2. `GET /competitors/compare?ids=1,2` — 2개 경쟁사 비교 API 신규
   - 두 경쟁사의 radar 지표와 최근 12개월 추이 반환
3. `schemas.py` — `CompetitorPattern`, `CompetitorCompareResponse` 추가

### Frontend
4. `bid-system/frontend/src/api/index.ts` — `competitorsApi.pattern(id)`, `competitorsApi.compare(ids)` 추가
5. `bid-system/frontend/src/types/index.ts` — 관련 타입 추가
6. `bid-system/frontend/src/pages/CompetitorPage.tsx` 수정
   - 경쟁사 상세에 "투찰성향" 탭 추가
     - Recharts `RadarChart` — 5개 지표 레이더
     - 금액대별 `BarChart` (건수 + 낙찰가율 dual)
     - 최근 성향 변화 방향 배지 (공격적↑ / 안정 / 방어적↓)
   - 경쟁사 목록에서 체크박스 2개 선택 → "비교하기" 버튼
   - 비교 모달: 두 경쟁사 레이더차트 오버레이

## Acceptance Criteria
- [ ] `/competitors/1/pattern` 응답에 radar, amount_pattern 포함
- [ ] RadarChart 5개 지표 렌더링 확인
- [ ] 금액대별 투찰 바차트 표시
- [ ] 경쟁사 2개 비교 모달 동작
- [ ] 빌드 오류 없음

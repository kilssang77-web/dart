---
relevant_docs: ["PRD", "UI_GUIDE"]
---

# Step 6: UX 종합 개선 (북마크·My입찰 분석·대시보드)

## 목표
반복 작업 최소화(북마크)와 개인 성과 추적(My입찰 분석), 대시보드 KPI 강화로 일상 사용성을 높인다.

## 작업 내용

### 공고 북마크
1. `bid-system/backend/app/models.py` — `BidBookmark` 모델 추가
   ```python
   class BidBookmark(Base):
       __tablename__ = "bid_bookmarks"
       id         = Column(Integer, primary_key=True)
       user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
       bid_id     = Column(BigInteger, ForeignKey("bids.id"), nullable=False)
       note       = Column(String(200))
       created_at = Column(DateTime(timezone=True), server_default=func.now())
       __table_args__ = (UniqueConstraint("user_id", "bid_id"),)
   ```
2. `bid-system/backend/app/api/v1/bids.py`
   - `POST /bids/{id}/bookmark` — 북마크 추가
   - `DELETE /bids/{id}/bookmark` — 북마크 제거
   - `GET /bids/bookmarks` — 내 북마크 목록 (페이지네이션)
3. `bid-system/backend/app/services.py` — `BidService` 북마크 메서드 추가
4. `bid-system/backend/app/schemas.py` — `BookmarkResponse` 추가

### My입찰 정확도 분석
5. `bid-system/backend/app/api/v1/my_bids.py`
   - `GET /my-bids/analysis` 신규
   - 반환: `{ accuracy_stats, rate_scatter[], monthly_accuracy[] }`
     - `accuracy_stats`: 평균 오차, 중앙값 오차, ±1% 적중률, ±3% 적중률
     - `rate_scatter`: `[{ submitted_rate, recommendation_rate, result, bid_date }]`
     - `monthly_accuracy`: `[{ year_month, mae, win_count, total }]`
6. `bid-system/backend/app/schemas.py` — `MyBidAnalysisResponse` 추가

### 대시보드 KPI 강화
7. `bid-system/backend/app/api/v1/statistics.py`
   - `GET /stats/overview` 응답에 전월 대비 증감률 추가
     - `win_rate_change_pct`, `bid_count_change_pct`, `avg_competitors_change`

### Frontend
8. `bid-system/frontend/src/api/index.ts` 추가
   - `bidsApi.addBookmark(id)`, `bidsApi.removeBookmark(id)`, `bidsApi.bookmarks()`
   - `myBidsApi.analysis()`
9. `bid-system/frontend/src/types/index.ts` — 관련 타입 추가
10. `bid-system/frontend/src/pages/BidsPage.tsx`
    - 공고 행에 북마크 토글 버튼 (★) — 즉시 반영 (낙관적 업데이트)
    - 북마크된 공고 필터 탭 추가
11. `bid-system/frontend/src/pages/MyBidsPage.tsx`
    - "정확도 분석" 탭 추가
    - Recharts `ScatterChart` — X축: 추천률, Y축: 실제 투찰률, 색상: 낙찰여부
    - 월별 MAE 라인차트
    - 정확도 요약 카드 (±1% 적중률, ±3% 적중률)
12. `bid-system/frontend/src/pages/DashboardPage.tsx`
    - KPI 카드에 전월 대비 화살표 추가 (↑/↓ + 변화율 %)
    - 색상: 낙찰률 상승 → green, 하락 → red

## Acceptance Criteria
- [ ] `POST /bids/1/bookmark` → 204 응답 + DB 저장 확인
- [ ] `GET /bids/bookmarks` 목록 반환 확인
- [ ] `GET /my-bids/analysis` 응답에 rate_scatter, monthly_accuracy 포함
- [ ] BidsPage 북마크 토글 즉시 반영 (낙관적 업데이트)
- [ ] MyBidsPage 산점도 차트 렌더링 확인
- [ ] DashboardPage KPI 카드 전월 대비 화살표 표시
- [ ] 빌드 오류 없음

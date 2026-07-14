# 실행 리포트: mvp-enhance2/2026-06-05_21-00-28

## 개요

| 항목 | 값 |
|------|------|
| task | mvp-enhance2 |
| run_id | 2026-06-05_21-00-28 |
| 시작 | 2026-06-05T21:00:28+09:00 |
| 완료 | 2026-06-05T22:23:55+0900 |
| 참고 프로젝트 | info21c, infose_info21c |

## Step 결과

| step | 이름 | 상태 | 요약 |
|------|------|------|------|
| 1 | A값 자동 계산 + 낙찰하한가 산출 | ✓ completed | ml/a_value.py 신규(FLOOR_RATE_TABLE 이전·calc_bid_range), GET /recommend/bid-range 엔 |
| 2 | 사정율 트렌드 알림 (발주처×공종 최근 3개월) | ✓ completed | SrateTrendService(get_trend·get_top_trends·폴백), GET /stats/srate-trend·/top-srat |
| 3 | 프리즘 2.0 대응 — 구간별 낙찰확률 히트맵 10개 추천 | ✓ completed | ml/prism.py 신규(scan_prism_zones·71구간·floor필터·top10), POST /recommend/prism 엔드포인트 |
| 4 | 경쟁사 최근 투찰 구간 실시간 모니터링 | ✓ completed | CompetitorZoneService(get_recent_zones·0.005버킷·peak_zone), GET /competitors/{id} |
| 5 | 공고 자동 추천 TOP 5 + 점수 카드 (Dashboard) | ✓ completed | OpportunityScoreService.get_top_recommended(7일 이내 open 공고·활성공종필터·점수정렬), GET /bid |
| 6 | 낙찰 후 역산 분석 — rate_diff 분포·패턴 | ✓ completed | DefeatAnalysisService.get_gap_distribution, GET /my-bids/gap-analysis, GapBucket |
| 7 | 예가 번호 패턴 ML — 발주처 특화 빈도 분석 | ✓ completed | ml/yega.py get_agency_yega_pattern(C(15,4) 역산 번호1~15 빈도 dominant_zone), AgencyYe |
| 8 | 공동도급 적격심사 AI 매칭 + 입찰 전략 레포트 PDF | ✓ completed | JointQualService.find_matching_partners(CompetitorStat 집계·적격여부·궁합점수·최소지분율), GET  |

## 커밋 목록

```
00eb650 chore(mvp-enhance2): step 8 output
ffa4303 feat(mvp-enhance2): step 8 — 공동도급 적격심사 AI 매칭 + 입찰 전략 레포트 PDF
5eb7735 chore(mvp-enhance2): step 7 output
e8608ef feat(mvp-enhance2): step 7 — 예가 번호 패턴 ML (발주처 특화 빈도 분석)
01ee519 chore(mvp-enhance2): step 6 output
4024443 feat(mvp-enhance2): step 6 — 낙찰 후 역산 분석 rate_diff 분포·패턴
2f134af chore(mvp-enhance2): step 5 output
641f886 feat(mvp-enhance2): step 5 — 공고 자동 추천 TOP 5 + 점수 카드 (Dashboard)
af8f62a chore(mvp-enhance2): step 4 output
f4d6fe1 feat(mvp-enhance2): step 4 — 경쟁사 최근 투찰 구간 실시간 모니터링
```

## 변경 통계

```
.../mvp-enhance2/2026-06-05_21-00-28/index.json    |  12 +-
 .../2026-06-05_21-00-28/step6-output.json          |   8 +
 .../2026-06-05_21-00-28/step7-output.json          |   8 +
 .../2026-06-05_21-00-28/step8-output.json          |   8 +
 bid-system/backend/app/api/v1/bids.py              |  15 +-
 bid-system/backend/app/api/v1/recommend.py         |  16 +-
 bid-system/backend/app/ml/yega.py                  |  97 +++++++++++-
 bid-system/backend/app/schemas.py                  |  33 +++++
 bid-system/backend/app/services.py                 | 142 ++++++++++++++++++
 .../backend/tests/unit/test_joint_qual_service.py  | 157 ++++++++++++++++++++
 bid-system/backend/tests/unit/test_yega_pattern.py |  74 +++++++++
 bid-system/frontend/package.json                   |   2 +
 bid-system/frontend/src/api/index.ts               |   8 +-
 bid-system/frontend/src/pages/JointBidPage.tsx     | 139 ++++++++++++++++-
 bid-system/frontend/src/pages/RecommendPage.tsx    | 165 ++++++++++++++++++++-
 bid-system/frontend/src/pages/YegaPage.tsx         | 123 ++++++++++++++-
 bid-system/frontend/src/types/index.ts             |  34 +++++
 17 files changed, 1018 insertions(+), 23 deletions(-)
```

## 다음 단계 제안

- 이 run에서 생성된 release-note를 확인하세요: `.harness/release-notes/2026-06-05_21-00-28_mvp-enhance2.md`
- docs 동기화가 필요하면: `/a2m_sync_docs`
- 추가 개선이 필요하면: `/a2m_improve`

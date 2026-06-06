---
step: 5
title: "MVP 보강: pytest 단위 테스트 신설"
status: pending
relevant_docs: ["TESTING", "CODING_CONVENTION"]
relevant_references: []
---

## 목표

mvp 단계 요건인 pytest 단위 테스트를 신설한다.
핵심 비즈니스 로직 (탐지 규칙, 추천 알고리즘)을 우선 커버한다.

## 변경 파일 (신설)

- `kospi-feature-stock/tests/__init__.py`
- `kospi-feature-stock/tests/test_candlestick.py`
- `kospi-feature-stock/tests/test_entry_recommender.py`
- `kospi-feature-stock/tests/requirements-test.txt`

## 구현 세부사항

### test_candlestick.py

```python
# 테스트 케이스:
# 1. detect_long_white_candle — 양봉 65% 이상 + 3% 상승 → True
# 2. detect_long_white_candle — 50% 봉 → False
# 3. detect_hammer — 하단꼬리 2×몸통 → True
# 4. detect_hammer — 상단꼬리 있음 → False
# 5. detect_morning_star — 정상 3봉 패턴 → True
# 6. detect_morning_star — b2 몸통 40% 초과 → False
# 7. detect_morning_star — bars 부족 (2개) → False
# 8. long_white_score — 범위 [0.50, 0.92] 확인
```

### test_entry_recommender.py

```python
# 테스트 케이스:
# 1. recommend() — risk>0.60 → action==SKIP
# 2. recommend() — prob<0.55 → action==WAIT
# 3. recommend() — rr<2.0 → action==WAIT
# 4. recommend() — 정상 조건 → action==BUY
# 5. 진입가 = 현재가 (±0.5% 이내)
# 6. 손절가 ≥ 5% 하락
# 7. 목표가 = 손절거리 × 2 이상
# 8. risk_reward_ratio = (target-entry) / (entry-stop)
```

### requirements-test.txt

```
pytest==8.2.0
pytest-asyncio==0.23.7
```

## 완료 기준

- `pytest kospi-feature-stock/tests/ -v` 실행 시 전체 통과
- candlestick 테스트 8개 이상
- entry_recommender 테스트 8개 이상
- 탐지 규칙 핵심 로직 커버

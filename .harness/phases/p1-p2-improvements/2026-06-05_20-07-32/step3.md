---
step: 3
title: "P1-3: KOSPI 상대수익률 피처 수정"
status: pending
relevant_docs: ["CODING_CONVENTION", "ARCHITECTURE"]
relevant_references: []
---

## 목표

ML 피처의 `kospi_return_1d` / `kospi_return_5d`가 항상 0으로 반환되는 문제를 수정한다.
`daily_bars` 테이블에 이미 KOSPI 지수 데이터가 존재하는 경우 이를 활용한다.
없으면 collector에서 KIS API 지수 데이터를 수집해 저장하는 로직을 추가한다.

## 변경 파일

- `kospi-feature-stock/services/ml/features/technical.py`
- `kospi-feature-stock/services/collector/main.py` (KOSPI 지수 수집 추가)

## 구현 세부사항

### 1. TechnicalFeatureExtractor 수정 (features/technical.py)

`extract()` 메서드에서 `kospi_return_1d`, `kospi_return_5d`를 계산하는 부분이 0을 반환하는 원인 찾기:
- 현재: `df["kospi_return_1d"] = 0.0` (하드코딩)
- 수정: DB에서 KOSPI 지수 일봉(code='0001' 또는 KOSPI pseudo-code)을 조회해 계산

```python
async def _load_market_returns(pool, start_date, end_date) -> pd.Series:
    rows = await pool.fetch(
        "SELECT date, close FROM daily_bars WHERE code='0001' AND date BETWEEN $1 AND $2 ORDER BY date",
        start_date, end_date,
    )
    if not rows:
        return pd.Series(dtype=float)
    s = pd.Series({r['date']: float(r['close']) for r in rows})
    return s.pct_change().rename("kospi_return")
```

### 2. Collector KOSPI 지수 수집 (collector/main.py)

KIS API의 국내 지수 조회 API (`/uapi/domestic-stock/v1/quotations/inquire-index-daily`)를 이용해
KOSPI(0001), KOSDAQ(1001) 일봉을 `daily_bars`에 저장:
- 종목코드 '0001' (KOSPI), '1001' (KOSDAQ) 사용
- 장 마감 후 기존 일봉 수집 루프에 함께 실행

### 3. stocks 테이블에 KOSPI 의사 종목 등록

`infra/postgres/seed_data.sql`에 추가:
```sql
INSERT INTO stocks (code, name, market, sector) VALUES
  ('0001', 'KOSPI지수', 'INDEX', '지수'),
  ('1001', 'KOSDAQ지수', 'INDEX', '지수')
ON CONFLICT (code) DO NOTHING;
```

## 사이드 이펙트

- ML 피처 변경으로 기존 모델의 kospi_return 피처 정밀도 향상
- 기존 모델은 0 피처로 학습됐으므로 재학습 후 효과 반영 (step2 연동)

## 완료 기준

- `daily_bars` 테이블에 code='0001' 데이터 존재
- `TechnicalFeatureExtractor.extract()` 결과에서 kospi_return_1d ≠ 0
- ML 추론 로그에서 kospi_return_1d 값이 실제값으로 출력됨

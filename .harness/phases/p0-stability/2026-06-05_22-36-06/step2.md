---
step: 2
title: "KOSPI/KOSDAQ 지수 일봉 수집"
relevant_docs: ["ARCHITECTURE.md", "CODING_CONVENTION.md"]
relevant_references: []
---

## 목적

`daily_bars`에 `code='0001'`(KOSPI), `'1001'`(KOSDAQ) 데이터가 없어
ML 모델의 시장 상대강도 4개 피처(`kospi_return_1d`, `kospi_return_5d`, `rel_strength_5d`, `market_vol_ratio`)가 전부 0.

## 해결 방식

### 1. `rest_client.py` — `get_index_bars()` 메서드 추가

KIS API: `GET /uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice`
TR-ID: `FHKUP03500100`

```python
async def get_index_bars(self, market: str, start: str, end: str) -> list[dict]:
    """
    market: "0001" (KOSPI) / "1001" (KOSDAQ)
    start/end: "YYYYMMDD"
    returns: [{"code": market, "date": "YYYYMMDD", "open": ..., "close": ..., "volume": ...}, ...]
    """
```

KIS API 파라미터:
- `FID_COND_MRKT_DIV_CODE`: "U" (업종/지수)
- `FID_INPUT_ISCD`: "0001" or "1001"
- `FID_INPUT_DATE_1`, `FID_INPUT_DATE_2`: YYYYMMDD
- `FID_PERIOD_DIV_CODE`: "D"
응답 필드: `output2[*]` — `stck_bsop_date`, `bstp_nmix_oprc`, `bstp_nmix_hgpr`, `bstp_nmix_lwpr`, `bstp_nmix_prpr`, `acml_vol`

### 2. `collector/main.py` — `_daily_bar_loop()` 에 지수 수집 추가

`_daily_bar_loop` 내부, 종목 일봉 수집 완료 후:
```python
for mkt_code in ["0001", "1001"]:
    try:
        idx_bars = await self.rest.get_index_bars(mkt_code, start, today)
        await write_daily_bars(self.db, idx_bars)
    except Exception as e:
        logger.error(f"[Index] {mkt_code}: {e}")
```

### 3. `_backfill_daily_bars()` — 지수도 백필 대상에 포함

`to_backfill` 체크 후 지수 코드 별도 백필:
```python
for mkt_code in ["0001", "1001"]:
    if mkt_code not in covered_set:
        idx_bars = await self.rest.get_index_bars(mkt_code, start, end)
        await write_daily_bars(self.db, idx_bars)
```

## 기존 시그니처 변경 없음

`write_daily_bars`는 code 포함 dict 리스트를 받으므로 그대로 사용 가능.

## 사이드 이펙트

없음. `daily_bars`에 `code='0001'/'1001'` 추가 INSERT만 발생.
이후 ML 재학습 시 KOSPI 피처 4개 정상 계산됨.

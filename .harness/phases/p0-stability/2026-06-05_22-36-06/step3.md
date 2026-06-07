---
step: 3
title: "supply_demand EOD 수집 추가 + 로깅 개선"
relevant_docs: ["ARCHITECTURE.md", "CODING_CONVENTION.md"]
relevant_references: []
---

## 목적

`supply_demand` 테이블이 0행. 원인 분석:
- `_supply_demand_loop`는 `is_market_open()` True일 때만 실행 → 장 마감 후 수집 불가
- KIS `inquire-investor` API는 당일 누적 투자자 순매수를 실시간 제공하지만,
  장 마감 후(15:30 이후) 당일 최종 확정 수급 데이터가 더 정확함
- 장 마감 후 EOD 수급 수집 루프 추가 필요
- 또한 `_supply_demand_loop` 실패 시 `logger.error`만 출력되고 어떤 API 응답인지 불투명

## 해결 방식

### 1. 장 마감 후 EOD 수급 수집 메서드 추가

`collector/main.py`에 `_supply_demand_eod_loop()` 추가:
- `is_after_close()` True이고 오늘 미실행인 경우 1회 실행
- `all_codes` (전체 종목) 대상으로 오늘 수급 수집
- rate limit: 0.3초 간격 (일봉과 동일)
- `_daily_bars_done` 이벤트 대기 후 실행 (일봉 수집 완료 보장)

```python
async def _supply_demand_eod_loop(self, all_codes: list[str]):
    last_run_date = ""
    while True:
        await asyncio.sleep(60)
        if not is_after_close():
            continue
        today = datetime.now(_KST).strftime("%Y%m%d")
        if last_run_date == today:
            continue
        # _daily_bars_done 대기 (일봉 완료 후 실행)
        try:
            await asyncio.wait_for(asyncio.shield(self._daily_bars_done.wait()), timeout=3600)
        except asyncio.TimeoutError:
            continue
        last_run_date = today
        logger.info(f"[SD-EOD] Starting supply_demand EOD for {len(all_codes)} stocks")
        success, fail = 0, 0
        for code in all_codes:
            try:
                sd = await self.rest.get_supply_demand(code, today)
                if sd:
                    await write_supply_demand(self.db, sd)
                    success += 1
                else:
                    fail += 1
            except Exception as e:
                logger.warning(f"[SD-EOD] {code}: {e}")
                fail += 1
            await asyncio.sleep(0.3)
        logger.info(f"[SD-EOD] Done: success={success}, empty={fail}")
```

### 2. `run()` gather에 `_supply_demand_eod_loop` 추가

`asyncio.gather(...)` 목록에 `self._supply_demand_eod_loop(all_codes)` 추가.

### 3. `_supply_demand_loop` 로깅 개선

실패 건수 집계 및 요약 로그 추가:
```python
success, empty, fail = 0, 0, 0
# ...
if sd:
    success += 1
else:
    empty += 1
# except: fail += 1
logger.info(f"[SD] Cycle done: success={success}, empty={empty}, error={fail}")
```

## 기존 시그니처 변경 없음

새 메서드 추가만. 기존 intraday 루프는 그대로 유지.

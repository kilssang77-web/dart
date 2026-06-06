---
step: 1
title: "P1-1: 모닝스타 3봉 패턴 detector 연결"
status: pending
relevant_docs: ["CODING_CONVENTION", "ARCHITECTURE"]
relevant_references: []
---

## 목표

`services/detector/rules/candlestick.py`에 이미 구현된 `detect_morning_star(bars: list[dict])`를
`services/detector/main.py`의 `_process_minute_bars()`에 연결한다.

## 변경 파일

- `kospi-feature-stock/services/detector/main.py`

## 구현 세부사항

1. `FeatureStockDetector.__init__`에 종목별 최근 3개 분봉을 유지하는 슬라이딩 버퍼 추가:
   ```python
   self._bar_buffer: dict[str, list[dict]] = {}   # code → 최근 3봉
   ```

2. `_process_minute_bars()` 내 기존 장대양봉/망치형 처리 다음에 모닝스타 탐지 블록 추가:
   ```python
   # 버퍼 업데이트 (최근 3봉 유지)
   buf = self._bar_buffer.setdefault(code, [])
   buf.append(bar)
   if len(buf) > 3:
       buf.pop(0)

   # 모닝스타 (3봉 필요)
   if self.cnd_det.detect_morning_star(buf):
       await self._emit({
           "code":        code,
           "event_type":  "MORNING_STAR",
           "price":       int(bar.get("close", 0)),
           "change_rate": float(bar.get("change_rate", 0)),
           "signal_score": 0.68,
           "signal_data": {"bars": buf[-3:]},
       })
   ```

3. `services/api/routers/features.py`의 `EVENT_TYPES` 리스트에 `"MORNING_STAR"` 추가

## 사이드 이펙트

- 쿨다운 10분으로 중복 신호 자동 억제됨
- _bar_buffer는 메모리 내 상태 — 재시작 시 버퍼 리셋되나 큰 문제 없음

## 완료 기준

- detect_morning_star가 실제 Kafka 이벤트로 발행됨
- event_type='MORNING_STAR'가 feature_events에 저장됨
- EVENT_TYPES 목록에 추가됨

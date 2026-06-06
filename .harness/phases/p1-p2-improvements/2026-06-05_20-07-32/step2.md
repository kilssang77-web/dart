---
step: 2
title: "P1-2: ML 모델 주간 자동 재학습 스케줄러"
status: pending
relevant_docs: ["CODING_CONVENTION", "ARCHITECTURE"]
relevant_references: []
---

## 목표

`services/ml/main.py`에 asyncio 기반 주간 자동 재학습 루프를 추가한다.
외부 라이브러리 없이 asyncio.sleep 기반으로 구현 (requirements 변경 없음).

## 변경 파일

- `kospi-feature-stock/services/ml/main.py`

## 구현 세부사항

1. `run()` 함수에서 기존 1시간 결과 업데이트 루프와 함께 `_weekly_retrain_loop()` 코루틴을 병렬 실행:
   ```python
   await asyncio.gather(
       _result_update_loop(db),
       _weekly_retrain_loop(db),
   )
   ```

2. `_weekly_retrain_loop(pool)` 구현:
   - 매 10분마다 현재 시각 확인
   - 일요일 02:00 KST에 학습 실행 (장 미개장 시간)
   - 최근 2년치 데이터로 학습 (rolling window)
   - 학습 완료 후 `/models/lgbm/` 파일 교체 (atomic rename)
   - predictor.load() 재호출로 핫스왑

3. 재학습 조건 체크:
   ```python
   KST = timezone(timedelta(hours=9))
   now = datetime.now(KST)
   if now.weekday() == 6 and now.hour == 2 and not _retrain_done_today:
       await _run_retrain(pool, predictor)
       _retrain_done_today = True
   elif now.weekday() != 6:
       _retrain_done_today = False
   ```

4. `_run_retrain()` 내부에서 `scripts/train_model.py`의 핵심 로직을 직접 호출
   (subprocess 불필요, ml 서비스 내 sys.path에 이미 포함)

## 사이드 이펙트

- 재학습 중 LightGBM 모델 파일 잠금 없음 (별도 tmp 경로로 저장 후 rename)
- 학습 실패 시 기존 모델 유지 (예외 처리로 fallback)

## 완료 기준

- ml service 로그에 매주 일요일 02:00 KST "Weekly retrain started" 로그 출력
- 학습 완료 후 "Weekly retrain done, AUC=..." 로그 출력
- 실패 시 "Weekly retrain failed, keeping existing model" 로그 출력

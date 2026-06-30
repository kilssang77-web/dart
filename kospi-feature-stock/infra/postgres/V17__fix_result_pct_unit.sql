-- V17: result_1d/3d/5d 단위 불일치 수정
-- 원인: services/collector/main.py의 SQL 백필이 * 100 없이 소수(decimal)로 저장
-- 정상 단위: 퍼센트(%) — 예) 5.2 = +5.2%
-- 비정상(소수): 예) 0.052 = +5.2% (이것을 퍼센트로 변환)
--
-- 판별 기준: ABS(result_5d) < 1.0 → 소수 단위 (한국 주식 5일 수익률 100%+ 불가능)
-- 영향: result_1d/3d/5d 전부 동일한 경로로 기록되므로 함께 수정

UPDATE feature_events
SET
    result_1d = CASE WHEN result_1d IS NOT NULL THEN ROUND((result_1d * 100)::NUMERIC, 4) END,
    result_3d = CASE WHEN result_3d IS NOT NULL THEN ROUND((result_3d * 100)::NUMERIC, 4) END,
    result_5d = ROUND((result_5d * 100)::NUMERIC, 4)
WHERE result_5d IS NOT NULL
  AND ABS(result_5d) < 1.0;

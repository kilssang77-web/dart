---
step: 1
title: "Recovery 중복처리 버그 수정 — feature_event_id FK"
relevant_docs: ["SCHEMA.md", "CODING_CONVENTION.md"]
relevant_references: []
---

## 목적

`_recover_missed_events()`가 재시작 때마다 같은 이벤트를 중복 처리하는 버그 수정.
`recommendations.created_at = datetime.now()` 이 `detected_at ± 10분` 윈도우 체크를 통과해 매번 중복 INSERT됨.

## 해결 방식

1. `recommendations` 테이블에 `feature_event_id INTEGER REFERENCES feature_events(id)` 컬럼 추가.
2. `NOT EXISTS` 조건을 시간 범위 → ID 기반으로 교체.
3. `recommender/main.py`:
   - `_save_feature_event()`: 이미 event_id 반환 ✓
   - `run()` loop: event_id를 `_emit()` 에 전달
   - `_recover_missed_events()`: `row["id"]`를 `_emit()`에 전달, NOT EXISTS → feature_event_id 조건
   - `_emit()`: event_id를 `_save()`에 전달
   - `_save()`: `feature_event_id` 컬럼 포함 INSERT

## 기존 시그니처 변경

- `_emit(rec, event, producer)` → `_emit(rec, event, producer, feature_event_id=None)`
- `_save(rec)` → `_save(rec, feature_event_id=None)`
- 기존 데이터는 `feature_event_id = NULL` 허용 (NOT NULL 아님)

## 마이그레이션

`infra/postgres/V3__recommendations_feature_event_id.sql` 생성:
```sql
ALTER TABLE recommendations
  ADD COLUMN IF NOT EXISTS feature_event_id INTEGER REFERENCES feature_events(id);

CREATE INDEX IF NOT EXISTS idx_recommendations_feature_event_id
  ON recommendations(feature_event_id)
  WHERE feature_event_id IS NOT NULL;
```

## SCHEMA.md 업데이트

recommendations 테이블에 feature_event_id 컬럼 추가.

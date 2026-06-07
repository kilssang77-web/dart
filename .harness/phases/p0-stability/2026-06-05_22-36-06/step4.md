---
step: 4
title: "pattern_vector 오류 가시화 + 기존 이벤트 backfill 스크립트"
relevant_docs: ["ARCHITECTURE.md"]
relevant_references: []
---

## 목적

1. `update_pattern_vector()` 내부 오류가 `logger.debug`로 숨겨져 있어 문제 파악 불가
2. 기존 `feature_events.pattern_vector = NULL` 이벤트 backfill 스크립트 없음
3. `_recover_missed_events()`에서 복구된 이벤트도 pattern_vector 생성 누락

## 해결 방식

### 1. `recommender/pattern_vector.py` — 오류 레벨 상향

```python
# AS-IS
except Exception as e:
    logger.debug(f"pattern_vector update error (event_id={event_id}): {e}")

# TO-BE
except Exception as e:
    logger.warning(f"[PatternVector] update failed event_id={event_id} code={code}: {e}")
```

### 2. `recommender/main.py` — 복구 이벤트도 pattern_vector 트리거

`_recover_missed_events()` 내부, rec 생성 후:
```python
# 복구된 이벤트의 pattern_vector가 없으면 생성
asyncio.create_task(update_pattern_vector(self._db, row["id"], row["code"]))
```
(이미 있으면 DB UPDATE가 무해하게 실행됨)

### 3. `scripts/backfill_vectors.py` 신설

기존 NULL 이벤트 일괄 처리:
```python
"""
feature_events.pattern_vector가 NULL인 이벤트에 대해 일괄 벡터 생성.
사용: docker exec -it kospi-recommender python /app/scripts/backfill_vectors.py
또는: python scripts/backfill_vectors.py  (로컬, POSTGRES_DSN 환경변수 필요)
"""
import asyncio, asyncpg, os, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.recommender.pattern_vector import update_pattern_vector

async def main():
    pool = await asyncpg.create_pool(
        dsn=os.environ["POSTGRES_DSN"].replace("+asyncpg",""),
        min_size=2, max_size=5,
    )
    rows = await pool.fetch(
        "SELECT id, code FROM feature_events WHERE pattern_vector IS NULL ORDER BY detected_at DESC"
    )
    logging.info(f"Backfill target: {len(rows)} events")
    ok, fail = 0, 0
    for r in rows:
        result = await update_pattern_vector(pool, r["id"], r["code"])
        if result:
            ok += 1
        else:
            fail += 1
        await asyncio.sleep(0.05)
    logging.info(f"Done: ok={ok}, fail={fail}")
    await pool.close()

asyncio.run(main())
```

스크립트는 Docker 컨테이너 내에서도 실행 가능하도록 절대 경로 처리.

## 사이드 이펙트

- 기존 이벤트에 pattern_vector 생성 → 유사도 검색 활성화
- `update_pattern_vector` 오류가 로그에 나타남 → 필요 시 추가 수정 가능

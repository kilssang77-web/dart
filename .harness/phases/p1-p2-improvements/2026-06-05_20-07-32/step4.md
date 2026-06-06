---
step: 4
title: "P2-5: signal-generated Kafka 토픽 연결"
status: pending
relevant_docs: ["CODING_CONVENTION", "ARCHITECTURE"]
relevant_references: []
---

## 목표

`services/recommender/main.py`에서 BUY 액션 추천 시 `signal-generated` Kafka 토픽에 발행한다.
현재 `recommendation` 토픽만 발행하고 있어 signal-generated 토픽이 dead letter 상태.

## 변경 파일

- `kospi-feature-stock/services/recommender/main.py`

## 구현 세부사항

1. `run()` 메서드에서 producer가 이미 생성되어 있으므로, `_generate()` 결과가 `action == "BUY"`인 경우에만 `signal-generated` 토픽에 추가 발행:

```python
if rec and rec["action"] == "BUY":
    # 기존: recommendation 토픽 발행
    await producer.send("recommendation", value=rec, key=event["code"])
    # 추가: signal-generated 토픽 발행 (간결한 신호 포맷)
    await producer.send(
        "signal-generated",
        value={
            "code":         rec["code"],
            "created_at":   rec["created_at"],
            "action":       rec["action"],
            "entry_price":  rec["entry_price"],
            "target_price": rec["target_price"],
            "stop_loss_price": rec["stop_loss_price"],
            "success_prob": rec["success_prob"],
            "risk_score":   rec["risk_score"],
        },
        key=event["code"],
    )
    await self._save(rec)
    await self._publish_redis(rec)
    await self._redis.publish("channel:features", orjson.dumps(event).decode())
else:
    # WAIT/SKIP은 recommendation만 저장
    if rec:
        await self._save(rec)
```

2. WAIT/SKIP 추천도 DB에 저장하되 signal-generated에는 발행하지 않음

## 사이드 이펙트

- signal-generated 토픽을 소비하는 소비자가 없어도 문제없음 (토픽에 쌓임)
- 향후 알림 서비스 구축 시 signal-generated 토픽 소비만 하면 됨

## 완료 기준

- BUY 추천 발생 시 signal-generated Kafka 토픽에 메시지 발행됨
- WAIT/SKIP은 signal-generated 발행 안 됨
- 기존 recommendation 토픽 발행 동작 유지

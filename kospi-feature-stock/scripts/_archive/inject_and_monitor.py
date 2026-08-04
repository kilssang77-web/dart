"""
Kafka 신호 주입 + 탐지 결과 모니터링 스크립트.
실제 Redis 통계값을 읽어 탐지 룰이 발동할 데이터를 Kafka에 주입하고
feature-detected 토픽에서 탐지 신호를 수신합니다.

사용: docker exec fstock-collector python /app/scripts/inject_and_monitor.py
"""
import asyncio
import os
import sys
import json
from datetime import datetime

sys.path.insert(0, "/app")

from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
import orjson
import redis.asyncio as redis_lib

BOOTSTRAP = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
TEST_CODE  = "005930"   # 삼성전자
WAIT_SEC   = 15         # 신호 수신 대기 시간

G = "\033[92m"
R = "\033[91m"
Y = "\033[93m"
B = "\033[94m"
W = "\033[97m"
E = "\033[0m"


async def rget_float(redis, key: str) -> float:
    v = await redis.get(key)
    return float(v) if v else 0.0


async def rget_int(redis, key: str) -> int:
    v = await redis.get(key)
    return int(float(v)) if v else 0


async def publish(producer: AIOKafkaProducer, topic: str, data: dict, key: str = ""):
    value = orjson.dumps(data)
    k     = key.encode() if key else None
    await producer.send_and_wait(topic, value=value, key=k)
    print(f"  {B}→ [{topic}]{E} {json.dumps(data, ensure_ascii=False)[:120]}")


async def inject_test_data(producer: AIOKafkaProducer, redis):
    """각 탐지 룰을 발동시킬 데이터를 Kafka 토픽에 주입"""

    avg_vol = await rget_float(redis, f"stats:{TEST_CODE}:avg_vol_20d")
    avg_amt = await rget_float(redis, f"stats:{TEST_CODE}:avg_amount_20d")
    high_20d = await rget_int(redis, f"stats:{TEST_CODE}:high_20d")
    avg_f   = await rget_float(redis, f"stats:{TEST_CODE}:avg_foreign_20d")
    avg_i   = await rget_float(redis, f"stats:{TEST_CODE}:avg_inst_20d")

    print(f"\n{W}▶ Redis 통계 확인{E}")
    print(f"  avg_vol_20d    = {avg_vol:>15,.0f}")
    print(f"  avg_amount_20d = {avg_amt:>15,.0f}")
    print(f"  high_20d       = {high_20d:>15,}")
    print(f"  avg_foreign_20d= {avg_f:>15,.0f}")
    print(f"  avg_inst_20d   = {avg_i:>15,.0f}")

    now_str = datetime.now().strftime("%Y%m%d%H%M%S")
    print(f"\n{W}▶ Kafka 데이터 주입{E}")

    # 1) VolumeSurge — minute-bar 토픽 (6x volume)
    await publish(producer, "minute-bar", {
        "code": TEST_CODE,
        "bars": [{
            "code": TEST_CODE, "time": now_str,
            "open": 79000, "high": 80500, "low": 78800, "close": 80000,
            "volume": int(avg_vol * 6.5) if avg_vol > 0 else 200_000_000,
            "amount": int(avg_amt * 6.5) if avg_amt > 0 else 60_000_000_000_000,
            "change_rate": 4.5,
            "volume_ratio": 6.5,
        }],
    }, key=TEST_CODE)

    # 2) Breakout — tick-data 토픽 (20일 신고가 +1%)
    brk_price = int(high_20d * 1.01) if high_20d > 0 else 365_000
    await publish(producer, "tick-data", {
        "code": TEST_CODE, "price": brk_price,
        "change_rate": 3.2, "volume": 1_500_000, "amount": 5_000_000_000,
        "is_buy": True,
    }, key=TEST_CODE)

    # 3) VI — tick-data 토픽 (12% 급등)
    await redis.delete(f"vi:{TEST_CODE}:triggered")   # 중복 방지 키 초기화
    await publish(producer, "tick-data", {
        "code": TEST_CODE, "price": 90000,
        "change_rate": 12.5, "volume": 3_000_000, "amount": 8_000_000_000,
        "is_buy": True,
    }, key=TEST_CODE)

    # 4) LONG_WHITE_CANDLE — minute-bar 토픽 (강한 양봉)
    await publish(producer, "minute-bar", {
        "code": TEST_CODE,
        "bars": [{
            "code": TEST_CODE, "time": now_str,
            "open": 75000, "high": 80500, "low": 74800, "close": 80200,
            "volume": 5_000_000, "amount": 3_000_000_000,
            "change_rate": 7.0, "volume_ratio": 1.8,
        }],
    }, key=TEST_CODE)

    # 5) HAMMER_CANDLE — minute-bar 토픽 (망치형)
    await publish(producer, "minute-bar", {
        "code": TEST_CODE,
        "bars": [{
            "code": TEST_CODE, "time": now_str,
            "open": 78000, "high": 78200, "low": 71800, "close": 78200,
            "volume": 2_000_000, "amount": 1_500_000_000,
            "change_rate": 0.5, "volume_ratio": 1.0,
        }],
    }, key=TEST_CODE)

    # 6) SupplyAnomaly — supply-demand 토픽 (외국인 6x)
    if avg_f != 0:
        await publish(producer, "supply-demand", {
            "code": TEST_CODE,
            "foreign_net": int(abs(avg_f) * 6 + 1),
            "inst_net": int(abs(avg_i) * 3 + 1) if avg_i != 0 else 0,
            "indiv_net": 0, "prog_arbitrage_net": 0,
        }, key=TEST_CODE)

    # 7) PostDisclosure — disclosure 먼저 → 이후 tick
    await publish(producer, "disclosure", {
        "code": TEST_CODE, "rcept_no": "TEST001",
        "title": "삼성전자 대규모 수주 공시",
        "category": "favorable",
        "corp_name": "삼성전자",
        "disclosed_at": datetime.now().isoformat(),
    }, key=TEST_CODE)

    await asyncio.sleep(1)  # disclosure 처리 대기

    await publish(producer, "tick-data", {
        "code": TEST_CODE, "price": 82000,
        "change_rate": 5.0, "volume": 2_000_000, "amount": 4_000_000_000,
        "is_buy": True,
    }, key=TEST_CODE)

    print(f"\n  {G}총 8개 이벤트 주입 완료{E}")


async def monitor_signals(timeout: int) -> list[dict]:
    """feature-detected 토픽에서 신호 수신"""
    consumer = AIOKafkaConsumer(
        "feature-detected",
        bootstrap_servers=BOOTSTRAP,
        group_id="test-monitor-group",
        auto_offset_reset="latest",
        value_deserializer=lambda v: orjson.loads(v),
        consumer_timeout_ms=timeout * 1000,
    )
    await consumer.start()

    signals = []
    print(f"\n{W}▶ feature-detected 토픽 모니터링 ({timeout}초){E}")
    try:
        async for msg in consumer:
            sig = msg.value
            et  = sig.get("event_type", "?")
            sc  = sig.get("signal_score", 0)
            cd  = sig.get("code", "?")
            print(f"  {G}[SIGNAL]{E} {W}{cd}{E} {Y}{et:<30}{E} score={G}{sc:.3f}{E}  "
                  f"data={json.dumps(sig.get('signal_data', {}), ensure_ascii=False)[:80]}")
            signals.append(sig)
    except Exception:
        pass
    finally:
        await consumer.stop()
    return signals


async def main():
    redis    = redis_lib.from_url(os.environ["REDIS_URL"])

    producer = AIOKafkaProducer(
        bootstrap_servers=BOOTSTRAP,
        value_serializer=lambda v: v,
        key_serializer=lambda k: k,
        acks="all",
    )
    await producer.start()

    print()
    print("=" * 70)
    print(f"  {W}Kafka 탐지 파이프라인 End-to-End 테스트{E}")
    print(f"  종목: 삼성전자({TEST_CODE})  |  대기: {WAIT_SEC}초")
    print("=" * 70)

    # 모니터링 시작 후 주입 (순서 중요)
    monitor_task = asyncio.create_task(monitor_signals(WAIT_SEC))
    await asyncio.sleep(1)   # consumer가 join하기 전에 주입되면 못 받음

    await inject_test_data(producer, redis)

    print(f"\n  {B}detector 처리 대기 중...{E}")
    signals = await monitor_task

    await producer.stop()
    await redis.aclose()

    # 집계
    print()
    print("=" * 70)
    event_types = [s.get("event_type") for s in signals]
    expected = [
        "VOLUME_SURGE", "AMOUNT_SURGE", "BREAKOUT_20D",
        "VI_TRIGGERED", "LONG_WHITE_CANDLE", "HAMMER_CANDLE",
        "SUPPLY_ANOMALY", "POST_DISCLOSURE_SURGE",
    ]
    print(f"  수신 신호: {len(signals)}개")
    for et in expected:
        ok = et in event_types
        tag = f"{G}✓{E}" if ok else f"{R}✗{E}"
        print(f"    {tag} {et}")
    missing = [e for e in expected if e not in event_types]
    extra   = [e for e in event_types if e not in expected]
    if extra:
        print(f"  추가 수신: {extra}")
    print()
    if missing:
        print(f"  {R}미수신: {missing}{E}")
        rc = 1
    else:
        print(f"  {G}모든 탐지 룰 신호 수신 완료!{E}")
        rc = 0
    print("=" * 70)
    print()
    sys.exit(rc)


if __name__ == "__main__":
    asyncio.run(main())

"""
탐지 룰 통합 테스트 스크립트.
Redis에 실제 저장된 통계값을 읽어 각 룰이 정상 발동하는지 확인합니다.

사용: docker exec fstock-detector python /app/scripts/test_detection_rules.py
"""
import asyncio
import os
import sys

sys.path.insert(0, "/app")

import redis.asyncio as redis_lib
from rules.volume_surge import VolumeSurgeDetector
from rules.amount_surge import AmountSurgeDetector
from rules.breakout import BreakoutDetector
from rules.candlestick import CandlestickDetector
from rules.vi_detector import VIDetector
from rules.supply_anomaly import SupplyAnomalyDetector
from rules.post_disclosure import PostDisclosureDetector

import logging
logging.basicConfig(level=logging.WARNING)

TEST_CODE = "005930"  # 삼성전자

G = "\033[92mPASS\033[0m"
R = "\033[91mFAIL\033[0m"
Y = "\033[93mSKIP\033[0m"
B = "\033[94mINFO\033[0m"

results: list[tuple[str, bool | None]] = []


def report(name: str, ok: bool | None, detail: str = "") -> None:
    tag = G if ok is True else (Y if ok is None else R)
    print(f"  [{tag}] {name:<48} {detail}")
    results.append((name, ok))


async def rget_float(redis, key: str) -> float:
    v = await redis.get(key)
    return float(v) if v else 0.0


async def rget_int(redis, key: str) -> int:
    v = await redis.get(key)
    return int(float(v)) if v else 0


# ── 1. VolumeSurge ─────────────────────────────────────────────────────────────
async def test_volume_surge(redis):
    det = VolumeSurgeDetector(redis)
    avg = await rget_float(redis, f"stats:{TEST_CODE}:avg_vol_20d")
    print(f"  [{B}] avg_vol_20d = {avg:,.0f}")

    if avg <= 0:
        report("VolumeSurge — Redis 키 없음", None, "avg_vol_20d 미존재")
        return

    bar6x = {"code": TEST_CODE, "close": 80000, "change_rate": 4.0,
              "volume": int(avg * 6), "amount": 10_000_000_000}
    sig = await det.detect(bar6x)
    report("6x 볼륨 → 발동",
           sig is not None,
           f"score={sig.signal_score:.3f} ratio={sig.volume_ratio}x" if sig else "신호 없음")

    bar2x = {**bar6x, "volume": int(avg * 2)}
    sig_no = await det.detect(bar2x)
    report("2x 볼륨 → 미발동",
           sig_no is None,
           "정상" if sig_no is None else f"오발동 score={sig_no.signal_score:.3f}")

    bar_low_amt = {**bar6x, "amount": 500_000_000}
    sig_lamt = await det.detect(bar_low_amt)
    report("amount 미달 → 미발동",
           sig_lamt is None,
           "정상" if sig_lamt is None else "오발동")


# ── 2. AmountSurge ─────────────────────────────────────────────────────────────
async def test_amount_surge(redis):
    det = AmountSurgeDetector(redis)
    avg = await rget_float(redis, f"stats:{TEST_CODE}:avg_amount_20d")
    print(f"  [{B}] avg_amount_20d = {avg:,.0f}")

    if avg <= 0:
        report("AmountSurge — Redis 키 없음", None, "avg_amount_20d 미존재")
        return

    bar6x = {"code": TEST_CODE, "close": 80000, "change_rate": 3.0,
              "volume": 5_000_000, "amount": int(avg * 6)}
    sig = await det.detect(bar6x)
    report("6x 거래대금 → 발동",
           sig is not None,
           f"score={sig.signal_score:.3f} ratio={sig.amount_ratio}x" if sig else "신호 없음")

    bar2x = {**bar6x, "amount": int(avg * 2)}
    sig_no = await det.detect(bar2x)
    report("2x 거래대금 → 미발동",
           sig_no is None,
           "정상" if sig_no is None else f"오발동 score={sig_no.signal_score:.3f}")


# ── 3. Breakout ────────────────────────────────────────────────────────────────
async def test_breakout(redis):
    det = BreakoutDetector(redis)
    h20  = await rget_int(redis, f"stats:{TEST_CODE}:high_20d")
    h52w = await rget_int(redis, f"stats:{TEST_CODE}:high_260d")
    print(f"  [{B}] high_20d={h20:,}  high_52w={h52w:,}")

    if h20 <= 0:
        report("Breakout — Redis 키 없음", None, "high_20d 미존재")
        return

    tick_hit = {"code": TEST_CODE, "price": int(h20 * 1.005), "change_rate": 1.0}
    sigs = await det.detect(tick_hit)
    report("20일 신고가 0.5% 돌파 → 발동",
           len(sigs) > 0,
           f"event={sigs[0].event_type} score={sigs[0].signal_score:.3f}" if sigs else "신호 없음")

    tick_miss = {"code": TEST_CODE, "price": int(h20 * 0.995), "change_rate": -0.5}
    sigs_no = await det.detect(tick_miss)
    report("신고가 미달 → 미발동",
           len(sigs_no) == 0,
           "정상" if not sigs_no else f"오발동: {sigs_no[0].event_type}")

    if h52w > 0:
        tick_52w = {"code": TEST_CODE, "price": int(h52w * 1.002), "change_rate": 2.0}
        sigs_52w = await det.detect(tick_52w)
        report("52주 신고가 0.2% 돌파 → 발동",
               len(sigs_52w) > 0,
               f"event={sigs_52w[0].event_type} score={sigs_52w[0].signal_score:.3f}" if sigs_52w else "신호 없음")


# ── 4. Candlestick ─────────────────────────────────────────────────────────────
async def test_candlestick():
    det = CandlestickDetector()

    # 강한 양봉: body_ratio ≈ 0.91, change_rate ≈ 6.7%
    bar_lw = {"code": TEST_CODE, "open": 75000, "high": 80500,
               "low": 74800, "close": 80000, "change_rate": 6.7,
               "volume_ratio": 1.8}
    fired_lw = det.detect_long_white_candle(bar_lw)
    score_lw = det.long_white_score(bar_lw)
    report("강한 양봉 (body≈91%, 6.7%) → 발동",
           fired_lw,
           f"score={score_lw:.3f}" if fired_lw else "미발동")

    # 약한 양봉: change_rate 1.3%, body 낮음
    bar_weak = {"code": TEST_CODE, "open": 75000, "high": 80000,
                "low": 70000, "close": 76000, "change_rate": 1.3,
                "volume_ratio": 0.9}
    fired_weak = det.detect_long_white_candle(bar_weak)
    report("약한 양봉 (1.3%) → 미발동",
           not fired_weak,
           "정상" if not fired_weak else "오발동")

    # 망치형: lower_shadow = 6000, body = 200 → ratio = 30x
    bar_h = {"code": TEST_CODE, "open": 78000, "high": 78200,
              "low": 71800, "close": 78200, "change_rate": 0.3,
              "volume_ratio": 1.0}
    fired_h = det.detect_hammer(bar_h)
    score_h = det.hammer_score(bar_h)
    report("망치형 (꼬리30x) → 발동",
           fired_h,
           f"score={score_h:.3f}" if fired_h else "미발동")

    # 망치형 아님: upper_shadow 큼
    bar_not_h = {"code": TEST_CODE, "open": 78000, "high": 82000,
                  "low": 75000, "close": 78200, "change_rate": 0.3,
                  "volume_ratio": 1.0}
    fired_not_h = det.detect_hammer(bar_not_h)
    report("상단 꼬리 큰 봉 → 미발동",
           not fired_not_h,
           "정상" if not fired_not_h else "오발동")


# ── 5. VI Detector ─────────────────────────────────────────────────────────────
async def test_vi_detector(redis):
    det = VIDetector(redis)
    await redis.delete(f"vi:{TEST_CODE}:triggered")

    tick_vi = {"code": TEST_CODE, "price": 88000,
               "change_rate": 12.0, "volume": 1_000_000, "amount": 5_000_000_000}
    sig = await det.detect(tick_vi)
    report("12% 급등 → 발동",
           sig is not None,
           f"score={sig['signal_score']:.3f}" if sig else "신호 없음")

    sig2 = await det.detect(tick_vi)
    report("동일 종목 중복 발동 방지",
           sig2 is None,
           "중복 차단됨" if sig2 is None else "오발동(중복)")

    await redis.delete(f"vi:{TEST_CODE}:triggered")
    tick_low = {**tick_vi, "change_rate": 5.0}
    sig_no = await det.detect(tick_low)
    report("5% 상승 → 미발동",
           sig_no is None,
           "정상" if sig_no is None else f"오발동 score={sig_no['signal_score']:.3f}")

    await redis.delete(f"vi:{TEST_CODE}:triggered")


# ── 6. SupplyAnomaly ───────────────────────────────────────────────────────────
async def test_supply_anomaly(redis):
    det = SupplyAnomalyDetector(redis)
    avg_f = await rget_float(redis, f"stats:{TEST_CODE}:avg_foreign_20d")
    avg_i = await rget_float(redis, f"stats:{TEST_CODE}:avg_inst_20d")
    print(f"  [{B}] avg_foreign_20d={avg_f:,.0f}  avg_inst_20d={avg_i:,.0f}")

    if avg_f == 0 and avg_i == 0:
        report("SupplyAnomaly — 수급 통계 없음 → 스킵", None,
               "수급 데이터 미수집 (장 중 REST 호출 필요)")
        return

    # 외국인 6배 순매수 (avg_f가 음수여도 abs로 사용)
    sd_foreign = {"code": TEST_CODE,
                  "foreign_net": int(abs(avg_f) * 6 + 1),
                  "inst_net": 0, "indiv_net": 0, "prog_arbitrage_net": 0}
    sig_f = await det.detect(sd_foreign)
    report("외국인 6x 순매수 → 발동",
           sig_f is not None,
           f"score={sig_f['signal_score']:.3f}" if sig_f else "신호 없음")

    # 외국인+기관 동시 매수
    if avg_i != 0:
        sd_dual = {"code": TEST_CODE,
                   "foreign_net": int(abs(avg_f) * 3 + 1),
                   "inst_net":    int(abs(avg_i) * 3 + 1),
                   "indiv_net": 0, "prog_arbitrage_net": 0}
        sig_d = await det.detect(sd_dual)
        report("외국인+기관 동시 3x → 발동",
               sig_d is not None,
               f"score={sig_d['signal_score']:.3f}" if sig_d else "신호 없음")

    # 미달
    sd_no = {"code": TEST_CODE, "foreign_net": int(abs(avg_f) * 1),
             "inst_net": 0, "indiv_net": 0, "prog_arbitrage_net": 0}
    sig_no = await det.detect(sd_no)
    report("1x 수급 → 미발동",
           sig_no is None,
           "정상" if sig_no is None else f"오발동 {sig_no['signal_data']}")


# ── 7. PostDisclosure ──────────────────────────────────────────────────────────
async def test_post_disclosure(redis):
    det = PostDisclosureDetector(redis)

    # 공시 플래그 심기 (favorable만 mark됨 — 직접 key 세팅)
    await redis.setex(f"disclosure:recent:{TEST_CODE}", 3600, "favorable")

    tick = {"code": TEST_CODE, "price": 82000,
            "change_rate": 5.0, "volume": 3_000_000, "amount": 5_000_000_000}
    sig = await det.detect(tick)
    report("공시 플래그 + 5% 급등 → 발동",
           sig is not None,
           f"score={sig['signal_score']:.3f}" if sig else "신호 없음")

    # 공시 플래그 없음
    await redis.delete(f"disclosure:recent:{TEST_CODE}")
    sig_no = await det.detect(tick)
    report("공시 플래그 없음 → 미발동",
           sig_no is None,
           "정상" if sig_no is None else "오발동")

    # change_rate 미달
    await redis.setex(f"disclosure:recent:{TEST_CODE}", 3600, "favorable")
    sig_low = await det.detect({**tick, "change_rate": 1.5})
    report("공시 있지만 1.5% → 미발동",
           sig_low is None,
           "정상" if sig_low is None else "오발동")

    await redis.delete(f"disclosure:recent:{TEST_CODE}")


# ── 메인 ───────────────────────────────────────────────────────────────────────
async def main():
    redis = redis_lib.from_url(os.environ["REDIS_URL"])
    print()
    print("=" * 65)
    print(f"  탐지 룰 통합 테스트  (종목: 삼성전자 {TEST_CODE})")
    print("=" * 65)

    print("\n▶ [1] 거래량 급증 (VolumeSurge)")
    await test_volume_surge(redis)

    print("\n▶ [2] 거래대금 급증 (AmountSurge)")
    await test_amount_surge(redis)

    print("\n▶ [3] 신고가 돌파 (Breakout)")
    await test_breakout(redis)

    print("\n▶ [4] 캔들스틱 패턴 (Candlestick)")
    await test_candlestick()

    print("\n▶ [5] 변동성 완화장치 (VI Detector)")
    await test_vi_detector(redis)

    print("\n▶ [6] 수급 이상 (SupplyAnomaly)")
    await test_supply_anomaly(redis)

    print("\n▶ [7] 공시 후 급등 (PostDisclosure)")
    await test_post_disclosure(redis)

    total   = len(results)
    passed  = sum(1 for _, ok in results if ok is True)
    failed  = sum(1 for _, ok in results if ok is False)
    skipped = sum(1 for _, ok in results if ok is None)

    print()
    print("=" * 65)
    color = "\033[92m" if failed == 0 else "\033[91m"
    print(f"  {color}결과: {passed} 통과 / {failed} 실패 / {skipped} 스킵  (총 {total}건)\033[0m")
    print("=" * 65)
    print()

    await redis.aclose()
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    asyncio.run(main())

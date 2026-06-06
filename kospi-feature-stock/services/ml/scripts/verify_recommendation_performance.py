#!/usr/bin/env python3
"""
추천 성공률 검증 스크립트.
result_1d/3d/5d가 채워진 추천 건의 통계를 출력.

사용법:
  python verify_recommendation_performance.py --since 2025-01-01
"""
import argparse
import asyncio
import logging
import os

import asyncpg
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify_rec")


async def main(args):
    pool = await asyncpg.create_pool(
        dsn=os.environ["POSTGRES_DSN"].replace("+asyncpg", ""),
        min_size=2, max_size=5,
    )
    rows = await pool.fetch(
        """
        SELECT r.action, r.success_prob, r.risk_score,
               r.target_price, r.stop_loss_price, r.entry_price,
               fe.result_1d, fe.result_3d, fe.result_5d,
               fe.event_type, r.created_at::date AS rec_date
        FROM recommendations r
        JOIN feature_events fe ON fe.id = r.feature_event_id
        WHERE r.action = 'BUY'
          AND r.created_at >= $1::date
          AND fe.result_5d IS NOT NULL
        ORDER BY r.created_at DESC
        """,
        args.since,
    )
    await pool.close()

    if not rows:
        logger.warning("결과 없음. result_5d 데이터가 쌓이는 데 최소 5 영업일 필요")
        return

    data = [dict(r) for r in rows]
    r5  = np.array([d["result_5d"] for d in data], dtype=float)
    r3  = np.array([d["result_3d"] for d in data if d["result_3d"] is not None], dtype=float)
    r1  = np.array([d["result_1d"] for d in data if d["result_1d"] is not None], dtype=float)
    probs = np.array([d["success_prob"] for d in data], dtype=float)

    wins5  = (r5 >= 5.0).sum()
    loss5  = (r5 <= -5.0).sum()
    total  = len(r5)

    # 예상 vs 실제 성공률 캘리브레이션
    prob_bins  = np.percentile(probs, [0,25,50,75,100])
    print(f"""
╔═══════════════════════════════════════════════════════════╗
║           추천 성과 검증 리포트                             ║
╠═══════════════════════════════════════════════════════════╣
║ 기간       : {args.since} ~ 현재                           ║
║ 총 BUY 추천: {total:>4}건                                       ║
╠═══════════════════════════════════════════════════════════╣
║ [5일 수익률]                                               ║
║   평균     : {r5.mean():>6.2f}%                                ║
║   중앙값   : {np.median(r5):>6.2f}%                                ║
║   표준편차 : {r5.std():>6.2f}%                                ║
║   승률(≥5%): {wins5}/{total} = {wins5/total*100:.1f}%                    ║
║   손실(≤-5%): {loss5}/{total} = {loss5/total*100:.1f}%                   ║
╠═══════════════════════════════════════════════════════════╣
║ [보유 기간별 수익률]                                        ║
║   1일후    : {r1.mean():>6.2f}% (n={len(r1)})                       ║
║   3일후    : {r3.mean():>6.2f}% (n={len(r3)})                       ║
║   5일후    : {r5.mean():>6.2f}% (n={total})                       ║
╠═══════════════════════════════════════════════════════════╣
║ [모델 확률 캘리브레이션]                                     ║
║   예상 성공확률 평균: {probs.mean():.3f}                           ║
║   실제 승률(5%):      {wins5/total:.3f}                           ║
║   캘리브레이션 오차:  {abs(probs.mean()-wins5/total):.3f}                           ║
╚═══════════════════════════════════════════════════════════╝
""")

    # 이벤트 타입별 분석
    from collections import defaultdict
    by_event = defaultdict(list)
    for d in data:
        by_event[d["event_type"]].append(float(d["result_5d"]))

    print("이벤트 타입별 5일 수익률:")
    print(f"{'이벤트타입':<25} {'건수':>5} {'평균':>7} {'승률':>7}")
    print("-" * 50)
    for et, rets in sorted(by_event.items(), key=lambda x: -len(x[1])):
        arr = np.array(rets)
        print(f"{et:<25} {len(arr):>5} {arr.mean():>6.2f}% {(arr>=5.0).mean()*100:>6.1f}%")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default="2025-01-01")
    asyncio.run(main(parser.parse_args()))

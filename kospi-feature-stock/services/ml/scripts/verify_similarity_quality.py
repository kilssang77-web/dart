#!/usr/bin/env python3
"""
유사사례 검색 품질 검증 스크립트.

각 feature_event의 패턴 벡터로 유사사례를 검색하고
유사도 분포, 평균수익률, 표준편차를 출력한다.

사용법:
  python verify_similarity_quality.py --limit 100 --top-k 20
"""
import argparse
import asyncio
import logging
import os
import sys

import asyncpg
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("verify_sim")


async def main(args):
    pool = await asyncpg.create_pool(
        dsn=os.environ["POSTGRES_DSN"].replace("+asyncpg", ""),
        min_size=2, max_size=5,
    )

    # 패턴 벡터가 있고 result_5d가 있는 이벤트 샘플링
    anchors = await pool.fetch(
        """
        SELECT id, code, event_type, pattern_vector, result_5d
        FROM feature_events
        WHERE pattern_vector IS NOT NULL AND result_5d IS NOT NULL
        ORDER BY detected_at DESC
        LIMIT $1
        """,
        args.limit,
    )
    logger.info(f"Anchor events: {len(anchors)}")

    all_sims, all_rets, all_counts = [], [], []

    for anchor in anchors:
        vec = anchor["pattern_vector"]
        code = anchor["code"]

        # HNSW ANN 검색
        neighbors = await pool.fetch(
            """
            SELECT
                ROUND((1 - (pattern_vector <=> $1::vector))::NUMERIC, 4) AS sim,
                result_5d
            FROM feature_events
            WHERE code != $2
              AND pattern_vector IS NOT NULL
              AND result_5d IS NOT NULL
            ORDER BY pattern_vector <=> $1::vector
            LIMIT $3
            """,
            vec, code, args.top_k,
        )

        if not neighbors:
            continue

        sims = [float(r["sim"]) for r in neighbors]
        rets = [float(r["result_5d"]) for r in neighbors]

        all_sims.extend(sims)
        all_rets.extend(rets)
        all_counts.append(len(neighbors))

    await pool.close()

    if not all_sims:
        logger.error("No results. 패턴 벡터가 충분하지 않거나 result_5d 데이터 부족")
        return

    sims_arr = np.array(all_sims)
    rets_arr = np.array(all_rets)
    high_sim = sims_arr >= 0.80
    mid_sim  = (sims_arr >= 0.60) & (sims_arr < 0.80)

    print(f"""
╔═══════════════════════════════════════════════════════════╗
║           유사사례 검색 품질 검증 결과                      ║
╠═══════════════════════════════════════════════════════════╣
║ 분석 앵커 이벤트 수  : {len(anchors):>6}                        ║
║ 총 이웃 이벤트 수    : {len(all_sims):>6}                        ║
║ 평균 이웃 수         : {np.mean(all_counts):>6.1f}                        ║
╠═══════════════════════════════════════════════════════════╣
║ [유사도 분포]                                              ║
║   평균   : {sims_arr.mean():.4f}                                   ║
║   중앙값 : {np.median(sims_arr):.4f}                                   ║
║   최고   : {sims_arr.max():.4f}                                   ║
║   최저   : {sims_arr.min():.4f}                                   ║
║   >0.8   : {high_sim.sum():>6}건 ({high_sim.mean()*100:.1f}%)              ║
║   0.6~0.8: {mid_sim.sum():>6}건 ({mid_sim.mean()*100:.1f}%)              ║
╠═══════════════════════════════════════════════════════════╣
║ [전체 이웃 수익률]                                          ║
║   평균수익률 : {rets_arr.mean():>6.2f}%                              ║
║   표준편차   : {rets_arr.std():>6.2f}%                              ║
║   승률(>=5%) : {(rets_arr>=5.0).mean()*100:>5.1f}%                              ║
╠═══════════════════════════════════════════════════════════╣
║ [유사도 ≥0.80 이웃 수익률]                                  ║""")
    if high_sim.any():
        hr = rets_arr[high_sim]
        print(f"║   평균수익률 : {hr.mean():>6.2f}%                              ║")
        print(f"║   표준편차   : {hr.std():>6.2f}%                              ║")
        print(f"║   승률(>=5%) : {(hr>=5.0).mean()*100:>5.1f}%                              ║")
    else:
        print("║   해당 이웃 없음                                           ║")
    print("╚═══════════════════════════════════════════════════════════╝")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit",  type=int, default=100, help="분석할 앵커 이벤트 수")
    parser.add_argument("--top-k",  type=int, default=20,  help="이웃 검색 수")
    asyncio.run(main(parser.parse_args()))

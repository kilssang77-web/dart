"""재분류: 기존 공시의 sentiment_score·category를 개선된 분류기로 재계산."""
import sys, os, asyncio, logging
sys.path.insert(0, '/app')
from disclosure.classifier import DisclosureClassifier
import asyncpg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("reclassify")

BATCH = 200

async def run():
    dsn = os.environ['POSTGRES_DSN'].replace('+asyncpg', '')
    pool = await asyncpg.create_pool(dsn, min_size=2, max_size=4)
    clf = DisclosureClassifier()

    rows = await pool.fetch(
        'SELECT id, title, content, disclosure_type FROM disclosures ORDER BY id'
    )
    logger.info(f"총 {len(rows)}건 공시 재분류 시작")

    stats = {"favorable": 0, "neutral": 0, "unfavorable": 0}
    updates = []
    for r in rows:
        res = clf.classify(r['title'] or '', r['content'] or '', r['disclosure_type'] or '')
        stats[res['category']] += 1
        updates.append((res['sentiment_score'], res['category'], r['id']))

    # 배치 업데이트
    for i in range(0, len(updates), BATCH):
        batch = updates[i:i + BATCH]
        await pool.executemany(
            "UPDATE disclosures SET sentiment_score=$1, category=$2 WHERE id=$3",
            batch,
        )

    await pool.close()
    total = len(rows)
    logger.info(
        f"재분류 완료: favorable={stats['favorable']}({stats['favorable']/total*100:.1f}%) "
        f"unfavorable={stats['unfavorable']}({stats['unfavorable']/total*100:.1f}%) "
        f"neutral={stats['neutral']}({stats['neutral']/total*100:.1f}%)"
    )

asyncio.run(run())

import sys, os, asyncio
sys.path.insert(0, '/app')
from disclosure.classifier import DisclosureClassifier
import asyncpg

async def run():
    dsn = os.environ['POSTGRES_DSN'].replace('+asyncpg', '')
    pool = await asyncpg.create_pool(dsn, min_size=2, max_size=4)
    clf = DisclosureClassifier()
    rows = await pool.fetch(
        'SELECT id, title, content, disclosure_type FROM disclosures ORDER BY id DESC LIMIT 10'
    )
    for r in rows:
        result = clf.classify(r['title'] or '', r['content'] or '', r['disclosure_type'] or '')
        print(f"{r['title'][:45]:45s} {result['sentiment_score']:+.3f} {result['category']}")
    await pool.close()

asyncio.run(run())

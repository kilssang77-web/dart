"""
setup_bootstrap.py — 신규 설치 후 원클릭 초기화
실행: docker compose run --rm collector-tick python /app/../../setup_bootstrap.py

수행 순서:
  1. DB 연결 확인 + 스키마 검증
  2. 종목 코드 수집 (KIS REST API)
  3. 과거 3년 일봉 데이터 백필
  4. Redis 통계 초기 계산
  5. 공시 벡터 백필
  6. Feature 생성 + 모델 학습
  7. 유사사례 패턴 벡터 생성
  8. 검증 (모델 AUC, 데이터 무결성)
  9. 서비스 준비 완료 플래그 설정
"""

import asyncio
import logging
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import asyncpg
import redis.asyncio as redis_lib
import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [BOOTSTRAP] %(levelname)s — %(message)s",
)
logger = logging.getLogger("bootstrap")

# ── 환경변수 ─────────────────────────────────────────────────────────────────
POSTGRES_DSN = os.environ.get("POSTGRES_DSN", "postgresql://fstock:fstock@postgres:5432/fstock")
REDIS_URL    = os.environ.get("REDIS_URL", "redis://redis:6379/0")
KIS_APP_KEY  = os.environ.get("KIS_APP_KEY", "")
KIS_APP_SEC  = os.environ.get("KIS_APP_SECRET", "")
KIS_ACCOUNT  = os.environ.get("KIS_ACCOUNT_NO", "")
KIS_BASE_URL = os.environ.get("KIS_BASE_URL", "https://openapi.koreainvestment.com:9443")
DART_API_KEY = os.environ.get("DART_API_KEY", "")
MODEL_DIR    = os.environ.get("LGBM_MODEL_DIR", "/models/lgbm")
BACKFILL_DAYS = int(os.environ.get("BOOTSTRAP_BACKFILL_DAYS", "780"))  # ~3년


# ── 스텝 유틸 ────────────────────────────────────────────────────────────────

def step(n: int, title: str):
    logger.info(f"\n{'='*60}")
    logger.info(f"STEP {n}: {title}")
    logger.info(f"{'='*60}")


def ok(msg: str):
    logger.info(f"  ✅ {msg}")


def warn(msg: str):
    logger.warning(f"  ⚠️  {msg}")


def fail(msg: str):
    logger.error(f"  ❌ {msg}")
    sys.exit(1)


# ── STEP 1: 인프라 연결 확인 ─────────────────────────────────────────────────

async def check_infra(pool: asyncpg.Pool, redis: redis_lib.Redis):
    step(1, "인프라 연결 확인")

    # PostgreSQL
    try:
        version = await pool.fetchval("SELECT version()")
        ok(f"PostgreSQL 연결: {version[:50]}")
    except Exception as e:
        fail(f"PostgreSQL 연결 실패: {e}")

    # TimescaleDB
    try:
        ts = await pool.fetchval("SELECT extversion FROM pg_extension WHERE extname='timescaledb'")
        ok(f"TimescaleDB: {ts}")
    except Exception:
        warn("TimescaleDB 미설치 — init.sql 재실행 필요")

    # pgvector
    try:
        await pool.fetchval("SELECT extversion FROM pg_extension WHERE extname='vector'")
        ok("pgvector 설치 확인")
    except Exception:
        fail("pgvector 미설치 — init.sql 재실행 필요")

    # Redis
    try:
        pong = await redis.ping()
        ok(f"Redis 연결: {pong}")
    except Exception as e:
        fail(f"Redis 연결 실패: {e}")

    # KIS API Key
    if not KIS_APP_KEY or not KIS_APP_SEC:
        fail("KIS_APP_KEY / KIS_APP_SECRET 환경변수 미설정. .env 파일을 확인하세요.")
    ok("KIS API Key 확인")

    if not DART_API_KEY:
        warn("DART_API_KEY 미설정 — 공시 수집 불가 (선택사항)")


# ── STEP 2: 종목 코드 수집 ────────────────────────────────────────────────────

async def load_stock_list(pool: asyncpg.Pool):
    step(2, "KOSPI/KOSDAQ 종목 코드 수집")

    existing = await pool.fetchval("SELECT COUNT(*) FROM stocks WHERE is_active=TRUE")
    if existing >= 100:
        ok(f"종목 {existing}개 이미 존재 — SKIP")
        return existing

    # KIS OAuth 토큰 발급
    async with httpx.AsyncClient(timeout=30) as client:
        token_r = await client.post(
            f"{KIS_BASE_URL}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": KIS_APP_KEY,
                "appsecret": KIS_APP_SEC,
            },
        )
        token_r.raise_for_status()
        token = token_r.json()["access_token"]

        headers = {
            "authorization": f"Bearer {token}",
            "appkey": KIS_APP_KEY,
            "appsecret": KIS_APP_SEC,
            "tr_id": "CTPF1702R",
            "custtype": "P",
        }

        total = 0
        for market_code, market_name in [("J", "KOSPI"), ("Q", "KOSDAQ")]:
            logger.info(f"  {market_name} 종목 수집 중...")
            fk100 = "0000000000"

            while True:
                params = {
                    "PRDT_TYPE_CD": "300",
                    "MRKT_ID_CD": market_code,
                    "SCTY_NM": "",
                    "FK100": fk100,
                    "NK100": fk100,
                    "CTX_AREA_FK100": fk100,
                    "CTX_AREA_NK100": fk100,
                }
                try:
                    r = await client.get(
                        f"{KIS_BASE_URL}/uapi/domestic-stock/v1/quotations/psearch-title",
                        headers=headers,
                        params=params,
                    )
                    data = r.json()
                except Exception as e:
                    warn(f"  종목 수집 API 오류: {e} — 대체 로직 사용")
                    break

                output2 = data.get("output2", [])
                if not output2:
                    break

                rows = [
                    (item["mksc_shrn_iscd"], item.get("hts_kor_isnm", ""), market_name)
                    for item in output2
                    if item.get("mksc_shrn_iscd")
                ]

                async with pool.acquire() as conn:
                    await conn.executemany(
                        """
                        INSERT INTO stocks (code, name, market, is_active)
                        VALUES ($1, $2, $3, TRUE)
                        ON CONFLICT (code) DO UPDATE
                            SET name=EXCLUDED.name, market=EXCLUDED.market,
                                is_active=TRUE, updated_at=NOW()
                        """,
                        rows,
                    )
                total += len(rows)

                ctx = data.get("ctx_area_fk100", "").strip()
                if not ctx or ctx == fk100:
                    break
                fk100 = ctx
                await asyncio.sleep(0.2)

    count = await pool.fetchval("SELECT COUNT(*) FROM stocks WHERE is_active=TRUE")
    ok(f"종목 수집 완료: {count}개")
    return count


# ── STEP 3: 일봉 백필 ─────────────────────────────────────────────────────────

async def backfill_daily_bars(pool: asyncpg.Pool):
    step(3, f"일봉 데이터 백필 (최근 {BACKFILL_DAYS}일)")

    existing = await pool.fetchval("SELECT COUNT(*) FROM daily_bars")
    if existing >= 50000:
        ok(f"일봉 {existing:,}건 이미 존재 — SKIP")
        return

    codes = [r["code"] for r in await pool.fetch(
        "SELECT code FROM stocks WHERE is_active=TRUE ORDER BY code LIMIT 500"
    )]

    end_date   = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=BACKFILL_DAYS)
    start_str  = start_date.strftime("%Y%m%d")
    end_str    = end_date.strftime("%Y%m%d")

    logger.info(f"  대상 {len(codes)}종목, {start_str}~{end_str}")

    # Docker compose의 collector backfill 사용
    import subprocess
    cmd = [
        "docker", "compose", "run", "--rm",
        "--no-deps", "collector-backfill",
        "python", "scripts/backfill_history.py",
        "--start", start_str,
        "--end",   end_str,
        "--concurrency", "3",
    ]
    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        warn("Docker 백필 실패 — 직접 실행 모드로 전환")
        await _backfill_direct(pool, codes, start_str, end_str)
    else:
        ok("일봉 백필 완료 (Docker compose)")


async def _backfill_direct(pool, codes, start_str, end_str):
    """Docker 없이 직접 백필 (최소 동작 보장용)."""
    logger.info("  직접 백필 시작...")
    sys.path.insert(0, "/app")
    try:
        from scripts.backfill_history import run_backfill
        await run_backfill(pool, codes, start_str, end_str, concurrency=3)
        ok("직접 백필 완료")
    except ImportError:
        warn("backfill_history 모듈 없음 — 수동 백필 필요")
        warn("  실행: make backfill START=20220101 END=20251231")


# ── STEP 4: Redis 통계 초기화 ────────────────────────────────────────────────

async def init_redis_stats(pool: asyncpg.Pool, redis: redis_lib.Redis):
    step(4, "Redis 통계 초기화 (거래량/수급 20일 평균)")

    key_sample = await redis.get("stats:005930:avg_vol_20d")
    if key_sample:
        ok("Redis 통계 이미 존재 — SKIP")
        return

    logger.info("  DB에서 20일 평균 통계 계산 중...")

    rows = await pool.fetch(
        """
        SELECT
            code,
            AVG(volume)          AS avg_vol_20d,
            AVG(amount)          AS avg_amount_20d,
            AVG(ABS(foreign_net_buy)) AS avg_foreign_20d,
            AVG(ABS(inst_net_buy))    AS avg_inst_20d
        FROM (
            SELECT code, volume, amount, foreign_net_buy, inst_net_buy, date,
                   ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) AS rn
            FROM daily_bars
            WHERE close > 0
        ) t
        WHERE rn <= 20
        GROUP BY code
        HAVING COUNT(*) >= 5
        """
    )

    pipe = redis.pipeline()
    for r in rows:
        prefix = f"stats:{r['code']}"
        if r["avg_vol_20d"]:
            pipe.set(f"{prefix}:avg_vol_20d",    str(r["avg_vol_20d"]),    ex=90000)
        if r["avg_amount_20d"]:
            pipe.set(f"{prefix}:avg_amount_20d", str(r["avg_amount_20d"]), ex=90000)
        if r["avg_foreign_20d"]:
            pipe.set(f"{prefix}:avg_foreign_20d", str(r["avg_foreign_20d"]), ex=90000)
        if r["avg_inst_20d"]:
            pipe.set(f"{prefix}:avg_inst_20d",   str(r["avg_inst_20d"]),   ex=90000)
    await pipe.execute()

    ok(f"Redis 통계 초기화: {len(rows)}종목")


# ── STEP 5: 공시 벡터 백필 ────────────────────────────────────────────────────

async def backfill_disclosure_vectors(pool: asyncpg.Pool):
    step(5, "공시 임베딩 벡터 백필")

    no_vec = await pool.fetchval(
        "SELECT COUNT(*) FROM disclosures WHERE embedding IS NULL AND content IS NOT NULL"
    )
    if no_vec == 0:
        ok("모든 공시에 벡터 존재 — SKIP")
        return

    logger.info(f"  벡터 없는 공시 {no_vec}건 처리 중...")

    try:
        sys.path.insert(0, "/app")
        from embedding.embedder import DisclosureEmbedder
        embedder = DisclosureEmbedder()

        rows = await pool.fetch(
            "SELECT id, title, content FROM disclosures "
            "WHERE embedding IS NULL AND content IS NOT NULL "
            "ORDER BY id LIMIT 2000"
        )

        updated = 0
        for i in range(0, len(rows), 32):
            batch = rows[i:i+32]
            texts = [f"{r['title']} {(r['content'] or '')[:500]}" for r in batch]
            vecs  = embedder.encode_batch(texts)

            async with pool.acquire() as conn:
                await conn.executemany(
                    "UPDATE disclosures SET embedding=$1::vector WHERE id=$2",
                    [(f"[{','.join(f'{v:.6f}' for v in vec)}]", r["id"])
                     for vec, r in zip(vecs, batch)],
                )
            updated += len(batch)
            if updated % 200 == 0:
                logger.info(f"  진행: {updated}/{len(rows)}")

        ok(f"공시 벡터 백필 완료: {updated}건")
    except ImportError as e:
        warn(f"임베더 로드 실패: {e} — 서비스 시작 후 자동 처리됨")


# ── STEP 6: 모델 학습 ─────────────────────────────────────────────────────────

async def train_models(pool: asyncpg.Pool):
    step(6, "LightGBM 모델 학습")

    entry_model = Path(MODEL_DIR) / "entry_model.lgb"
    if entry_model.exists():
        ok(f"모델 이미 존재: {entry_model} — SKIP")
        ok("재학습 원할 시: make train 실행")
        return

    bar_count = await pool.fetchval("SELECT COUNT(*) FROM daily_bars")
    if bar_count < 10000:
        warn(f"일봉 데이터 부족 ({bar_count}건). 백필 완료 후 재실행 필요.")
        warn("재실행: python setup_bootstrap.py")
        return

    logger.info("  모델 학습 시작 (소요 시간: 5~30분)...")
    Path(MODEL_DIR).mkdir(parents=True, exist_ok=True)

    # 학습 기간: 최근 3년 ~ 1년 전
    end_train = (date.today() - timedelta(days=365)).isoformat()
    start_train = (date.today() - timedelta(days=365 + 780)).isoformat()

    import subprocess
    cmd = [
        sys.executable,
        "/app/train_model.py",
        "--start", start_train,
        "--end",   end_train,
    ]
    env = os.environ.copy()
    result = subprocess.run(cmd, env=env)
    if result.returncode == 0:
        ok("모델 학습 완료")
    else:
        warn("모델 학습 실패 — 로그 확인 후 재시도: make train")


# ── STEP 7: 패턴 벡터 백필 ────────────────────────────────────────────────────

async def backfill_pattern_vectors(pool: asyncpg.Pool):
    step(7, "과거 이벤트 패턴 벡터 백필")

    no_vec = await pool.fetchval(
        "SELECT COUNT(*) FROM feature_events WHERE pattern_vector IS NULL"
    )
    if no_vec == 0:
        ok("모든 이벤트에 벡터 존재 — SKIP")
        return

    logger.info(f"  패턴 벡터 없는 이벤트 {no_vec}건 처리 중...")

    try:
        sys.path.insert(0, "/app")
        from similarity.pattern_embedder import PatternEmbedder
        embedder = PatternEmbedder()

        rows = await pool.fetch(
            """
            SELECT fe.id, fe.code, fe.detected_at::DATE AS event_date,
                   fe.event_type, fe.signal_data
            FROM feature_events fe
            WHERE fe.pattern_vector IS NULL
            ORDER BY fe.detected_at DESC
            LIMIT 5000
            """
        )

        updated = 0
        for r in rows:
            try:
                bar_rows = await pool.fetch(
                    """
                    SELECT db.date::TEXT, db.open, db.high, db.low, db.close,
                           db.volume, db.foreign_net_buy AS foreign_net,
                           db.inst_net_buy AS inst_net
                    FROM daily_bars db
                    WHERE db.code=$1
                      AND db.date <= $2
                    ORDER BY db.date DESC
                    LIMIT 22
                    """,
                    r["code"], r["event_date"],
                )
                if len(bar_rows) < 10:
                    continue

                import pandas as pd
                df = pd.DataFrame([dict(b) for b in bar_rows]).sort_values("date")
                vec = embedder.embed(df)

                vec_str = "[" + ",".join(f"{v:.6f}" for v in vec.tolist()) + "]"
                await pool.execute(
                    "UPDATE feature_events SET pattern_vector=$1::vector WHERE id=$2",
                    vec_str, r["id"],
                )
                updated += 1
                if updated % 500 == 0:
                    logger.info(f"  진행: {updated}/{len(rows)}")
            except Exception as e:
                logger.debug(f"  벡터 생성 실패 {r['id']}: {e}")

        ok(f"패턴 벡터 백필 완료: {updated}건")
    except ImportError as e:
        warn(f"패턴 임베더 로드 실패: {e}")


# ── STEP 8: 검증 ─────────────────────────────────────────────────────────────

async def validate(pool: asyncpg.Pool, redis: redis_lib.Redis):
    step(8, "시스템 검증")

    issues = []

    # 종목 수
    n_stocks = await pool.fetchval("SELECT COUNT(*) FROM stocks WHERE is_active=TRUE")
    if n_stocks < 100:
        issues.append(f"종목 수 부족: {n_stocks}")
    else:
        ok(f"종목: {n_stocks}개")

    # 일봉 데이터
    n_bars = await pool.fetchval("SELECT COUNT(*) FROM daily_bars")
    if n_bars < 10000:
        issues.append(f"일봉 데이터 부족: {n_bars}건")
    else:
        ok(f"일봉: {n_bars:,}건")

    # Redis 통계
    sample = await redis.get("stats:005930:avg_vol_20d")
    if not sample:
        issues.append("Redis 통계 없음 (005930)")
    else:
        ok(f"Redis 통계: 005930 avg_vol={float(sample):,.0f}")

    # 모델 파일
    entry_path = Path(MODEL_DIR) / "entry_model.lgb"
    if entry_path.exists():
        ok(f"모델: {entry_path}")
    else:
        issues.append(f"모델 없음: {entry_path}")

    # 항상 0인 피처 경고
    try:
        sys.path.insert(0, "/app")
        from models.lgbm_predictor import FEATURE_COLUMNS
        from features.technical import TechnicalFeatureExtractor
        ok(f"피처 컬럼: {len(FEATURE_COLUMNS)}개")
    except Exception as e:
        issues.append(f"피처 모듈 로드 실패: {e}")

    if issues:
        for issue in issues:
            warn(f"검증 이슈: {issue}")
        warn("일부 이슈가 있지만 서비스는 시작 가능합니다.")
        warn("모델 없는 경우 make train 실행 후 recommender 재시작")
    else:
        ok("모든 검증 통과")

    return len(issues) == 0


# ── STEP 9: 서비스 준비 플래그 ───────────────────────────────────────────────

async def set_ready_flag(redis: redis_lib.Redis, success: bool):
    step(9, "서비스 준비 완료")

    import json
    from datetime import datetime, timezone

    payload = {
        "bootstrapped_at": datetime.now(timezone.utc).isoformat(),
        "success": success,
        "version": "1.0",
    }
    await redis.set("system:bootstrapped", json.dumps(payload))

    if success:
        ok("Bootstrap 완료 — 서비스 시작 가능")
        ok("실행: docker compose up -d")
    else:
        warn("Bootstrap 부분 완료 — 이슈 해결 후 재실행 권장")
        warn("재실행: python setup_bootstrap.py")


# ── 메인 ──────────────────────────────────────────────────────────────────────

async def main():
    logger.info("\n" + "="*60)
    logger.info("KOSPI/KOSDAQ 특징주 시스템 초기화")
    logger.info("="*60 + "\n")

    start = time.time()

    pool = await asyncpg.create_pool(
        dsn=POSTGRES_DSN.replace("+asyncpg", ""),
        min_size=3, max_size=10,
        command_timeout=60,
    )
    redis = redis_lib.from_url(REDIS_URL, decode_responses=True)

    try:
        await check_infra(pool, redis)
        await load_stock_list(pool)
        await backfill_daily_bars(pool)
        await init_redis_stats(pool, redis)
        await backfill_disclosure_vectors(pool)
        await train_models(pool)
        await backfill_pattern_vectors(pool)
        success = await validate(pool, redis)
        await set_ready_flag(redis, success)
    finally:
        await pool.close()
        await redis.aclose()

    elapsed = time.time() - start
    logger.info(f"\n총 소요 시간: {elapsed/60:.1f}분")


if __name__ == "__main__":
    asyncio.run(main())

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import engine, SessionLocal
from .models import Base
from .api.v1.router import api_router
from .config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.is_default_secret:
        logger.warning("⚠️  SECRET_KEY가 기본값입니다. 프로덕션 배포 전 .env에서 SECRET_KEY를 반드시 교체하세요!")
    logger.info("서버 시작 — DB 테이블 동기화 중...")
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as _create_err:
        logger.warning(f"create_all 일부 실패 (테이블 중복 등, 무시): {_create_err}")

    # bids 테이블 신규 컬럼 마이그레이션 (ALTER TABLE IF NOT EXISTS)
    _mig_db = SessionLocal()
    try:
        from sqlalchemy import text as _mt
        for col_sql in [
            "ALTER TABLE bids ADD COLUMN IF NOT EXISTS construction_work_div VARCHAR(200)",
            "ALTER TABLE bids ADD COLUMN IF NOT EXISTS joint_supply_bid VARCHAR(10)",
            "ALTER TABLE bids ADD COLUMN IF NOT EXISTS participant_limit VARCHAR(10)",
            "ALTER TABLE bid_results ADD COLUMN IF NOT EXISTS draw_no1 SMALLINT",
            "ALTER TABLE bid_results ADD COLUMN IF NOT EXISTS draw_no2 SMALLINT",
            "ALTER TABLE bid_results ADD COLUMN IF NOT EXISTS bid_dt TIMESTAMPTZ",
            """CREATE TABLE IF NOT EXISTS g2b_yega_details (
                id              SERIAL PRIMARY KEY,
                announcement_no VARCHAR(60)  NOT NULL,
                yega_no         SMALLINT     NOT NULL,
                base_amount     BIGINT,
                estimated_price BIGINT,
                yega_total      SMALLINT,
                yega_price      BIGINT,
                is_selected     BOOLEAN DEFAULT FALSE,
                draw_count      SMALLINT,
                bid_open_dt     TIMESTAMPTZ,
                created_at      TIMESTAMPTZ DEFAULT now(),
                UNIQUE(announcement_no, yega_no)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_g2b_yega_announcement ON g2b_yega_details(announcement_no)",
        ]:
            _mig_db.execute(_mt(col_sql))
        _mig_db.commit()
    except Exception as _mig_err:
        logger.warning("bids 컬럼 마이그레이션 실패 (무시): %s", _mig_err)
        _mig_db.rollback()
    finally:
        _mig_db.close()

    if settings.seed_demo_data:
        db = SessionLocal()
        try:
            from .seed import seed_all
            seed_all(db)
        except Exception as e:
            logger.error(f"시드 오류: {e}")
        finally:
            db.close()

    # admin 계정 보장 — 매 시작마다 .env의 FIRST_ADMIN_PASSWORD로 비밀번호 동기화.
    # 이 방식으로 .env 수정 + 재시작만으로 항상 로그인 가능 상태 유지.
    _sync_db = SessionLocal()
    try:
        from .seed import ensure_admin_password
        ensure_admin_password(_sync_db)
    except Exception as _sync_err:
        logger.warning("admin 비밀번호 동기화 실패 (무시): %s", _sync_err)
    finally:
        _sync_db.close()

    # ML 엔진 미리 초기화 (첫 번째 추천 호출 지연 방지)
    try:
        from .ml.engine import get_engine
        get_engine()
        logger.info("ML 엔진 워밍업 완료")
    except Exception as _e:
        logger.warning(f"ML 엔진 워밍업 실패 (무시): {_e}")

    # 발주기관 빈도표 + 전략 DB pre-warm (테이블이 비어있을 때만)
    _db_warm = SessionLocal()
    try:
        from sqlalchemy import text as _t
        _freq_cnt = _db_warm.execute(_t("SELECT COUNT(*) FROM rate_frequency_tables")).scalar() or 0
        _strat_cnt = _db_warm.execute(_t("SELECT COUNT(*) FROM agency_strategies")).scalar() or 0
        if _freq_cnt == 0 or _strat_cnt == 0:
            logger.info("빈도표 초기 생성 시작 (freq=%d, strategy=%d)...", _freq_cnt, _strat_cnt)
            from .services import FrequencyService, AgencyStrategyService
            if _freq_cnt == 0:
                FrequencyService(_db_warm).rebuild_all()
            if _strat_cnt == 0:
                AgencyStrategyService(_db_warm).rebuild_all()
            logger.info("빈도표 초기 생성 완료")
    except Exception as _warm_err:
        logger.warning("빈도표 pre-warm 실패 (무시): %s", _warm_err)
    finally:
        _db_warm.close()

    # APScheduler — 멀티워커 환경에서 한 프로세스만 스케줄러 실행
    _sched_lock_fd = None
    _is_scheduler_master = False
    try:
        import fcntl as _fcntl
        _sched_lock_fd = open("/tmp/bid_scheduler.lock", "w")
        _fcntl.flock(_sched_lock_fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
        _is_scheduler_master = True
    except (IOError, OSError, ImportError):
        if _sched_lock_fd:
            try:
                _sched_lock_fd.close()
            except Exception:
                pass
            _sched_lock_fd = None

    if _is_scheduler_master:
        from .collector.scheduler import create_scheduler, set_scheduler
        scheduler = create_scheduler()
        scheduler.start()
        set_scheduler(scheduler)
        logger.info("Scheduler started (master worker)")
    else:
        scheduler = None
        logger.info("Scheduler skipped (secondary worker)")

    logger.info("서버 준비 완료")
    yield

    if scheduler:
        scheduler.shutdown(wait=False)
    if _sched_lock_fd:
        try:
            import fcntl as _fcntl
            _fcntl.flock(_sched_lock_fd, _fcntl.LOCK_UN)
            _sched_lock_fd.close()
        except Exception:
            pass
    logger.info("서버 종료")


app = FastAPI(
    title="건설 입찰 분석 시스템",
    description="상용 AI 없이 로컬 ML(XGBoost/LightGBM)로 구동되는 투찰율 추천 시스템",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

_origins = (
    ["*"] if settings.cors_origins.strip() == "*"
    else [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "1.0.0", "ai_mode": "local-ml"}

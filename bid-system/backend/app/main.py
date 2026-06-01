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
    logger.info("서버 시작 — DB 테이블 동기화 중...")
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as _create_err:
        logger.warning(f"create_all 일부 실패 (테이블 중복 등, 무시): {_create_err}")

    if settings.seed_demo_data:
        db = SessionLocal()
        try:
            from .seed import seed_all
            seed_all(db)
        except Exception as e:
            logger.error(f"시드 오류: {e}")
        finally:
            db.close()

    # ML 엔진 미리 초기화 (첫 번째 추천 호출 지연 방지)
    try:
        from .ml.engine import get_engine
        get_engine()
        logger.info("ML 엔진 워밍업 완료")
    except Exception as _e:
        logger.warning(f"ML 엔진 워밍업 실패 (무시): {_e}")

    logger.info("서버 준비 완료")
    yield
    logger.info("서버 종료")


app = FastAPI(
    title="건설 입찰 분석 시스템",
    description="상용 AI 없이 로컬 ML(XGBoost/LightGBM)로 구동되는 투찰율 추천 시스템",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "1.0.0", "ai_mode": "local-ml"}

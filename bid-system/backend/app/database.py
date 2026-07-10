from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from .config import get_settings

settings = get_settings()

# CockroachDB requires its own SQLAlchemy dialect (cockroachdb+psycopg2://)
_db_url = settings.database_url
if "cockroachlabs.cloud" in _db_url:
    _db_url = _db_url.replace("postgresql://", "cockroachdb+psycopg2://", 1)
    _db_url = _db_url.replace("postgresql+psycopg2://", "cockroachdb+psycopg2://", 1)

engine = create_engine(
    _db_url,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_reset_on_return="rollback",  # aborted 트랜잭션이 풀에 남지 않도록
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

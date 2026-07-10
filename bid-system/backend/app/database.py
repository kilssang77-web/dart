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
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

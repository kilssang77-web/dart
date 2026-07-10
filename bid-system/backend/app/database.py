from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from .config import get_settings

settings = get_settings()

# CockroachDB requires sslrootcert=system; psycopg2 connect_args takes priority over URL params
_connect_args: dict = {}
if "cockroachlabs.cloud" in settings.database_url:
    _connect_args["sslrootcert"] = "system"

engine = create_engine(
    settings.database_url,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    connect_args=_connect_args,
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

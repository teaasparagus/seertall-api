import os

from sqlalchemy import create_engine
from sqlmodel import SQLModel
from structlog import get_logger

logger = get_logger()
engine = None


def create_db_and_tables():
    global engine
    if engine is None:
        db_url = os.getenv(
            "DB_URL", "postgresql://postgres:postgres@127.0.0.1:5432/seertall"
        )
        engine = create_engine(db_url)
    logger.debug(f"Engine created: {engine!r}")
    SQLModel.metadata.create_all(engine)

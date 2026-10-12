from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


def _engine_options(database_url: str) -> dict:
    """Build bounded SQLAlchemy pool options for a single app process."""
    is_sqlite = database_url.startswith("sqlite")
    options = {
        "connect_args": {"check_same_thread": False} if is_sqlite else {"connect_timeout": 10},
        "future": True,
    }
    if not is_sqlite:
        options.update(
            {
                "pool_pre_ping": True,
                "pool_recycle": settings.database_pool_recycle,
                "pool_timeout": settings.database_pool_timeout,
                "pool_size": settings.database_pool_size,
                "max_overflow": settings.database_max_overflow,
            }
        )
    return options


engine = create_engine(settings.database_url, **_engine_options(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

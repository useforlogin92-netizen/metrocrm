from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


is_sqlite = settings.database_url.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {"connect_timeout": 10}

# Production PostgreSQL connections can be dropped while the service is idle or
# while the database provider rotates/recycles an upstream connection. Validate
# pooled connections before reuse and recycle them periodically so requests do
# not receive a stale SSL connection.
engine_kwargs = {
    "connect_args": connect_args,
    "future": True,
}
if not is_sqlite:
    engine_kwargs.update(
        {
            "pool_pre_ping": True,
            "pool_recycle": 1800,
            "pool_timeout": 30,
        }
    )

engine = create_engine(settings.database_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

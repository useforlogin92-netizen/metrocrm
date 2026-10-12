from app.database import _engine_options
from app.config import settings


def test_postgres_pool_is_bounded_for_ten_concurrent_callers():
    options = _engine_options("postgresql://user:pass@localhost/metrocrm")
    assert options["pool_size"] == settings.database_pool_size == 5
    assert options["max_overflow"] == settings.database_max_overflow == 5
    assert options["pool_size"] + options["max_overflow"] >= 10
    assert options["pool_timeout"] == 15
    assert options["pool_pre_ping"] is True
    assert options["pool_recycle"] == 1800


def test_sqlite_does_not_receive_postgres_pool_options():
    options = _engine_options("sqlite:///./test.db")
    assert options["connect_args"] == {"check_same_thread": False}
    assert "pool_size" not in options
    assert "max_overflow" not in options

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_production_requires_non_placeholder_secret():
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(
            environment="production",
            secret_key="CHANGE-ME-IN-ENV",
            database_url="postgresql://user:pass@localhost/metrocrm",
        )


def test_production_rejects_sqlite_database():
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings(
            environment="production",
            secret_key="a-long-random-production-secret",
            database_url="sqlite:///./metrocrm.db",
        )


def test_production_accepts_secret_and_postgres_url():
    settings = Settings(
        environment="production",
        secret_key="a-long-random-production-secret",
        database_url="postgresql://user:pass@localhost/metrocrm",
    )
    assert settings.environment == "production"


@pytest.mark.parametrize(
    ("setting", "value"),
    [
        ("session_max_age", 0),
        ("otp_expiry_seconds", 0),
        ("otp_max_attempts", 0),
    ],
)
def test_security_limits_must_be_positive(setting, value):
    with pytest.raises(ValidationError):
        Settings(**{setting: value})

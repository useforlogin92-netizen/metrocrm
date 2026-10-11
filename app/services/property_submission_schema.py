from sqlalchemy import inspect, text

from app.database import engine


def ensure_property_submission_schema() -> None:
    """Apply only the additive schema change required by same-link corrections."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "property_submissions" not in tables:
        return
    columns = {column["name"] for column in inspector.get_columns("property_submissions")}
    if "token_encrypted" in columns:
        return
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE property_submissions ADD COLUMN token_encrypted VARCHAR(512)"))


def ensure_property_master_schema() -> None:
    """Apply additive schema changes required by the canonical Metro Property Master."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "property_configurations" not in tables:
        return
    columns = {column["name"] for column in inspector.get_columns("property_configurations")}
    if "bundle_rate" in columns:
        return
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE property_configurations ADD COLUMN bundle_rate NUMERIC(18, 2)"))

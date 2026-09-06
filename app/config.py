from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MetroCRM"
    environment: str = "development"
    secret_key: str = "CHANGE-ME-IN-ENV"
    database_url: str = "sqlite:///./metrocrm.db"
    session_max_age: int = 28800
    otp_expiry_seconds: int = 300
    otp_max_attempts: int = 5

    # Full CRM backup settings. Keep destinations and encryption key in .env, never in Git.
    backup_enabled: bool = True
    backup_timezone: str = "Asia/Kolkata"
    backup_local_path: str = "./backups"
    uploads_path: str = "./uploads"
    backup_encryption_key: str = ""
    backup_cloud_provider: str = "none"
    backup_s3_endpoint: str = ""
    backup_s3_bucket: str = ""
    backup_s3_access_key: str = ""
    backup_s3_secret_key: str = ""
    backup_s3_region: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()

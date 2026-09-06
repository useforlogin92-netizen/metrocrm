from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MetroCRM"
    environment: str = "development"
    secret_key: str = "CHANGE-ME-IN-ENV"
    database_url: str = "sqlite:///./metrocrm.db"
    session_max_age: int = 28800
    otp_expiry_seconds: int = 300
    otp_max_attempts: int = 5
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()

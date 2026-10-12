from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MetroCRM"
    environment: str = "development"
    secret_key: str = "CHANGE-ME-IN-ENV"
    database_url: str = "sqlite:///./metrocrm.db"
    session_max_age: int = 900
    otp_expiry_seconds: int = 300
    otp_max_attempts: int = 5

    # Full CRM backup settings. Keep destinations and encryption key in .env, never in Git.
    backup_enabled: bool = True
    backup_timezone: str = "Asia/Kolkata"
    backup_local_path: str = "./backups"
    uploads_path: str = "./uploads"
    backup_external_path: str = ""
    backup_agent_token: str = ""
    backup_encryption_key: str = ""
    backup_cloud_provider: str = "none"
    backup_cloud_providers: str = ""
    backup_s3_endpoint: str = ""
    backup_s3_bucket: str = ""
    backup_s3_access_key: str = ""
    backup_s3_secret_key: str = ""
    backup_s3_region: str = ""
    # Optional dedicated B2 Native API credentials. These can be different from the
    # S3-compatible credentials and prevent a bad S3 key from breaking the native path.
    backup_b2_key_id: str = ""
    backup_b2_application_key: str = ""
    backup_b2_bucket_id: str = ""
    backup_google_client_id: str = ""
    backup_google_client_secret: str = ""
    backup_google_refresh_token: str = ""
    backup_google_folder_id: str = ""
    backup_onedrive_tenant: str = "common"
    backup_onedrive_client_id: str = ""
    backup_onedrive_client_secret: str = ""
    backup_onedrive_refresh_token: str = ""
    backup_onedrive_folder_path: str = "MetroCRM-Backups"
    # Backup alert destinations. Provider credentials remain deployment secrets.
    backup_alert_email_to: str = ""
    backup_alert_whatsapp_to: str = ""
    backup_alert_webhook_url: str = ""
    backup_alert_webhook_token: str = ""
    backup_missed_cycle_grace_minutes: int = 30

    # External lead/communication integrations. Credentials are supplied later in .env.
    lead_integrations_enabled: bool = True
    magicbricks_enabled: bool = False
    ninetynineacres_enabled: bool = False
    housing_enabled: bool = False
    facebook_leads_enabled: bool = False
    instagram_leads_enabled: bool = False
    google_leads_enabled: bool = False
    meta_ads_enabled: bool = False
    other_lead_webhook_enabled: bool = True
    integration_webhook_secret: str = ""
    integration_encryption_key: str = ""

    # WhatsApp gateway. Keep access tokens and provider credentials in deployment env vars, never Git.
    whatsapp_enabled: bool = False
    whatsapp_mode: str = "test"
    whatsapp_api_url: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_sender_name: str = "MetroCRM"
    whatsapp_public_base_url: str = ""

    otp_mobile_provider: str = "test"
    otp_email_provider: str = "test"
    sms_provider: str = "test"
    sms_api_url: str = ""
    sms_api_key: str = ""
    sms_sender_id: str = ""
    email_provider: str = "test"
    email_api_url: str = ""
    email_api_key: str = ""
    email_from: str = ""

    property_visit_alerts_enabled: bool = True
    property_visit_alert_cooldown_seconds: int = 60

    # AI caller/voice gateway. Provider credentials and voice IDs stay in deployment env vars.
    ai_caller_provider: str = ""
    ai_caller_provider_secret: str = ""
    ai_caller_default_language: str = "hi-IN"
    ai_caller_male_voice: str = ""
    ai_caller_female_voice: str = ""
    ai_caller_store_transcript: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def validate_runtime_settings(self):
        environment = self.environment.strip().lower()
        if self.session_max_age <= 0:
            raise ValueError("SESSION_MAX_AGE must be a positive number")
        if self.otp_expiry_seconds <= 0:
            raise ValueError("OTP_EXPIRY_SECONDS must be a positive number")
        if self.otp_max_attempts <= 0:
            raise ValueError("OTP_MAX_ATTEMPTS must be a positive number")
        if environment in {"production", "prod"}:
            if not self.secret_key.strip() or self.secret_key == "CHANGE-ME-IN-ENV":
                raise ValueError("SECRET_KEY must be set to a unique secret in production")
            if self.database_url.startswith("sqlite"):
                raise ValueError("DATABASE_URL must point to a persistent production database, not SQLite")
        return self


settings = Settings()

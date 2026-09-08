from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MetroCRM"
    environment: str = "development"
    secret_key: str = "CHANGE-ME-IN-ENV"
    database_url: str = "sqlite:///./metrocrm.db"
    # Security baseline: authenticated browser sessions expire after 15 minutes.
    session_max_age: int = 900
    otp_expiry_seconds: int = 300
    otp_max_attempts: int = 5

    # Full CRM backup settings. Keep destinations and encryption key in .env, never in Git.
    backup_enabled: bool = True
    backup_timezone: str = "Asia/Kolkata"
    backup_local_path: str = "./backups"
    backup_external_path: str = ""
    backup_agent_token: str = ""
    backup_encryption_key: str = ""
    backup_cloud_provider: str = "none"  # legacy single-provider setting
    backup_cloud_providers: str = ""  # comma-separated: s3,google_drive,onedrive
    backup_s3_endpoint: str = ""
    backup_s3_bucket: str = ""
    backup_s3_access_key: str = ""
    backup_s3_secret_key: str = ""
    backup_s3_region: str = ""

    # Google Drive delegated OAuth configuration. Keep all secrets in the deployment environment.
    backup_google_client_id: str = ""
    backup_google_client_secret: str = ""
    backup_google_refresh_token: str = ""
    backup_google_folder_id: str = ""

    # Microsoft OneDrive / Graph delegated OAuth configuration.
    backup_onedrive_tenant: str = "common"
    backup_onedrive_client_id: str = ""
    backup_onedrive_client_secret: str = ""
    backup_onedrive_refresh_token: str = ""
    backup_onedrive_folder_path: str = "MetroCRM-Backups"

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

    # OTP delivery providers are intentionally disabled until real credentials are configured.
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

    # Instant property/project visit alerts.
    property_visit_alerts_enabled: bool = True
    property_visit_alert_cooldown_seconds: int = 60

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()

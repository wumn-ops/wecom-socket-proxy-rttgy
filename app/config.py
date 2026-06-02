from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    wecom_bot_id: str = ""
    wecom_bot_secret: str = ""
    host: str = "0.0.0.0"
    port: int = 8001
    wecom_callback_path: str = "/wecom/aibot/callback/rttgy"
    health_path: str = "/health/rttgy"
    log_level: str = "INFO"

    upload_token_secret: str = ""

    smartsheet_webhook_url: str = ""
    smartsheet_field_demand_content: str = "f9VtuW"
    smartsheet_field_image: str = "fE88Fv"
    smartsheet_field_submitter: str = "f04Gwj"
    smartsheet_field_system: str = "fJodHY"
    registration_system_options: str = "CRM,SAP,MES,其他"
    smartsheet_docid: str = ""
    smartsheet_sheet_id: str = ""
    smartsheet_field_progress: str = "ftQMc5"
    smartsheet_field_test_result: str = "ft3nIs"
    smartsheet_field_satisfaction: str = "fLOs6M"
    launch_progress_value: str = "已上线"
    launch_test_pass_value: str = "通过"
    feedback_test_fail_value: str = "不通过"
    launch_notify_enabled: bool = True
    launch_poll_interval_seconds: int = 60
    launch_notify_state_path: str = "data/launch_notified.json"
    issue_list_url: str = ""

    public_base_url: str = ""
    register_upload_path: str = "/register/upload/rttgy"
    register_daily_path: str = "/register/daily/rttgy"
    register_daily_success_message: str = "您的需求已登记成功，感谢提交。"
    feedback_path: str = "/feedback/rttgy"
    upload_token_ttl_seconds: int = 3600
    feedback_token_ttl_seconds: int = 604800
    max_upload_bytes: int = 5 * 1024 * 1024

    wecom_corp_id: str = ""
    wecom_agent_id: str = ""
    wecom_corp_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()

from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_file=None)
    ai_provider: str = "alibaba"
    ai_api_key: SecretStr = SecretStr("")
    ai_model: str = ""
    alibaba_api_key: SecretStr = SecretStr("")
    alibaba_base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    alibaba_tool_model: str = "qwen-plus"
    alibaba_fallback_model: str = ""
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = ""
    ai_timeout_seconds: float = Field(15, gt=0, le=15)
    ai_rate_limit_per_hour: int = Field(20, ge=1, le=1000)
    ai_timezone: str = "Asia/Karachi"

    @field_validator("ai_provider")
    @classmethod
    def provider(cls, v):
        if v not in {"alibaba", "gemini"}:
            raise ValueError("Unsupported AI provider")
        return v

    @field_validator("alibaba_base_url")
    @classmethod
    def endpoint(cls, v):
        from urllib.parse import urlparse

        u = urlparse(v)
        if u.scheme != "https" or not u.hostname or u.username or u.password:
            raise ValueError(
                "Provider endpoint must use HTTPS without embedded credentials"
            )
        return v

    @field_validator("alibaba_tool_model", "alibaba_fallback_model")
    @classmethod
    def tool_model(cls, v):
        if "character" in v.casefold():
            raise ValueError("Character models cannot run tools")
        return v

    @field_validator("ai_timezone")
    @classmethod
    def timezone(cls, v):
        ZoneInfo(v)
        return v

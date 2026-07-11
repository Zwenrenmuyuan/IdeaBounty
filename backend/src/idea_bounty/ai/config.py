from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AISettings(BaseSettings):
    """延迟加载的 OpenAI 兼容生成模型配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AI_",
        extra="ignore",
    )

    base_url: str = Field(min_length=1)
    api_key: SecretStr = Field(min_length=1)
    model_id: str = Field(min_length=1)
    timeout_seconds: float = Field(default=60, gt=0, le=300)
    max_retries: int = Field(default=2, ge=0, le=3)
    temperature: float = Field(default=0.2, ge=0, le=2)


@lru_cache
def get_ai_settings() -> AISettings:
    """只在首次处理投稿时读取 AI 配置。"""

    return AISettings()

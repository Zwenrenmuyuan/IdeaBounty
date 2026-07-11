from functools import lru_cache
from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

EXPECTED_EMBEDDING_DIMENSIONS = 1024


class EmbeddingSettings(BaseSettings):
    """延迟加载的 OpenAI 兼容 Embedding 配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="EMBEDDING_",
        extra="ignore",
    )

    base_url: str = Field(min_length=1)
    api_key: SecretStr = Field(min_length=1)
    model_id: str = Field(min_length=1)
    dimensions: int = Field(gt=0, le=100_000)
    timeout_seconds: float = Field(default=60, gt=0, le=300)
    max_retries: int = Field(default=2, ge=0, le=3)

    @model_validator(mode="after")
    def validate_dimensions(self) -> Self:
        """数据库列固定为 1024 维，配置必须与其一致。"""

        if self.dimensions != EXPECTED_EMBEDDING_DIMENSIONS:
            raise ValueError(f"EMBEDDING_DIMENSIONS 必须为 {EXPECTED_EMBEDDING_DIMENSIONS}")
        return self


@lru_cache
def get_embedding_settings() -> EmbeddingSettings:
    """只在首次需要生成向量时读取 Embedding 配置。"""

    return EmbeddingSettings()

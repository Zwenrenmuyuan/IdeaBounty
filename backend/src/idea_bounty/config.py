from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """从环境变量或本地 .env 文件加载应用配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="IDEA_BOUNTY_",
        extra="ignore",
    )

    app_name: str = "idea-bounty-api"
    app_env: Literal["development", "test", "production"] = "development"
    debug: bool = False
    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://idea_bounty:idea_bounty_dev@localhost:5432/idea_bounty"
    )


@lru_cache
def get_settings() -> Settings:
    """返回在进程生命周期内复用的配置实例。"""

    return Settings()

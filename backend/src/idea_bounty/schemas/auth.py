from datetime import datetime
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from idea_bounty.models import UserRole, UserStatus


class CredentialsRequest(BaseModel):
    """注册和登录共用的用户名密码输入。"""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(pattern=r"^[a-z0-9_]{3,32}$")
    password: str = Field(min_length=8, max_length=128)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value: Any) -> Any:
        """统一用户名的首尾空白和大小写。"""

        if isinstance(value, str):
            return value.strip().lower()
        return value


class RegisterRequest(CredentialsRequest):
    """公开注册请求。"""


class LoginRequest(CredentialsRequest):
    """用户名密码登录请求。"""


class UserResponse(BaseModel):
    """可以安全返回给当前用户的账户信息。"""

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: UserRole
    status: UserStatus
    created_at: datetime

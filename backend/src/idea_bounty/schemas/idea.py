from datetime import datetime
from typing import ClassVar

from pydantic import UUID4, BaseModel, ConfigDict, Field, field_validator

from idea_bounty.models import IdeaProcessingStatus


class IdeaCreateRequest(BaseModel):
    """创建点子所需的客户端输入。"""

    model_config = ConfigDict(extra="forbid")

    submission_key: UUID4
    raw_content: str = Field(max_length=2000)

    @field_validator("raw_content")
    @classmethod
    def validate_raw_content(cls, value: str) -> str:
        """拒绝无意义或 PostgreSQL 无法保存的原始文本。"""

        if "\x00" in value:
            raise ValueError("投稿内容不能包含 NUL 字符")
        if len(value.strip()) < 8:
            raise ValueError("投稿内容去除首尾空白后至少需要 8 个字符")
        return value


class IdeaResponse(BaseModel):
    """当前用户可以查看的点子字段。"""

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    public_id: UUID4
    submission_key: UUID4
    raw_content: str
    processing_status: IdeaProcessingStatus
    retry_count: int
    created_at: datetime
    updated_at: datetime


class IdeaListResponse(BaseModel):
    """带总数的个人点子分页结果。"""

    items: list[IdeaResponse]
    total: int
    limit: int
    offset: int

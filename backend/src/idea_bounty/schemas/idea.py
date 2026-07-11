from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import UUID4, BaseModel, ConfigDict, Field, field_validator

from idea_bounty.models import IdeaProcessingStatus, InputDecision
from idea_bounty.schemas.ai import EvaluationScores, NormalizedContent

if TYPE_CHECKING:
    from idea_bounty.models import Idea


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


class IdeaSummaryResponse(BaseModel):
    """个人投稿列表中的轻量点子摘要。"""

    public_id: UUID4
    submission_key: UUID4
    raw_content: str
    generated_title: str | None
    processing_status: IdeaProcessingStatus
    input_decision: InputDecision | None
    retry_count: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_idea(cls, idea: Idea) -> IdeaSummaryResponse:
        """从 ORM 快照投影用户可见的列表字段。"""

        normalized_content = _parse_normalized_content(idea)
        return cls(
            public_id=idea.public_id,
            submission_key=idea.submission_key,
            raw_content=idea.raw_content,
            generated_title=(
                normalized_content.generated_title if normalized_content is not None else None
            ),
            processing_status=IdeaProcessingStatus(idea.processing_status),
            input_decision=(
                InputDecision(idea.input_decision) if idea.input_decision is not None else None
            ),
            retry_count=idea.retry_count,
            created_at=idea.created_at,
            updated_at=idea.updated_at,
        )


class IdeaResponse(IdeaSummaryResponse):
    """创建和个人详情接口返回的完整评估结果。"""

    decision_reason: str | None
    clarification_question: str | None
    evaluation: EvaluationScores | None

    @classmethod
    def from_idea(cls, idea: Idea) -> IdeaResponse:
        """从 ORM 快照投影用户可见字段并重新校验 JSONB。"""

        summary = IdeaSummaryResponse.from_idea(idea)
        normalized_content = _parse_normalized_content(idea)
        evaluation = _parse_evaluation_scores(idea)
        return cls(
            **summary.model_dump(),
            decision_reason=idea.decision_reason,
            clarification_question=(
                normalized_content.clarification_question
                if normalized_content is not None
                else None
            ),
            evaluation=evaluation,
        )


class IdeaListResponse(BaseModel):
    """带总数的个人点子摘要分页。"""

    items: list[IdeaSummaryResponse]
    total: int
    limit: int
    offset: int


def _parse_normalized_content(idea: Idea) -> NormalizedContent | None:
    if idea.normalized_content is None:
        return None
    return NormalizedContent.model_validate_json(
        json.dumps(idea.normalized_content, ensure_ascii=False)
    )


def _parse_evaluation_scores(idea: Idea) -> EvaluationScores | None:
    if idea.dimension_scores is None:
        return None
    return EvaluationScores.model_validate_json(
        json.dumps(idea.dimension_scores, ensure_ascii=False)
    )

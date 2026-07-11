from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Self

from pydantic import UUID4, BaseModel, ConfigDict, Field, field_validator, model_validator

from idea_bounty.models import AdminAction, DuplicateVerdict, IdeaProcessingStatus, InputDecision
from idea_bounty.schemas.idea import IdeaResponse


class AdminIdeaProcessRequest(BaseModel):
    """管理员一次性确认、调价或驳回投稿。"""

    model_config = ConfigDict(extra="forbid")

    action: AdminAction
    amount: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=2)
    reason: str | None = Field(default=None, max_length=300)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def validate_action_fields(self) -> Self:
        if self.action is AdminAction.CONFIRMED:
            if self.amount is not None:
                raise ValueError("直接确认时不能指定金额")
        elif self.action is AdminAction.ADJUSTED:
            if self.amount is None or self.reason is None:
                raise ValueError("调整金额时必须提供金额和理由")
        elif self.reason is None:
            raise ValueError("驳回时必须提供理由")
        if self.action is not AdminAction.ADJUSTED and self.amount is not None:
            raise ValueError("只有调整操作可以指定金额")
        return self


class AdminIdeaListItem(BaseModel):
    """管理员列表所需的点子摘要。"""

    public_id: UUID4
    username: str
    generated_title: str | None
    processing_status: IdeaProcessingStatus
    input_decision: InputDecision | None
    commercial_score: int | None
    final_amount: float | None
    duplicate_verdict: DuplicateVerdict | None
    admin_action: AdminAction | None
    created_at: datetime


class AdminIdeaListResponse(BaseModel):
    items: list[AdminIdeaListItem]
    total: int
    limit: int
    offset: int


class AdminIdeaDetailResponse(BaseModel):
    """后台查看和最终处理共用的完整响应。"""

    username: str
    idea: IdeaResponse
    admin_reason: str | None
    admin_processed_at: datetime | None


class AdminSummaryResponse(BaseModel):
    """面试 MVP 所需的基础后台汇总。"""

    total_submissions: int
    completed_accepts: int
    duplicate_count: int
    estimated_total: float
    confirmed_payout_count: int
    simulated_payout_total: float

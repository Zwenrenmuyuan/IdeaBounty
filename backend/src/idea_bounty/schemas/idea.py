from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import TYPE_CHECKING, Literal

from pydantic import UUID4, BaseModel, ConfigDict, Field, field_validator

from idea_bounty.models import AdminAction, DuplicateVerdict, IdeaProcessingStatus, InputDecision
from idea_bounty.schemas.ai import EvaluationScores, NormalizedContent
from idea_bounty.schemas.duplicate import DuplicateComparisonSnapshot

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


class IdeaDuplicateResultResponse(BaseModel):
    """个人详情中允许展示的查重结论。"""

    verdict: DuplicateVerdict
    matched_public_id: UUID4 | None
    matched_idea_url: str | None
    same_aspects: list[str]
    different_aspects: list[str]
    reason: str


class SimulatedPayoutResponse(BaseModel):
    """用户和管理员均可查看的虚拟打款凭证。"""

    amount: float
    reference: str
    confirmed_at: datetime


class IdeaResponse(IdeaSummaryResponse):
    """创建和个人详情接口返回的完整评估结果。"""

    decision_reason: str | None
    clarification_question: str | None
    evaluation: EvaluationScores | None
    duplicate_result: IdeaDuplicateResultResponse | None
    commercial_score: int | None
    base_amount: float | None
    duplicate_deduction: float | None
    final_amount: float | None
    admin_action: AdminAction | None
    payout_status: Literal["not_ready", "awaiting_admin", "confirmed", "not_applicable"]
    payout: SimulatedPayoutResponse | None

    @classmethod
    def from_idea(
        cls,
        idea: Idea,
        matched_public_id: UUID4 | None = None,
    ) -> IdeaResponse:
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
            duplicate_result=_build_duplicate_result(idea, matched_public_id),
            commercial_score=idea.commercial_score,
            base_amount=float(idea.base_amount) if idea.base_amount is not None else None,
            duplicate_deduction=(
                float(idea.duplicate_deduction) if idea.duplicate_deduction is not None else None
            ),
            final_amount=float(idea.final_amount) if idea.final_amount is not None else None,
            admin_action=AdminAction(idea.admin_action) if idea.admin_action is not None else None,
            payout_status=get_payout_status(idea),
            payout=(
                SimulatedPayoutResponse(
                    amount=float(idea.payout.amount),
                    reference=idea.payout.reference,
                    confirmed_at=idea.payout.confirmed_at,
                )
                if idea.payout is not None
                else None
            ),
        )


class IdeaListResponse(BaseModel):
    """带总数的个人点子摘要分页。"""

    items: list[IdeaSummaryResponse]
    total: int
    limit: int
    offset: int


class PublicIdeaSummary(BaseModel):
    """允许登录用户跨用户查看的脱敏点子摘要。"""

    public_id: UUID4
    generated_title: str | None
    target_audience: str | None
    pain_point: str | None
    context: str | None
    solution_present: bool
    solution_outline: str | None
    created_date: date

    @classmethod
    def from_idea(cls, idea: Idea) -> PublicIdeaSummary:
        """从正式规范化快照投影白名单字段并逐项脱敏。"""

        content = _parse_normalized_content(idea)
        if content is None:
            raise ValueError("公开摘要缺少规范化内容")
        return cls(
            public_id=idea.public_id,
            generated_title=_safe_public_text(content.generated_title),
            target_audience=_safe_public_text(content.target_audience.value),
            pain_point=_safe_public_text(content.pain_point.value),
            context=_safe_public_text(content.context.value),
            solution_present=content.solution_present,
            solution_outline=_safe_public_text(content.solution_mechanism.value),
            created_date=idea.created_at.date(),
        )


def get_payout_status(
    idea: Idea,
) -> Literal["not_ready", "awaiting_admin", "confirmed", "not_applicable"]:
    """由现有状态推导用户可见的模拟打款状态。"""

    if (
        idea.processing_status != IdeaProcessingStatus.COMPLETED.value
        or idea.input_decision != InputDecision.ACCEPT.value
    ):
        return "not_ready"
    if idea.admin_action is None:
        return "awaiting_admin"
    if idea.payout is not None:
        return "confirmed"
    return "not_applicable"


SENSITIVE_PATTERNS = (
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\d)"),
    re.compile(r"(?:省|自治区|市|区|县).{0,24}(?:路|街|道|巷|号|栋|室)"),
    re.compile(r"\d{1,6}(?:号|栋|单元|室)"),
)


def _safe_public_text(value: str | None) -> str | None:
    if value is None or any(pattern.search(value) for pattern in SENSITIVE_PATTERNS):
        return None
    return value


def _build_duplicate_result(
    idea: Idea,
    matched_public_id: UUID4 | None,
) -> IdeaDuplicateResultResponse | None:
    if idea.effective_duplicate_verdict is None or idea.duplicate_reason is None:
        return None
    comparison = _parse_duplicate_comparison(idea)
    matched_url = (
        f"/api/ideas/{matched_public_id}/summary" if matched_public_id is not None else None
    )
    return IdeaDuplicateResultResponse(
        verdict=DuplicateVerdict(idea.effective_duplicate_verdict),
        matched_public_id=matched_public_id,
        matched_idea_url=matched_url,
        same_aspects=(
            [aspect.value for aspect in comparison.same_aspects] if comparison is not None else []
        ),
        different_aspects=(
            [aspect.value for aspect in comparison.different_aspects]
            if comparison is not None
            else []
        ),
        reason=idea.duplicate_reason,
    )


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


def _parse_duplicate_comparison(idea: Idea) -> DuplicateComparisonSnapshot | None:
    if idea.duplicate_comparison is None:
        return None
    return DuplicateComparisonSnapshot.model_validate_json(
        json.dumps(idea.duplicate_comparison, ensure_ascii=False)
    )

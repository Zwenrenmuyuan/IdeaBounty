"""API 请求与响应模型。"""

from idea_bounty.schemas.auth import LoginRequest, RegisterRequest, UserResponse
from idea_bounty.schemas.duplicate import (
    ComparableIdea,
    DuplicateCandidateInput,
    DuplicateComparisonInput,
    DuplicateJudgmentOutput,
)
from idea_bounty.schemas.idea import (
    IdeaCreateRequest,
    IdeaListResponse,
    IdeaResponse,
    IdeaSummaryResponse,
)

__all__ = [
    "ComparableIdea",
    "DuplicateCandidateInput",
    "DuplicateComparisonInput",
    "DuplicateJudgmentOutput",
    "IdeaCreateRequest",
    "IdeaListResponse",
    "IdeaResponse",
    "IdeaSummaryResponse",
    "LoginRequest",
    "RegisterRequest",
    "UserResponse",
]

"""API 请求与响应模型。"""

from idea_bounty.schemas.auth import LoginRequest, RegisterRequest, UserResponse
from idea_bounty.schemas.duplicate import (
    ComparableIdea,
    DuplicateCandidateInput,
    DuplicateComparisonInput,
    DuplicateComparisonSnapshot,
    DuplicateJudgmentOutput,
)
from idea_bounty.schemas.idea import (
    IdeaCreateRequest,
    IdeaDuplicateResultResponse,
    IdeaListResponse,
    IdeaResponse,
    IdeaSummaryResponse,
    PublicIdeaSummary,
)

__all__ = [
    "ComparableIdea",
    "DuplicateCandidateInput",
    "DuplicateComparisonInput",
    "DuplicateComparisonSnapshot",
    "DuplicateJudgmentOutput",
    "IdeaCreateRequest",
    "IdeaDuplicateResultResponse",
    "IdeaListResponse",
    "IdeaResponse",
    "IdeaSummaryResponse",
    "LoginRequest",
    "PublicIdeaSummary",
    "RegisterRequest",
    "UserResponse",
]

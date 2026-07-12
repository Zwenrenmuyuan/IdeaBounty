"""FastAPI 请求依赖。"""

from idea_bounty.api.dependencies.ai import get_evaluation_provider
from idea_bounty.api.dependencies.auth import (
    get_current_admin,
    get_current_submitter,
    get_current_user,
)
from idea_bounty.api.dependencies.duplicate import get_duplicate_provider
from idea_bounty.api.dependencies.embedding import get_embedding_provider

__all__ = [
    "get_current_admin",
    "get_current_submitter",
    "get_current_user",
    "get_duplicate_provider",
    "get_embedding_provider",
    "get_evaluation_provider",
]

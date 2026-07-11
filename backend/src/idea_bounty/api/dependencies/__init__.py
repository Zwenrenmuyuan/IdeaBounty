"""FastAPI 请求依赖。"""

from idea_bounty.api.dependencies.ai import get_evaluation_provider
from idea_bounty.api.dependencies.auth import get_current_user

__all__ = ["get_current_user", "get_evaluation_provider"]

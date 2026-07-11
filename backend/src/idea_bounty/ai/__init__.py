"""AI 服务配置、提示词和兼容客户端。"""

from idea_bounty.ai.client import (
    EvaluationProvider,
    EvaluationProviderError,
    EvaluationProviderResult,
    OpenAICompatibleEvaluationProvider,
)
from idea_bounty.ai.config import AISettings, get_ai_settings
from idea_bounty.ai.duplicate_client import (
    DuplicateProvider,
    DuplicateProviderError,
    DuplicateProviderResult,
    OpenAICompatibleDuplicateProvider,
)

__all__ = [
    "AISettings",
    "DuplicateProvider",
    "DuplicateProviderError",
    "DuplicateProviderResult",
    "EvaluationProvider",
    "EvaluationProviderError",
    "EvaluationProviderResult",
    "OpenAICompatibleDuplicateProvider",
    "OpenAICompatibleEvaluationProvider",
    "get_ai_settings",
]

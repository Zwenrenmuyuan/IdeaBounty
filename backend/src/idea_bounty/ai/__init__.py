"""AI 服务配置、提示词和兼容客户端。"""

from idea_bounty.ai.client import (
    EvaluationProvider,
    EvaluationProviderError,
    EvaluationProviderResult,
    OpenAICompatibleEvaluationProvider,
)
from idea_bounty.ai.config import AISettings, get_ai_settings

__all__ = [
    "AISettings",
    "EvaluationProvider",
    "EvaluationProviderError",
    "EvaluationProviderResult",
    "OpenAICompatibleEvaluationProvider",
    "get_ai_settings",
]

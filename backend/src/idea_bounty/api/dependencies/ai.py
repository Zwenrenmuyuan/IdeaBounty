from pydantic import ValidationError

from idea_bounty.ai import (
    EvaluationProvider,
    OpenAICompatibleEvaluationProvider,
    get_ai_settings,
)
from idea_bounty.ai.client import UnavailableEvaluationProvider


def get_evaluation_provider() -> EvaluationProvider:
    """延迟创建评估提供者，配置错误留给投稿状态记录。"""

    try:
        settings = get_ai_settings()
    except ValidationError:
        return UnavailableEvaluationProvider()
    return OpenAICompatibleEvaluationProvider(settings)

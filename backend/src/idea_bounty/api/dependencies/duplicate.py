from pydantic import ValidationError

from idea_bounty.ai import (
    DuplicateProvider,
    OpenAICompatibleDuplicateProvider,
    get_ai_settings,
)
from idea_bounty.ai.duplicate_client import UnavailableDuplicateProvider


def get_duplicate_provider() -> DuplicateProvider:
    """延迟创建查重提供者，配置错误留给投稿状态记录。"""

    try:
        settings = get_ai_settings()
    except ValidationError:
        return UnavailableDuplicateProvider()
    return OpenAICompatibleDuplicateProvider(settings)

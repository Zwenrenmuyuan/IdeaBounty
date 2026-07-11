from idea_bounty.embedding import (
    EmbeddingProvider,
    EmbeddingProviderResult,
    OpenAICompatibleEmbeddingProvider,
    UnavailableEmbeddingProvider,
    get_embedding_settings,
)


class EnvironmentEmbeddingProvider:
    """直到确实需要向量时才读取环境配置。"""

    def embed(self, text: str) -> EmbeddingProviderResult:
        try:
            settings = get_embedding_settings()
        except ValueError:
            return UnavailableEmbeddingProvider().embed(text)
        return OpenAICompatibleEmbeddingProvider(settings).embed(text)


def get_embedding_provider() -> EmbeddingProvider:
    """返回不会在依赖解析阶段读取配置的 Embedding 提供者。"""

    return EnvironmentEmbeddingProvider()

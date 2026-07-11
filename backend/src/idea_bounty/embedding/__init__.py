"""Embedding 配置、输入构建和 OpenAI 兼容客户端。"""

from idea_bounty.embedding.client import (
    EmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingProviderResult,
    OpenAICompatibleEmbeddingProvider,
    UnavailableEmbeddingProvider,
)
from idea_bounty.embedding.config import (
    EXPECTED_EMBEDDING_DIMENSIONS,
    EmbeddingSettings,
    get_embedding_settings,
)
from idea_bounty.embedding.contracts import (
    EmbeddingDimensionMismatchError,
    EmbeddingResponseError,
    ParsedEmbeddings,
    build_embeddings_url,
    parse_embedding_response,
    vector_norm,
)
from idea_bounty.embedding.text import EMBEDDING_INPUT_VERSION, build_embedding_text

__all__ = [
    "EMBEDDING_INPUT_VERSION",
    "EXPECTED_EMBEDDING_DIMENSIONS",
    "EmbeddingDimensionMismatchError",
    "EmbeddingProvider",
    "EmbeddingProviderError",
    "EmbeddingProviderResult",
    "EmbeddingResponseError",
    "EmbeddingSettings",
    "OpenAICompatibleEmbeddingProvider",
    "ParsedEmbeddings",
    "UnavailableEmbeddingProvider",
    "build_embedding_text",
    "build_embeddings_url",
    "get_embedding_settings",
    "parse_embedding_response",
    "vector_norm",
]

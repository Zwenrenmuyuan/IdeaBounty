from __future__ import annotations

from collections.abc import Callable

from idea_bounty.embedding import (
    EXPECTED_EMBEDDING_DIMENSIONS,
    EmbeddingProviderError,
    EmbeddingProviderResult,
)


def make_embedding_result(
    *,
    model_id: str = "fake-embedding-model",
) -> EmbeddingProviderResult:
    """创建固定 1024 维的测试向量结果。"""

    return EmbeddingProviderResult(
        vector=(1.0, *(0.0 for _ in range(EXPECTED_EMBEDDING_DIMENSIONS - 1))),
        model_id=model_id,
        response_model=model_id,
        dimensions=EXPECTED_EMBEDDING_DIMENSIONS,
        request_id="fake-embedding-request",
        prompt_tokens=20,
        total_tokens=20,
        elapsed_seconds=0.01,
        attempts=1,
    )


class FakeEmbeddingProvider:
    """可按顺序返回结果或异常的 Embedding 测试替身。"""

    def __init__(
        self,
        outcomes: list[EmbeddingProviderResult | EmbeddingProviderError] | None = None,
        *,
        on_embed: Callable[[], None] | None = None,
    ) -> None:
        self.outcomes = outcomes or [make_embedding_result()]
        self.on_embed = on_embed
        self.call_count = 0
        self.texts: list[str] = []

    def embed(self, text: str) -> EmbeddingProviderResult:
        self.call_count += 1
        self.texts.append(text)
        if self.on_embed is not None:
            self.on_embed()
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, EmbeddingProviderError):
            raise outcome
        return outcome

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class EmbeddingResponseError(ValueError):
    """Embedding 响应不满足结构或数值契约。"""


class EmbeddingDimensionMismatchError(EmbeddingResponseError):
    """Embedding 服务返回的向量维度与配置不一致。"""


class EmbeddingItem(BaseModel):
    """OpenAI 兼容响应中的单条向量。"""

    model_config = ConfigDict(extra="ignore", strict=True)

    index: int = Field(ge=0)
    embedding: list[float]

    @field_validator("embedding", mode="before")
    @classmethod
    def validate_embedding_values(cls, value: Any) -> list[float]:
        """只接受有限数值，并统一转换成 float。"""

        if not isinstance(value, list):
            raise ValueError("embedding 必须是数组")
        normalized: list[float] = []
        for item in value:
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                raise ValueError("embedding 只能包含数值")
            number = float(item)
            if not math.isfinite(number):
                raise ValueError("embedding 不能包含 NaN 或 Infinity")
            normalized.append(number)
        return normalized


class EmbeddingResponse(BaseModel):
    """项目需要的 OpenAI 兼容 Embedding 响应字段。"""

    model_config = ConfigDict(extra="ignore", strict=True)

    data: list[EmbeddingItem]
    model: str | None = None
    usage: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ParsedEmbeddings:
    """按响应 index 恢复输入顺序后的已校验向量。"""

    vectors: tuple[tuple[float, ...], ...]
    dimension: int
    norms: tuple[float, ...]
    response_model: str | None
    usage: dict[str, Any] | None


def build_embeddings_url(base_url: str) -> str:
    """把常规 Base URL 转换成 Embeddings 端点。"""

    normalized = base_url.strip().rstrip("/")
    if not normalized:
        raise ValueError("EMBEDDING_BASE_URL 不能为空")
    if normalized.endswith("/embeddings"):
        return normalized
    return f"{normalized}/embeddings"


def vector_norm(vector: tuple[float, ...]) -> float:
    """计算向量的欧几里得范数。"""

    return math.sqrt(sum(value * value for value in vector))


def parse_embedding_response(
    response_body: str,
    *,
    expected_count: int,
    expected_dimensions: int | None,
) -> ParsedEmbeddings:
    """严格校验数量、索引、维度和向量数值。"""

    try:
        parsed = EmbeddingResponse.model_validate_json(response_body)
    except ValidationError as exc:
        raise EmbeddingResponseError(
            f"Embedding 响应结构无效：{exc.error_count()} 个校验错误"
        ) from exc

    if len(parsed.data) != expected_count:
        raise EmbeddingResponseError(
            f"向量数量不符：期望 {expected_count}，实际 {len(parsed.data)}"
        )

    indexed: dict[int, tuple[float, ...]] = {}
    for item in parsed.data:
        if item.index in indexed:
            raise EmbeddingResponseError(f"响应包含重复 index：{item.index}")
        if item.index >= expected_count:
            raise EmbeddingResponseError(f"响应 index 越界：{item.index}")
        indexed[item.index] = tuple(item.embedding)

    expected_indices = set(range(expected_count))
    if set(indexed) != expected_indices:
        missing = ", ".join(str(index) for index in sorted(expected_indices - set(indexed)))
        raise EmbeddingResponseError(f"响应缺少 index：{missing}")

    vectors = tuple(indexed[index] for index in range(expected_count))
    dimensions = {len(vector) for vector in vectors}
    if len(dimensions) != 1:
        raise EmbeddingResponseError("响应中的向量维度不一致")
    dimension = dimensions.pop()
    if dimension == 0:
        raise EmbeddingResponseError("Embedding 向量不能为空")
    if expected_dimensions is not None and dimension != expected_dimensions:
        raise EmbeddingDimensionMismatchError(
            f"Embedding 维度不匹配：配置 {expected_dimensions}，实际 {dimension}"
        )

    norms = tuple(vector_norm(vector) for vector in vectors)
    if any(norm == 0 for norm in norms):
        raise EmbeddingResponseError("Embedding 响应包含零向量")

    return ParsedEmbeddings(
        vectors=vectors,
        dimension=dimension,
        norms=norms,
        response_model=parsed.model,
        usage=parsed.usage,
    )

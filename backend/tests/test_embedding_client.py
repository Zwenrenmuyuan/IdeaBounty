from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from pydantic import SecretStr, ValidationError

import idea_bounty.api.dependencies.embedding as embedding_dependency
from idea_bounty.embedding import (
    EXPECTED_EMBEDDING_DIMENSIONS,
    EmbeddingProviderError,
    EmbeddingSettings,
    OpenAICompatibleEmbeddingProvider,
    build_embedding_text,
)
from idea_bounty.models import FailureCode, InformationSource
from idea_bounty.schemas.ai import NormalizedField
from tests.ai_fakes import make_evaluation_output


def make_settings(*, max_retries: int = 0) -> EmbeddingSettings:
    return EmbeddingSettings(
        base_url="https://embedding.example/v1",
        api_key=SecretStr("embedding-secret-key"),
        model_id="BAAI/bge-m3",
        dimensions=EXPECTED_EMBEDDING_DIMENSIONS,
        timeout_seconds=10,
        max_retries=max_retries,
    )


def embedding_response(
    request: httpx.Request,
    *,
    dimensions: int = EXPECTED_EMBEDDING_DIMENSIONS,
    vector: list[float] | None = None,
) -> httpx.Response:
    values = vector or [1.0, *([0.0] * (dimensions - 1))]
    return httpx.Response(
        200,
        headers={"x-request-id": "embedding-request-123"},
        json={
            "data": [{"object": "embedding", "index": 0, "embedding": values}],
            "model": "returned-bge-m3",
            "usage": {"prompt_tokens": 21, "total_tokens": 21},
        },
        request=request,
    )


def test_build_embedding_text_uses_only_ordered_shared_fields() -> None:
    content = make_evaluation_output().normalized_content()
    content.context = NormalizedField(value=None, source=InformationSource.UNKNOWN)
    content.proposed_solution = NormalizedField(
        value="不应进入向量的具体方案",
        source=InformationSource.EXPLICIT,
    )
    content.solution_present = True
    content.unsupported_claims = ["百亿市场"]

    text = build_embedding_text(content)

    assert text == (
        "目标用户：社区独居老人\n核心痛点：行动不便时买菜困难\n期望结果：更方便地获得日常食材"
    )
    assert "具体方案" not in text
    assert "百亿市场" not in text


def test_settings_reject_dimensions_other_than_database_contract() -> None:
    with pytest.raises(ValidationError):
        EmbeddingSettings(
            base_url="https://embedding.example/v1",
            api_key=SecretStr("secret"),
            model_id="other-model",
            dimensions=768,
        )


def test_request_dependency_loads_configuration_only_when_embedding_is_called(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def invalid_settings() -> None:
        raise ValueError("invalid config")

    monkeypatch.setattr(embedding_dependency, "get_embedding_settings", invalid_settings)

    provider = embedding_dependency.get_embedding_provider()

    with pytest.raises(EmbeddingProviderError) as error_info:
        provider.embed("只有真正生成向量时才读取配置")
    assert error_info.value.failure_code is FailureCode.PROVIDER_CONFIG_ERROR


def test_client_sends_openai_compatible_single_item_request() -> None:
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return embedding_response(request)

    provider = OpenAICompatibleEmbeddingProvider(
        make_settings(),
        transport=httpx.MockTransport(handler),
    )

    result = provider.embed("目标用户：社区老人\n核心痛点：买菜困难")

    assert captured_request is not None
    assert str(captured_request.url) == "https://embedding.example/v1/embeddings"
    assert captured_request.headers["authorization"] == "Bearer embedding-secret-key"
    assert json.loads(captured_request.content) == {
        "model": "BAAI/bge-m3",
        "input": ["目标用户：社区老人\n核心痛点：买菜困难"],
        "encoding_format": "float",
    }
    assert result.model_id == "BAAI/bge-m3"
    assert result.response_model == "returned-bge-m3"
    assert result.dimensions == EXPECTED_EMBEDDING_DIMENSIONS
    assert result.request_id == "embedding-request-123"
    assert result.total_tokens == 21
    assert result.attempts == 1


def test_client_retries_transient_http_errors() -> None:
    call_count = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(500, request=request)
        if call_count == 2:
            return httpx.Response(429, request=request)
        return embedding_response(request)

    provider = OpenAICompatibleEmbeddingProvider(
        make_settings(max_retries=2),
        transport=httpx.MockTransport(handler),
        sleep=delays.append,
        jitter=lambda: 0,
    )

    result = provider.embed("用于验证重试的中性文本")

    assert call_count == 3
    assert delays == [1, 2]
    assert result.attempts == 3


@pytest.mark.parametrize(
    ("status_code", "failure_code"),
    [
        (400, FailureCode.PROVIDER_CONFIG_ERROR),
        (401, FailureCode.PROVIDER_AUTH_ERROR),
        (403, FailureCode.PROVIDER_AUTH_ERROR),
        (404, FailureCode.PROVIDER_CONFIG_ERROR),
        (422, FailureCode.PROVIDER_CONFIG_ERROR),
    ],
)
def test_client_does_not_retry_configuration_errors(
    status_code: int,
    failure_code: FailureCode,
) -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(status_code, request=request)

    provider = OpenAICompatibleEmbeddingProvider(
        make_settings(max_retries=3),
        transport=httpx.MockTransport(handler),
        sleep=lambda _: pytest.fail("不可重试错误不应等待"),
    )

    with pytest.raises(EmbeddingProviderError) as error_info:
        provider.embed("不会重试的中性文本")

    assert call_count == 1
    assert error_info.value.failure_code is failure_code
    assert error_info.value.http_status == status_code
    assert "embedding-secret-key" not in str(error_info.value)


@pytest.mark.parametrize(
    "network_error",
    [httpx.ReadTimeout("timeout"), httpx.ConnectError("connection failed")],
)
def test_client_retries_network_errors(network_error: httpx.RequestError) -> None:
    call_count = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise network_error
        return embedding_response(request)

    provider = OpenAICompatibleEmbeddingProvider(
        make_settings(max_retries=1),
        transport=httpx.MockTransport(handler),
        sleep=delays.append,
        jitter=lambda: 0,
    )

    result = provider.embed("网络恢复后的中性文本")

    assert call_count == 2
    assert delays == [1]
    assert result.attempts == 2


@pytest.mark.parametrize(
    ("response_factory", "failure_code"),
    [
        (
            lambda request: httpx.Response(200, text="not-json", request=request),
            FailureCode.INVALID_AI_RESPONSE,
        ),
        (
            lambda request: httpx.Response(200, json={"data": []}, request=request),
            FailureCode.INVALID_AI_RESPONSE,
        ),
        (
            lambda request: embedding_response(request, vector=[0.0] * 1024),
            FailureCode.INVALID_AI_RESPONSE,
        ),
        (
            lambda request: embedding_response(request, dimensions=768),
            FailureCode.EMBEDDING_DIMENSION_MISMATCH,
        ),
    ],
)
def test_client_rejects_invalid_embedding_responses(
    response_factory: Callable[[httpx.Request], httpx.Response],
    failure_code: FailureCode,
) -> None:
    provider = OpenAICompatibleEmbeddingProvider(
        make_settings(max_retries=3),
        transport=httpx.MockTransport(response_factory),
        sleep=lambda _: pytest.fail("结构和维度错误不应重试"),
    )

    with pytest.raises(EmbeddingProviderError) as error_info:
        provider.embed("服务端返回异常时的中性文本")

    assert error_info.value.failure_code is failure_code

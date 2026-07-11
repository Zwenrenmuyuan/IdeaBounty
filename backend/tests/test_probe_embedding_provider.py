from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from pydantic import SecretStr

from scripts.probe_embedding_provider import (
    SAMPLES,
    ProbeFailure,
    ProbeSettings,
    analyze_semantics,
    build_embeddings_url,
    cosine_similarity,
    parse_embedding_response,
    run_probe,
    send_probe,
)


def make_settings(*, dimensions: int | None = None) -> ProbeSettings:
    return ProbeSettings(
        base_url="https://embedding.example/v1",
        api_key=SecretStr("embedding-secret-key"),
        model_id="test-embedding-model",
        timeout_seconds=10,
        dimensions=dimensions,
    )


def passing_vectors() -> list[list[float]]:
    return [
        [1, 0, 0, 0, 0, 0],
        [0.9, 0, 0, 0.1, 0, 0],
        [0, 0, 0, 1, 0, 0],
        [0, 1, 0, 0, 0, 0],
        [0, 0.9, 0, 0, 0.1, 0],
        [0, 0, 0, 0, 1, 0],
        [0, 0, 1, 0, 0, 0],
        [0, 0, 0.9, 0, 0, 0.1],
        [0, 0, 0, 0, 0, 1],
        [1, 0, 0, 0, 0, 0],
    ]


def embedding_response(
    request: httpx.Request,
    *,
    vectors: list[list[float]] | None = None,
    reverse: bool = False,
) -> httpx.Response:
    selected_vectors = vectors or passing_vectors()
    data = [
        {"object": "embedding", "index": index, "embedding": vector}
        for index, vector in enumerate(selected_vectors)
    ]
    if reverse:
        data.reverse()
    return httpx.Response(
        200,
        headers={"x-request-id": "embedding-request-123"},
        json={
            "object": "list",
            "model": "returned-embedding-model",
            "data": data,
            "usage": {"prompt_tokens": 123, "total_tokens": 123},
        },
        request=request,
    )


def test_build_embeddings_url() -> None:
    assert build_embeddings_url("https://provider.example/v1/") == (
        "https://provider.example/v1/embeddings"
    )
    assert build_embeddings_url("https://provider.example/v1/embeddings") == (
        "https://provider.example/v1/embeddings"
    )
    with pytest.raises(ProbeFailure, match="不能为空"):
        build_embeddings_url("  ")


def test_send_probe_uses_batch_float_format_and_restores_index_order() -> None:
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return embedding_response(request, reverse=True)

    result = send_probe(
        make_settings(dimensions=6),
        transport=httpx.MockTransport(handler),
    )

    assert captured_request is not None
    assert str(captured_request.url) == "https://embedding.example/v1/embeddings"
    assert captured_request.headers["authorization"] == "Bearer embedding-secret-key"
    payload = json.loads(captured_request.content)
    assert payload == {
        "model": "test-embedding-model",
        "input": [sample.text for sample in SAMPLES],
        "encoding_format": "float",
    }
    assert result.embeddings.vectors[0] == tuple(passing_vectors()[0])
    assert result.embeddings.dimension == 6
    assert result.embeddings.response_model == "returned-embedding-model"
    assert result.request_id == "embedding-request-123"


def response_body_for(vectors: list[list[object]], indices: list[int] | None = None) -> str:
    selected_indices = indices or list(range(len(vectors)))
    return json.dumps(
        {
            "data": [
                {"index": index, "embedding": vector}
                for index, vector in zip(selected_indices, vectors, strict=True)
            ]
        }
    )


@pytest.mark.parametrize(
    ("body", "expected_count", "expected_dimensions", "message"),
    [
        (response_body_for([[1.0, 0.0]]), 2, None, "向量数量不符"),
        (
            response_body_for([[1.0, 0.0], [0.0, 1.0]], [0, 0]),
            2,
            None,
            "重复 index",
        ),
        (
            response_body_for([[1.0, 0.0], [0.0, 1.0]], [0, 2]),
            2,
            None,
            "index 越界",
        ),
        (
            response_body_for([[1.0, 0.0], [0.0, 1.0, 0.0]]),
            2,
            None,
            "维度不一致",
        ),
        (response_body_for([[1.0, 0.0]]), 1, 3, "维度不匹配"),
        (response_body_for([[0.0, 0.0]]), 1, None, "零向量"),
        (response_body_for([[1.0, "bad"]]), 1, None, "响应结构无效"),
        (response_body_for([[1.0, float("nan")]]), 1, None, "响应结构无效"),
        (response_body_for([[1.0, float("inf")]]), 1, None, "响应结构无效"),
    ],
)
def test_parse_embedding_response_rejects_invalid_vectors(
    body: str,
    expected_count: int,
    expected_dimensions: int | None,
    message: str,
) -> None:
    with pytest.raises(ProbeFailure, match=message):
        parse_embedding_response(
            body,
            expected_count=expected_count,
            expected_dimensions=expected_dimensions,
        )


def test_cosine_similarity_and_semantic_ranking_pass() -> None:
    assert cosine_similarity((1.0, 0.0), (1.0, 0.0)) == pytest.approx(1.0)
    assert cosine_similarity((1.0, 0.0), (0.0, 1.0)) == pytest.approx(0.0)

    analysis = analyze_semantics(tuple(tuple(vector) for vector in passing_vectors()))

    assert analysis.exact_duplicate_similarity == pytest.approx(1.0)
    assert not analysis.failures
    assert all(case.passed and case.margin > 0 for case in analysis.cases)
    assert [case.ranking[0][0] for case in analysis.cases] == [
        "invoice_paraphrase",
        "expiry_paraphrase",
        "appointment_paraphrase",
    ]


def test_exact_duplicate_allows_small_provider_variance() -> None:
    vectors = passing_vectors()
    vectors[9] = [1, 0.02, 0, 0, 0, 0]

    analysis = analyze_semantics(tuple(tuple(vector) for vector in vectors))

    assert 0.999 < analysis.exact_duplicate_similarity < 0.9999
    assert not analysis.failures


def test_semantic_ranking_failure_returns_exit_code_two(capsys: pytest.CaptureFixture[str]) -> None:
    vectors = passing_vectors()
    vectors[1] = [0, 1, 0, 0, 0, 0]

    def handler(request: httpx.Request) -> httpx.Response:
        return embedding_response(request, vectors=vectors)

    exit_code = run_probe(
        make_settings(dimensions=6),
        runs=1,
        transport=httpx.MockTransport(handler),
    )

    assert exit_code == 2
    assert "语义改写不是 Top-1" in capsys.readouterr().out


def test_run_probe_uses_requested_run_count(capsys: pytest.CaptureFixture[str]) -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return embedding_response(request)

    exit_code = run_probe(
        make_settings(dimensions=6),
        runs=3,
        transport=httpx.MockTransport(handler),
    )

    assert exit_code == 0
    assert call_count == 3
    assert "3 次探测" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("status_code", "category"),
    [
        (400, "请求参数"),
        (401, "鉴权失败"),
        (403, "鉴权失败"),
        (404, "Model ID 不存在"),
        (422, "请求参数"),
        (429, "限流或余额不足"),
        (500, "服务内部错误"),
    ],
)
def test_send_probe_classifies_http_errors_and_redacts_secret(
    status_code: int,
    category: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            text="provider error embedding-secret-key",
            request=request,
        )

    with pytest.raises(ProbeFailure) as error_info:
        send_probe(make_settings(), transport=httpx.MockTransport(handler))

    message = str(error_info.value)
    assert category in message
    assert "embedding-secret-key" not in message
    assert "***" in message


@pytest.mark.parametrize(
    ("error_factory", "message"),
    [
        (lambda request: httpx.ReadTimeout("timeout", request=request), "请求超时"),
        (lambda request: httpx.ConnectError("failed", request=request), "网络连接失败"),
    ],
)
def test_send_probe_handles_network_errors(
    error_factory: Callable[[httpx.Request], httpx.RequestError],
    message: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error_factory(request)

    with pytest.raises(ProbeFailure, match=message):
        send_probe(make_settings(), transport=httpx.MockTransport(handler))

from __future__ import annotations

import json
import logging
from collections.abc import Callable

import httpx
import pytest
from pydantic import SecretStr

from idea_bounty.ai import AISettings, EvaluationProviderError
from idea_bounty.ai.client import OpenAICompatibleEvaluationProvider
from idea_bounty.models import FailureCode
from tests.ai_fakes import evaluation_output_data, make_evaluation_output


def make_settings(*, max_retries: int = 0) -> AISettings:
    return AISettings(
        base_url="https://provider.example/v1",
        api_key=SecretStr("super-secret-key"),
        model_id="test-model",
        timeout_seconds=10,
        max_retries=max_retries,
    )


def completion_response(
    request: httpx.Request,
    *,
    content: str | None = None,
    finish_reason: str = "stop",
) -> httpx.Response:
    return httpx.Response(
        200,
        headers={"x-request-id": "request-123"},
        json={
            "choices": [
                {
                    "message": {
                        "content": (
                            make_evaluation_output().model_dump_json()
                            if content is None
                            else content
                        ),
                    },
                    "finish_reason": finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": 101,
                "completion_tokens": 202,
                "total_tokens": 303,
            },
        },
        request=request,
    )


def test_client_sends_json_mode_schema_and_untrusted_user_message() -> None:
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return completion_response(request)

    provider = OpenAICompatibleEvaluationProvider(
        make_settings(),
        transport=httpx.MockTransport(handler),
    )

    result = provider.evaluate("这是原始投稿，不应该进入系统指令")

    assert captured_request is not None
    assert str(captured_request.url) == "https://provider.example/v1/chat/completions"
    assert captured_request.headers["authorization"] == "Bearer super-secret-key"
    payload = json.loads(captured_request.content)
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["temperature"] == 0.2
    assert "EvaluationOutput" in payload["messages"][0]["content"]
    assert "允许同时命中多个值" in payload["messages"][0]["content"]
    assert "必须同时包含 prompt_injection" in payload["messages"][0]["content"]
    assert 'source="unknown" 时填写 value' in payload["messages"][0]["content"]
    assert "只有目标、愿望、期望结果" in payload["messages"][0]["content"]
    assert "target_audience, pain_point, context" in payload["messages"][0]["content"]
    assert '["pain_point","desired_outcome"]' in payload["messages"][0]["content"]
    assert (
        "input_decision=accept 时，clarification_question 必须为 null"
        in payload["messages"][0]["content"]
    )
    assert '"EvidenceField"' in payload["messages"][0]["content"]
    assert "这是原始投稿" not in payload["messages"][0]["content"]
    assert json.loads(payload["messages"][1]["content"]) == {
        "raw_content": "这是原始投稿，不应该进入系统指令"
    }
    assert result.request_id == "request-123"
    assert result.total_tokens == 303
    assert result.attempts == 1


def test_client_retries_transient_and_invalid_output_errors() -> None:
    call_count = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(500, request=request)
        if call_count == 2:
            return completion_response(request, content="{}")
        return completion_response(request)

    provider = OpenAICompatibleEvaluationProvider(
        make_settings(max_retries=2),
        transport=httpx.MockTransport(handler),
        sleep=delays.append,
        jitter=lambda: 0,
    )

    result = provider.evaluate("这是用于验证自动重试的投稿")

    assert call_count == 3
    assert delays == [1, 2]
    assert result.attempts == 3


def test_client_logs_safe_validation_error_signature(
    caplog: pytest.LogCaptureFixture,
) -> None:
    invalid_output = evaluation_output_data()
    invalid_output["current_alternative"] = {
        "value": "不应写入日志的模型内容",
        "source": "unknown",
    }
    provider = OpenAICompatibleEvaluationProvider(
        make_settings(),
        transport=httpx.MockTransport(
            lambda request: completion_response(
                request,
                content=json.dumps(invalid_output, ensure_ascii=False),
            )
        ),
    )

    with (
        caplog.at_level(logging.WARNING, logger="idea_bounty.ai.client"),
        pytest.raises(EvaluationProviderError),
    ):
        provider.evaluate("不应写入日志的用户原文")

    assert "current_alternative:normalized_unknown_has_value" in caplog.text
    assert "不应写入日志的模型内容" not in caplog.text
    assert "不应写入日志的用户原文" not in caplog.text
    assert "super-secret-key" not in caplog.text


@pytest.mark.parametrize(
    ("status_code", "failure_code"),
    [
        (400, FailureCode.JSON_MODE_UNSUPPORTED),
        (401, FailureCode.PROVIDER_AUTH_ERROR),
        (403, FailureCode.PROVIDER_AUTH_ERROR),
        (404, FailureCode.PROVIDER_CONFIG_ERROR),
        (422, FailureCode.JSON_MODE_UNSUPPORTED),
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

    provider = OpenAICompatibleEvaluationProvider(
        make_settings(max_retries=3),
        transport=httpx.MockTransport(handler),
        sleep=lambda _: pytest.fail("不可重试错误不应等待"),
    )

    with pytest.raises(EvaluationProviderError) as error_info:
        provider.evaluate("这是不会自动重试的投稿")

    assert call_count == 1
    assert error_info.value.failure_code is failure_code
    assert error_info.value.http_status == status_code
    assert "super-secret-key" not in str(error_info.value)


def test_client_exhausts_rate_limit_retries() -> None:
    call_count = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(429, request=request)

    provider = OpenAICompatibleEvaluationProvider(
        make_settings(max_retries=2),
        transport=httpx.MockTransport(handler),
        sleep=delays.append,
        jitter=lambda: 0.25,
    )

    with pytest.raises(EvaluationProviderError) as error_info:
        provider.evaluate("这是持续遇到限流的投稿")

    assert call_count == 3
    assert delays == [1.25, 2.25]
    assert error_info.value.failure_code is FailureCode.PROVIDER_RATE_LIMITED


@pytest.mark.parametrize(
    "network_error",
    [
        httpx.ReadTimeout("timeout"),
        httpx.ConnectError("connection failed"),
    ],
)
def test_client_retries_network_errors(
    network_error: httpx.RequestError,
) -> None:
    call_count = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise network_error
        return completion_response(request)

    provider = OpenAICompatibleEvaluationProvider(
        make_settings(max_retries=1),
        transport=httpx.MockTransport(handler),
        sleep=delays.append,
        jitter=lambda: 0,
    )

    result = provider.evaluate("这是用于验证网络错误恢复的投稿")

    assert call_count == 2
    assert delays == [1]
    assert result.attempts == 2


@pytest.mark.parametrize(
    "response_factory",
    [
        lambda request: httpx.Response(200, text="not-json", request=request),
        lambda request: httpx.Response(200, json={}, request=request),
        lambda request: completion_response(request, content=""),
        lambda request: completion_response(request, finish_reason="length"),
        lambda request: httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": None, "refusal": "refused"},
                        "finish_reason": "stop",
                    }
                ]
            },
            request=request,
        ),
    ],
)
def test_client_rejects_invalid_responses(
    response_factory: Callable[[httpx.Request], httpx.Response],
) -> None:
    provider = OpenAICompatibleEvaluationProvider(
        make_settings(),
        transport=httpx.MockTransport(response_factory),
    )

    with pytest.raises(EvaluationProviderError) as error_info:
        provider.evaluate("这是服务端响应异常的投稿")

    assert error_info.value.failure_code is FailureCode.INVALID_AI_RESPONSE

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from idea_bounty.ai import AISettings, DuplicateProviderError, OpenAICompatibleDuplicateProvider
from idea_bounty.models import FailureCode
from scripts.probe_duplicate_provider import PROBE_CASES
from tests.test_probe_duplicate_provider import output_data


def make_settings(*, max_retries: int = 0) -> AISettings:
    return AISettings(
        base_url="https://provider.example/v1",
        api_key=SecretStr("duplicate-secret-key"),
        model_id="test-model",
        timeout_seconds=10,
        max_retries=max_retries,
    )


def completion_response(
    request: httpx.Request,
    *,
    content: str,
    finish_reason: str = "stop",
) -> httpx.Response:
    return httpx.Response(
        200,
        headers={"x-request-id": "duplicate-request"},
        json={
            "choices": [
                {
                    "message": {"content": content},
                    "finish_reason": finish_reason,
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        },
        request=request,
    )


def test_duplicate_client_sends_safe_json_mode_payload() -> None:
    case = PROBE_CASES[0]
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return completion_response(
            request,
            content=json.dumps(output_data(case), ensure_ascii=False),
        )

    provider = OpenAICompatibleDuplicateProvider(
        make_settings(),
        transport=httpx.MockTransport(handler),
    )

    result = provider.judge(case.comparison)

    assert captured_request is not None
    payload = json.loads(captured_request.content)
    serialized = json.dumps(payload, ensure_ascii=False)
    assert str(captured_request.url) == "https://provider.example/v1/chat/completions"
    assert captured_request.headers["authorization"] == "Bearer duplicate-secret-key"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["temperature"] == 0.2
    assert "raw_content" not in serialized
    assert "cosine_similarity" not in serialized
    assert "embedding" not in serialized.lower()
    assert result.output.matched_internal_id == case.expected_matched_internal_id
    assert result.request_id == "duplicate-request"
    assert result.total_tokens == 30


def test_duplicate_client_retries_invalid_contract_and_server_error() -> None:
    case = PROBE_CASES[0]
    calls = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(500, request=request)
        if calls == 2:
            return completion_response(request, content="{}")
        return completion_response(
            request,
            content=json.dumps(output_data(case), ensure_ascii=False),
        )

    provider = OpenAICompatibleDuplicateProvider(
        make_settings(max_retries=2),
        transport=httpx.MockTransport(handler),
        sleep=delays.append,
        jitter=lambda: 0,
    )

    result = provider.judge(case.comparison)

    assert calls == 3
    assert delays == [1, 2]
    assert result.attempts == 3


@pytest.mark.parametrize(
    ("status_code", "failure_code"),
    [
        (400, FailureCode.JSON_MODE_UNSUPPORTED),
        (401, FailureCode.PROVIDER_AUTH_ERROR),
        (404, FailureCode.PROVIDER_CONFIG_ERROR),
        (429, FailureCode.PROVIDER_RATE_LIMITED),
    ],
)
def test_duplicate_client_classifies_http_errors(
    status_code: int,
    failure_code: FailureCode,
) -> None:
    case = PROBE_CASES[0]
    provider = OpenAICompatibleDuplicateProvider(
        make_settings(),
        transport=httpx.MockTransport(lambda request: httpx.Response(status_code, request=request)),
    )

    with pytest.raises(DuplicateProviderError) as error_info:
        provider.judge(case.comparison)

    assert error_info.value.failure_code is failure_code
    assert "duplicate-secret-key" not in str(error_info.value)

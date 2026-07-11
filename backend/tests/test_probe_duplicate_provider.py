from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from pydantic import SecretStr

from idea_bounty.models import DuplicateVerdict
from scripts.probe_duplicate_provider import (
    PROBE_CASES,
    ProbeCase,
    ProbeFailure,
    ProbeSettings,
    build_chat_completions_url,
    check_behavior,
    classify_http_error,
    run_probe,
    send_case,
)


def make_settings() -> ProbeSettings:
    return ProbeSettings(
        base_url="https://provider.example/v1",
        api_key=SecretStr("duplicate-secret-key"),
        model_id="test-model",
        timeout_seconds=10,
        temperature=0.2,
    )


def output_data(case: ProbeCase) -> dict[str, object]:
    return {
        "pain_relation": case.expected_pain_relation.value,
        "solution_relation": case.expected_solution_relation.value,
        "verdict": case.expected_verdict.value,
        "matched_internal_id": case.expected_matched_internal_id,
        "same_aspects": (
            ["pain_point"] if case.expected_verdict is not DuplicateVerdict.NOVEL else []
        ),
        "different_aspects": (
            ["proposed_solution"]
            if case.expected_verdict is DuplicateVerdict.RELATED
            else (["pain_point"] if case.expected_verdict is DuplicateVerdict.NOVEL else [])
        ),
        "added_value": "固定测试结论",
        "confidence": "high",
        "reason": "固定测试理由",
    }


def completion_response(
    request: httpx.Request,
    case: ProbeCase,
    *,
    content: str | None = None,
    finish_reason: str = "stop",
) -> httpx.Response:
    return httpx.Response(
        200,
        headers={"x-request-id": f"request-{case.case_id}"},
        json={
            "choices": [
                {
                    "message": {
                        "content": (
                            json.dumps(output_data(case), ensure_ascii=False)
                            if content is None
                            else content
                        )
                    },
                    "finish_reason": finish_reason,
                }
            ],
            "usage": {"total_tokens": 123},
        },
        request=request,
    )


def test_probe_cases_cover_three_verdicts_equally() -> None:
    assert len(PROBE_CASES) == 9
    assert {case.case_id for case in PROBE_CASES} == {
        "duplicate_paraphrase",
        "duplicate_same_solution",
        "duplicate_audience_wording",
        "related_different_solution",
        "related_new_solution",
        "related_pain",
        "novel_same_industry",
        "novel_different_payer",
        "novel_surface_keywords",
    }
    assert [case.expected_verdict for case in PROBE_CASES].count(DuplicateVerdict.DUPLICATE) == 3
    assert [case.expected_verdict for case in PROBE_CASES].count(DuplicateVerdict.RELATED) == 3
    assert [case.expected_verdict for case in PROBE_CASES].count(DuplicateVerdict.NOVEL) == 3


def test_send_case_uses_ai_config_json_mode_and_safe_projection() -> None:
    captured_request: httpx.Request | None = None
    case = PROBE_CASES[0]

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return completion_response(request, case)

    result = send_case(
        make_settings(),
        case,
        transport=httpx.MockTransport(handler),
    )

    assert captured_request is not None
    assert str(captured_request.url) == "https://provider.example/v1/chat/completions"
    assert captured_request.headers["authorization"] == "Bearer duplicate-secret-key"
    payload = json.loads(captured_request.content)
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["temperature"] == 0.2
    assert "raw_content" not in json.dumps(payload, ensure_ascii=False)
    assert result.output.verdict is DuplicateVerdict.DUPLICATE
    assert result.request_id == "request-duplicate_paraphrase"
    assert result.total_tokens == 123


def test_check_behavior_reports_valid_but_wrong_judgment() -> None:
    case = PROBE_CASES[0]
    wrong_data = output_data(PROBE_CASES[3])
    wrong_data["matched_internal_id"] = 101
    from idea_bounty.schemas.duplicate import validate_duplicate_judgment_json

    output = validate_duplicate_judgment_json(
        json.dumps(wrong_data, ensure_ascii=False),
        case.comparison,
    )

    failures = check_behavior(case, output)

    assert any("verdict" in failure for failure in failures)
    assert any("solution_relation" in failure for failure in failures)


def test_run_probe_returns_zero_when_all_cases_pass(
    capsys: pytest.CaptureFixture[str],
) -> None:
    call_index = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_index
        case = PROBE_CASES[call_index]
        call_index += 1
        return completion_response(request, case)

    exit_code = run_probe(
        make_settings(),
        show_output=False,
        transport=httpx.MockTransport(handler),
    )

    assert exit_code == 0
    assert call_index == 9
    output = capsys.readouterr().out
    assert "9/9" in output
    assert "Token 用量：1107" in output


def test_run_probe_returns_two_for_behavior_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    call_index = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_index
        case = PROBE_CASES[call_index]
        call_index += 1
        if call_index == 1:
            wrong = output_data(PROBE_CASES[3])
            wrong["matched_internal_id"] = 101
            return completion_response(
                request,
                case,
                content=json.dumps(wrong, ensure_ascii=False),
            )
        return completion_response(request, case)

    exit_code = run_probe(
        make_settings(),
        show_output=False,
        transport=httpx.MockTransport(handler),
    )

    assert exit_code == 2
    assert "verdict 期望 duplicate" in capsys.readouterr().out


@pytest.mark.parametrize(
    "response_factory",
    [
        lambda request, case: httpx.Response(200, text="not-json", request=request),
        lambda request, case: httpx.Response(200, json={}, request=request),
        lambda request, case: completion_response(request, case, content="{}"),
        lambda request, case: completion_response(request, case, content=""),
        lambda request, case: completion_response(request, case, finish_reason="length"),
    ],
)
def test_send_case_rejects_invalid_responses(
    response_factory: Callable[[httpx.Request, ProbeCase], httpx.Response],
) -> None:
    case = PROBE_CASES[0]

    with pytest.raises(ProbeFailure):
        send_case(
            make_settings(),
            case,
            transport=httpx.MockTransport(lambda request: response_factory(request, case)),
        )


@pytest.mark.parametrize(
    ("status_code", "category"),
    [
        (400, "请求参数"),
        (401, "鉴权失败"),
        (403, "鉴权失败"),
        (404, "Model ID 不存在"),
        (422, "请求参数"),
        (429, "限流或余额不足"),
        (500, "模型服务内部错误"),
    ],
)
def test_send_case_classifies_http_errors_and_redacts_secret(
    status_code: int,
    category: str,
) -> None:
    case = PROBE_CASES[0]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            text="provider error duplicate-secret-key",
            request=request,
        )

    with pytest.raises(ProbeFailure) as error_info:
        send_case(make_settings(), case, transport=httpx.MockTransport(handler))

    message = str(error_info.value)
    assert category in message
    assert "duplicate-secret-key" not in message
    assert "***" in message


@pytest.mark.parametrize(
    ("error_factory", "message"),
    [
        (lambda request: httpx.ReadTimeout("timeout", request=request), "请求超时"),
        (lambda request: httpx.ConnectError("failed", request=request), "网络连接失败"),
    ],
)
def test_send_case_handles_network_errors(
    error_factory: Callable[[httpx.Request], httpx.RequestError],
    message: str,
) -> None:
    case = PROBE_CASES[0]

    def handler(request: httpx.Request) -> httpx.Response:
        raise error_factory(request)

    with pytest.raises(ProbeFailure, match=message):
        send_case(make_settings(), case, transport=httpx.MockTransport(handler))


def test_build_url_and_error_classification() -> None:
    assert build_chat_completions_url("https://provider.example/v1/") == (
        "https://provider.example/v1/chat/completions"
    )
    assert (
        build_chat_completions_url("https://provider.example/v1/chat/completions")
        == "https://provider.example/v1/chat/completions"
    )
    assert classify_http_error(418) == "HTTP 请求失败"
    with pytest.raises(ProbeFailure, match="不能为空"):
        build_chat_completions_url("  ")

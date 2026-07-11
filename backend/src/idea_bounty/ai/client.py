from __future__ import annotations

import json
import logging
import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from pydantic import ValidationError

from idea_bounty.ai.config import AISettings
from idea_bounty.ai.prompts import build_evaluation_payload
from idea_bounty.models import FailureCode
from idea_bounty.schemas.ai import EvaluationOutput

logger = logging.getLogger(__name__)

SAFE_VALIDATION_PATH_PART = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")


def _validation_error_signature(error: ValidationError) -> str:
    """生成不含模型值和用户内容的稳定校验错误签名。"""

    signatures: list[str] = []
    for detail in error.errors(include_url=False, include_input=False)[:5]:
        path_parts: list[str] = []
        for part in detail["loc"]:
            if isinstance(part, int):
                path_parts.append(str(part))
            else:
                text = str(part)
                path_parts.append(text if SAFE_VALIDATION_PATH_PART.fullmatch(text) else "<field>")
        path = ".".join(path_parts) or "<root>"
        signatures.append(f"{path}:{detail['type']}")
    return "|".join(signatures)


@dataclass(frozen=True, slots=True)
class EvaluationProviderResult:
    """一次成功 AI 评估及其安全调用元数据。"""

    output: EvaluationOutput
    model_id: str
    request_id: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    elapsed_seconds: float
    attempts: int


class EvaluationProviderError(RuntimeError):
    """包含安全失败码和是否可以重试的 AI 调用错误。"""

    def __init__(
        self,
        failure_code: FailureCode,
        message: str,
        *,
        retryable: bool,
        http_status: int | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_code = failure_code
        self.retryable = retryable
        self.http_status = http_status
        self.request_id = request_id


class EvaluationProvider(Protocol):
    """供投稿服务和测试替换的评估提供者接口。"""

    def evaluate(self, raw_content: str) -> EvaluationProviderResult:
        """评估一条不可信用户原文。"""


class UnavailableEvaluationProvider:
    """在 AI 配置无效时延迟返回安全错误。"""

    def evaluate(self, raw_content: str) -> EvaluationProviderResult:
        del raw_content
        raise EvaluationProviderError(
            FailureCode.PROVIDER_CONFIG_ERROR,
            "AI 服务配置无效",
            retryable=False,
        )


class OpenAICompatibleEvaluationProvider:
    """使用 Chat Completions JSON mode 的同步评估客户端。"""

    def __init__(
        self,
        settings: AISettings,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._sleep = sleep
        self._jitter = jitter or (lambda: random.uniform(0, 0.25))

    def evaluate(self, raw_content: str) -> EvaluationProviderResult:
        endpoint = self._build_endpoint(self._settings.base_url)
        payload = build_evaluation_payload(
            self._settings.model_id,
            raw_content,
            temperature=self._settings.temperature,
        )
        headers = {
            "Authorization": f"Bearer {self._settings.api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }

        with httpx.Client(
            timeout=self._settings.timeout_seconds,
            transport=self._transport,
        ) as client:
            for attempt_index in range(self._settings.max_retries + 1):
                try:
                    return self._evaluate_once(
                        client,
                        endpoint,
                        headers,
                        payload,
                        attempts=attempt_index + 1,
                    )
                except EvaluationProviderError as exc:
                    logger.warning(
                        "AI 评估尝试失败：model=%s attempt=%s code=%s status=%s "
                        "request_id=%s retryable=%s",
                        self._settings.model_id,
                        attempt_index + 1,
                        exc.failure_code.value,
                        exc.http_status,
                        exc.request_id,
                        exc.retryable,
                    )
                    if not exc.retryable or attempt_index >= self._settings.max_retries:
                        raise
                    delay = (2**attempt_index) + self._jitter()
                    logger.warning(
                        "AI 评估失败，将进行第 %s 次重试：model=%s code=%s delay=%.2fs",
                        attempt_index + 1,
                        self._settings.model_id,
                        exc.failure_code.value,
                        delay,
                    )
                    self._sleep(delay)

        raise RuntimeError("AI 重试循环未执行")  # pragma: no cover

    def _evaluate_once(
        self,
        client: httpx.Client,
        endpoint: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        *,
        attempts: int,
    ) -> EvaluationProviderResult:
        started_at = time.perf_counter()
        try:
            response = client.post(endpoint, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise EvaluationProviderError(
                FailureCode.PROVIDER_TIMEOUT,
                "AI 服务请求超时",
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise EvaluationProviderError(
                FailureCode.PROVIDER_ERROR,
                "AI 服务连接失败",
                retryable=True,
            ) from exc

        elapsed = time.perf_counter() - started_at
        self._raise_for_status(response)
        response_body = self._parse_response_body(response)
        content, finish_reason = self._extract_content(response_body)
        if finish_reason == "length":
            raise EvaluationProviderError(
                FailureCode.INVALID_AI_RESPONSE,
                "AI 输出因长度限制被截断",
                retryable=True,
            )

        try:
            output = EvaluationOutput.model_validate_json(content)
        except ValidationError as exc:
            logger.warning(
                "AI 输出未通过契约校验：model=%s errors=%s signature=%s",
                self._settings.model_id,
                exc.error_count(),
                _validation_error_signature(exc),
            )
            raise EvaluationProviderError(
                FailureCode.INVALID_AI_OUTPUT,
                "AI 输出未通过业务契约校验",
                retryable=True,
            ) from exc

        request_id = response.headers.get("x-request-id") or response.headers.get("request-id")
        prompt_tokens, completion_tokens, total_tokens = self._parse_usage(
            response_body.get("usage")
        )
        logger.info(
            "AI 评估成功：model=%s request_id=%s attempts=%s elapsed=%.2fs tokens=%s",
            self._settings.model_id,
            request_id,
            attempts,
            elapsed,
            total_tokens,
        )
        return EvaluationProviderResult(
            output=output,
            model_id=self._settings.model_id,
            request_id=request_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            elapsed_seconds=elapsed,
            attempts=attempts,
        )

    @staticmethod
    def _build_endpoint(base_url: str) -> str:
        normalized = base_url.strip().rstrip("/")
        if not normalized:
            raise EvaluationProviderError(
                FailureCode.PROVIDER_CONFIG_ERROR,
                "AI_BASE_URL 不能为空",
                retryable=False,
            )
        if normalized.endswith("/chat/completions"):
            return normalized
        return f"{normalized}/chat/completions"

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        status_code = response.status_code
        if status_code < 400:
            return
        if status_code in {400, 422}:
            code = FailureCode.JSON_MODE_UNSUPPORTED
            message = "AI 服务不支持当前 JSON mode 请求"
            retryable = False
        elif status_code in {401, 403}:
            code = FailureCode.PROVIDER_AUTH_ERROR
            message = "AI 服务鉴权失败"
            retryable = False
        elif status_code == 404:
            code = FailureCode.PROVIDER_CONFIG_ERROR
            message = "AI 服务地址或模型不存在"
            retryable = False
        elif status_code == 429:
            code = FailureCode.PROVIDER_RATE_LIMITED
            message = "AI 服务限流或余额不足"
            retryable = True
        elif status_code >= 500:
            code = FailureCode.PROVIDER_ERROR
            message = "AI 服务内部错误"
            retryable = True
        else:
            code = FailureCode.PROVIDER_CONFIG_ERROR
            message = "AI 服务拒绝请求"
            retryable = False
        request_id = response.headers.get("x-request-id") or response.headers.get("request-id")
        raise EvaluationProviderError(
            code,
            message,
            retryable=retryable,
            http_status=status_code,
            request_id=request_id,
        )

    @staticmethod
    def _parse_response_body(response: httpx.Response) -> dict[str, Any]:
        try:
            response_body = response.json()
        except json.JSONDecodeError as exc:
            raise EvaluationProviderError(
                FailureCode.INVALID_AI_RESPONSE,
                "AI 服务没有返回合法响应 JSON",
                retryable=True,
            ) from exc
        if not isinstance(response_body, dict):
            raise EvaluationProviderError(
                FailureCode.INVALID_AI_RESPONSE,
                "AI 服务响应不是 JSON 对象",
                retryable=True,
            )
        return response_body

    @staticmethod
    def _extract_content(response_body: dict[str, Any]) -> tuple[str, str | None]:
        try:
            choice = response_body["choices"][0]
            message = choice["message"]
            finish_reason = choice.get("finish_reason")
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise EvaluationProviderError(
                FailureCode.INVALID_AI_RESPONSE,
                "AI 响应缺少 choices[0].message",
                retryable=True,
            ) from exc
        if not isinstance(message, dict):
            raise EvaluationProviderError(
                FailureCode.INVALID_AI_RESPONSE,
                "AI 响应 message 格式错误",
                retryable=True,
            )
        if message.get("refusal"):
            raise EvaluationProviderError(
                FailureCode.INVALID_AI_RESPONSE,
                "AI 模型拒绝处理投稿",
                retryable=True,
            )
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise EvaluationProviderError(
                FailureCode.INVALID_AI_RESPONSE,
                "AI 模型没有返回非空内容",
                retryable=True,
            )
        return content, finish_reason if isinstance(finish_reason, str) else None

    @staticmethod
    def _parse_usage(usage: Any) -> tuple[int | None, int | None, int | None]:
        if not isinstance(usage, dict):
            return None, None, None

        def integer_or_none(value: Any) -> int | None:
            return value if isinstance(value, int) and not isinstance(value, bool) else None

        return (
            integer_or_none(usage.get("prompt_tokens")),
            integer_or_none(usage.get("completion_tokens")),
            integer_or_none(usage.get("total_tokens")),
        )

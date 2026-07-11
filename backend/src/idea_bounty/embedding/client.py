from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from idea_bounty.embedding.config import EmbeddingSettings
from idea_bounty.embedding.contracts import (
    EmbeddingDimensionMismatchError,
    EmbeddingResponseError,
    build_embeddings_url,
    parse_embedding_response,
)
from idea_bounty.models import FailureCode

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EmbeddingProviderResult:
    """一次成功 Embedding 调用及其安全元数据。"""

    vector: tuple[float, ...]
    model_id: str
    response_model: str | None
    dimensions: int
    request_id: str | None
    prompt_tokens: int | None
    total_tokens: int | None
    elapsed_seconds: float
    attempts: int


class EmbeddingProviderError(RuntimeError):
    """包含安全失败码和重试属性的 Embedding 调用错误。"""

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


class EmbeddingProvider(Protocol):
    """供投稿流水线和测试替换的 Embedding 提供者接口。"""

    def embed(self, text: str) -> EmbeddingProviderResult:
        """为一条中性化文本生成向量。"""


class UnavailableEmbeddingProvider:
    """在 Embedding 配置无效时延迟返回安全错误。"""

    def embed(self, text: str) -> EmbeddingProviderResult:
        del text
        raise EmbeddingProviderError(
            FailureCode.PROVIDER_CONFIG_ERROR,
            "Embedding 服务配置无效",
            retryable=False,
        )


class OpenAICompatibleEmbeddingProvider:
    """使用 OpenAI Embeddings 格式的同步客户端。"""

    def __init__(
        self,
        settings: EmbeddingSettings,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._sleep = sleep
        self._jitter = jitter or (lambda: random.uniform(0, 0.25))

    def embed(self, text: str) -> EmbeddingProviderResult:
        try:
            endpoint = build_embeddings_url(self._settings.base_url)
        except ValueError as exc:
            raise EmbeddingProviderError(
                FailureCode.PROVIDER_CONFIG_ERROR,
                "Embedding Base URL 配置无效",
                retryable=False,
            ) from exc
        payload = {
            "model": self._settings.model_id,
            "input": [text],
            "encoding_format": "float",
        }
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
                    return self._embed_once(
                        client,
                        endpoint,
                        headers,
                        payload,
                        attempts=attempt_index + 1,
                    )
                except EmbeddingProviderError as exc:
                    logger.warning(
                        "Embedding 尝试失败：model=%s attempt=%s code=%s status=%s "
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
                    self._sleep(delay)

        raise RuntimeError("Embedding 重试循环未执行")  # pragma: no cover

    def _embed_once(
        self,
        client: httpx.Client,
        endpoint: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        *,
        attempts: int,
    ) -> EmbeddingProviderResult:
        started_at = time.perf_counter()
        try:
            response = client.post(endpoint, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise EmbeddingProviderError(
                FailureCode.PROVIDER_TIMEOUT,
                "Embedding 服务请求超时",
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise EmbeddingProviderError(
                FailureCode.PROVIDER_ERROR,
                "Embedding 服务连接失败",
                retryable=True,
            ) from exc

        elapsed = time.perf_counter() - started_at
        self._raise_for_status(response)
        try:
            parsed = parse_embedding_response(
                response.text,
                expected_count=1,
                expected_dimensions=self._settings.dimensions,
            )
        except EmbeddingDimensionMismatchError as exc:
            raise EmbeddingProviderError(
                FailureCode.EMBEDDING_DIMENSION_MISMATCH,
                "Embedding 服务返回的向量维度不匹配",
                retryable=False,
            ) from exc
        except EmbeddingResponseError as exc:
            raise EmbeddingProviderError(
                FailureCode.INVALID_AI_RESPONSE,
                "Embedding 服务响应未通过结构校验",
                retryable=False,
            ) from exc

        request_id = response.headers.get("x-request-id") or response.headers.get("request-id")
        prompt_tokens, total_tokens = self._parse_usage(parsed.usage)
        logger.info(
            "Embedding 成功：model=%s response_model=%s dimensions=%s request_id=%s "
            "attempts=%s elapsed=%.2fs tokens=%s",
            self._settings.model_id,
            parsed.response_model,
            parsed.dimension,
            request_id,
            attempts,
            elapsed,
            total_tokens,
        )
        return EmbeddingProviderResult(
            vector=parsed.vectors[0],
            model_id=self._settings.model_id,
            response_model=parsed.response_model,
            dimensions=parsed.dimension,
            request_id=request_id,
            prompt_tokens=prompt_tokens,
            total_tokens=total_tokens,
            elapsed_seconds=elapsed,
            attempts=attempts,
        )

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        status_code = response.status_code
        if status_code < 400:
            return
        if status_code in {401, 403}:
            code = FailureCode.PROVIDER_AUTH_ERROR
            message = "Embedding 服务鉴权失败"
            retryable = False
        elif status_code in {400, 404, 422}:
            code = FailureCode.PROVIDER_CONFIG_ERROR
            message = "Embedding 服务地址、模型或请求参数无效"
            retryable = False
        elif status_code == 429:
            code = FailureCode.PROVIDER_RATE_LIMITED
            message = "Embedding 服务限流或余额不足"
            retryable = True
        elif status_code >= 500:
            code = FailureCode.PROVIDER_ERROR
            message = "Embedding 服务内部错误"
            retryable = True
        else:
            code = FailureCode.PROVIDER_CONFIG_ERROR
            message = "Embedding 服务拒绝请求"
            retryable = False
        request_id = response.headers.get("x-request-id") or response.headers.get("request-id")
        raise EmbeddingProviderError(
            code,
            message,
            retryable=retryable,
            http_status=status_code,
            request_id=request_id,
        )

    @staticmethod
    def _parse_usage(usage: dict[str, Any] | None) -> tuple[int | None, int | None]:
        if usage is None:
            return None, None

        def integer_or_none(value: Any) -> int | None:
            return value if isinstance(value, int) and not isinstance(value, bool) else None

        return integer_or_none(usage.get("prompt_tokens")), integer_or_none(
            usage.get("total_tokens")
        )

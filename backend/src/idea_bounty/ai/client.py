from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import httpx
from pydantic import ValidationError

from idea_bounty.ai.chat import AIProviderError, OpenAICompatibleChatClient
from idea_bounty.ai.config import AISettings
from idea_bounty.ai.prompts import build_evaluation_payload
from idea_bounty.models import FailureCode
from idea_bounty.schemas.ai import EvaluationOutput

logger = logging.getLogger(__name__)

SAFE_VALIDATION_PATH_PART = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")


def validation_error_signature(error: ValidationError) -> str:
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


EvaluationProviderError = AIProviderError


class EvaluationProvider(Protocol):
    """供投稿服务和测试替换的评估提供者接口。"""

    def evaluate(self, raw_content: str) -> EvaluationProviderResult:
        """评估一条不可信用户原文。"""


class UnavailableEvaluationProvider:
    """在 AI 配置无效时延迟返回安全错误。"""

    def evaluate(self, raw_content: str) -> EvaluationProviderResult:
        del raw_content
        raise AIProviderError(
            FailureCode.PROVIDER_CONFIG_ERROR,
            "AI 服务配置无效",
            retryable=False,
        )


class OpenAICompatibleEvaluationProvider:
    """使用共享 Chat JSON 客户端的同步评估提供者。"""

    def __init__(
        self,
        settings: AISettings,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] | None = None,
    ) -> None:
        self._settings = settings
        self._client = OpenAICompatibleChatClient(
            settings,
            operation="AI 评估",
            transport=transport,
            sleep=sleep,
            jitter=jitter,
        )

    def evaluate(self, raw_content: str) -> EvaluationProviderResult:
        payload = build_evaluation_payload(
            self._settings.model_id,
            raw_content,
            temperature=self._settings.temperature,
        )
        result = self._client.complete(payload, self._parse_output)
        return EvaluationProviderResult(
            output=result.output,
            model_id=result.model_id,
            request_id=result.request_id,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            total_tokens=result.total_tokens,
            elapsed_seconds=result.elapsed_seconds,
            attempts=result.attempts,
        )

    def _parse_output(self, content: str) -> EvaluationOutput:
        try:
            return EvaluationOutput.model_validate_json(content)
        except ValidationError as exc:
            logger.warning(
                "AI 输出未通过契约校验：model=%s errors=%s signature=%s",
                self._settings.model_id,
                exc.error_count(),
                validation_error_signature(exc),
            )
            raise AIProviderError(
                FailureCode.INVALID_AI_OUTPUT,
                "AI 输出未通过业务契约校验",
                retryable=True,
            ) from exc

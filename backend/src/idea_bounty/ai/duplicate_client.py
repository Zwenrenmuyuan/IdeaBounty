from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import httpx
from pydantic import ValidationError

from idea_bounty.ai.chat import AIProviderError, OpenAICompatibleChatClient
from idea_bounty.ai.client import validation_error_signature
from idea_bounty.ai.config import AISettings
from idea_bounty.ai.duplicate_prompts import build_duplicate_payload
from idea_bounty.models import FailureCode
from idea_bounty.schemas.duplicate import (
    DuplicateComparisonInput,
    DuplicateJudgmentOutput,
    validate_duplicate_judgment_json,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DuplicateProviderResult:
    """一次成功查重判定及其安全调用元数据。"""

    output: DuplicateJudgmentOutput
    model_id: str
    request_id: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    elapsed_seconds: float
    attempts: int


DuplicateProviderError = AIProviderError


class DuplicateProvider(Protocol):
    """供查重流水线和测试替换的判定提供者接口。"""

    def judge(self, comparison: DuplicateComparisonInput) -> DuplicateProviderResult:
        """在给定候选集合内判定点子关系。"""


class UnavailableDuplicateProvider:
    """在 AI 配置无效时延迟返回安全错误。"""

    def judge(self, comparison: DuplicateComparisonInput) -> DuplicateProviderResult:
        del comparison
        raise AIProviderError(
            FailureCode.PROVIDER_CONFIG_ERROR,
            "AI 服务配置无效",
            retryable=False,
        )


class OpenAICompatibleDuplicateProvider:
    """使用共享 Chat JSON 客户端的同步查重提供者。"""

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
            operation="AI 查重",
            transport=transport,
            sleep=sleep,
            jitter=jitter,
        )

    def judge(self, comparison: DuplicateComparisonInput) -> DuplicateProviderResult:
        payload = build_duplicate_payload(
            self._settings.model_id,
            comparison,
            temperature=self._settings.temperature,
        )

        def parse_output(content: str) -> DuplicateJudgmentOutput:
            try:
                return validate_duplicate_judgment_json(content, comparison)
            except ValidationError as exc:
                logger.warning(
                    "查重输出未通过契约校验：model=%s errors=%s signature=%s",
                    self._settings.model_id,
                    exc.error_count(),
                    validation_error_signature(exc),
                )
                raise AIProviderError(
                    FailureCode.INVALID_AI_OUTPUT,
                    "查重输出未通过业务契约校验",
                    retryable=True,
                ) from exc

        result = self._client.complete(payload, parse_output)
        return DuplicateProviderResult(
            output=result.output,
            model_id=result.model_id,
            request_id=result.request_id,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            total_tokens=result.total_tokens,
            elapsed_seconds=result.elapsed_seconds,
            attempts=result.attempts,
        )

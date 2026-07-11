from __future__ import annotations

import json
from collections.abc import Callable

from idea_bounty.ai import DuplicateProviderError, DuplicateProviderResult
from idea_bounty.schemas.duplicate import (
    DuplicateComparisonInput,
    DuplicateJudgmentOutput,
    validate_duplicate_judgment_json,
)


def make_novel_judgment(comparison: DuplicateComparisonInput) -> DuplicateJudgmentOutput:
    """创建与任意候选集合匹配的默认 novel 结论。"""

    return validate_duplicate_judgment_json(
        json.dumps(
            {
                "pain_relation": "different",
                "solution_relation": "different",
                "verdict": "novel",
                "matched_internal_id": None,
                "same_aspects": [],
                "different_aspects": ["pain_point"],
                "added_value": "当前点子的核心痛点与历史候选不同",
                "confidence": "medium",
                "reason": "当前点子的核心痛点与历史候选不同",
            },
            ensure_ascii=False,
        ),
        comparison,
    )


class FakeDuplicateProvider:
    """按队列返回结果或错误的无网络查重提供者。"""

    def __init__(
        self,
        outcomes: list[DuplicateJudgmentOutput | DuplicateProviderError] | None = None,
        *,
        on_judge: Callable[[], None] | None = None,
    ) -> None:
        self.outcomes = outcomes or []
        self.on_judge = on_judge
        self.call_count = 0
        self.comparisons: list[DuplicateComparisonInput] = []

    def judge(self, comparison: DuplicateComparisonInput) -> DuplicateProviderResult:
        self.call_count += 1
        self.comparisons.append(comparison)
        if self.on_judge is not None:
            self.on_judge()
        outcome = (
            (self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0])
            if self.outcomes
            else make_novel_judgment(comparison)
        )
        if isinstance(outcome, DuplicateProviderError):
            raise outcome
        return DuplicateProviderResult(
            output=outcome,
            model_id="fake-duplicate-model",
            request_id="fake-duplicate-request",
            prompt_tokens=100,
            completion_tokens=100,
            total_tokens=200,
            elapsed_seconds=0.01,
            attempts=1,
        )

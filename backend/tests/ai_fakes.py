from __future__ import annotations

import json
from collections.abc import Callable

from idea_bounty.ai import (
    EvaluationProviderError,
    EvaluationProviderResult,
)
from idea_bounty.schemas.ai import EvaluationOutput


def evaluation_output_data(decision: str = "accept") -> dict[str, object]:
    """生成可按测试需要修改的完整 AI 输出字典。"""

    unknown = {"value": None, "source": "unknown"}
    data: dict[str, object] = {
        "input_decision": decision,
        "decision_reason": "这是用于自动测试的中性门禁理由",
        "generated_title": "社区老人买菜协助服务" if decision == "accept" else None,
        "target_audience": {"value": "社区独居老人", "source": "explicit"},
        "pain_point": {"value": "行动不便时买菜困难", "source": "explicit"},
        "context": {"value": "日常居家生活", "source": "inferred"},
        "frequency_or_severity": unknown.copy(),
        "current_alternative": unknown.copy(),
        "desired_outcome": {"value": "更方便地获得日常食材", "source": "inferred"},
        "solution_present": False,
        "proposed_solution": unknown.copy(),
        "solution_mechanism": unknown.copy(),
        "value_proposition": unknown.copy(),
        "unsupported_claims": [],
        "manipulation_signals": [],
        "clarification_question": None,
        "evaluation": None,
    }
    if decision == "accept":
        dimension = {
            "score": 3,
            "reason": "目标用户和痛点较为明确",
            "confidence": "medium",
            "evidence_fields": ["target_audience", "pain_point"],
        }
        data["evaluation"] = {
            "demand_breadth": dimension.copy(),
            "pain_intensity": dimension.copy(),
            "willingness_to_pay": dimension.copy(),
            "feasibility": dimension.copy(),
            "novelty": dimension.copy(),
        }
    elif decision == "clarify":
        data["clarification_question"] = "主要是哪一类老人，在什么场景下买菜困难？"
    return data


def make_evaluation_output(decision: str = "accept") -> EvaluationOutput:
    """通过正式 JSON 契约创建测试输出。"""

    return EvaluationOutput.model_validate_json(
        json.dumps(evaluation_output_data(decision), ensure_ascii=False)
    )


class FakeEvaluationProvider:
    """按队列返回结果或错误的无网络评估提供者。"""

    def __init__(
        self,
        outcomes: list[EvaluationOutput | EvaluationProviderError] | None = None,
        *,
        on_evaluate: Callable[[], None] | None = None,
    ) -> None:
        self.outcomes = outcomes or [make_evaluation_output()]
        self.on_evaluate = on_evaluate
        self.call_count = 0
        self.raw_contents: list[str] = []

    def evaluate(self, raw_content: str) -> EvaluationProviderResult:
        self.call_count += 1
        self.raw_contents.append(raw_content)
        if self.on_evaluate is not None:
            self.on_evaluate()
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, EvaluationProviderError):
            raise outcome
        return EvaluationProviderResult(
            output=outcome,
            model_id="fake-evaluation-model",
            request_id="fake-request-id",
            prompt_tokens=100,
            completion_tokens=200,
            total_tokens=300,
            elapsed_seconds=0.01,
            attempts=1,
        )

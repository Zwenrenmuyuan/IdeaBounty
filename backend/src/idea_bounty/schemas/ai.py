from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator
from pydantic_core import PydanticCustomError

from idea_bounty.models import (
    EvidenceField,
    InformationSource,
    InputDecision,
    ManipulationSignal,
    ScoreConfidence,
)

SOLUTION_SCHEMA_VARIANTS: list[JsonValue] = [
    {
        "title": "用户没有明确方案",
        "properties": {
            "solution_present": {"const": False},
            "proposed_solution": {
                "properties": {
                    "source": {"const": "unknown"},
                    "value": {"type": "null"},
                }
            },
            "solution_mechanism": {
                "properties": {
                    "source": {"const": "unknown"},
                    "value": {"type": "null"},
                }
            },
            "value_proposition": {
                "properties": {
                    "source": {"const": "unknown"},
                    "value": {"type": "null"},
                }
            },
        },
    },
    {
        "title": "用户明确提出方案",
        "properties": {
            "solution_present": {"const": True},
            "proposed_solution": {
                "properties": {
                    "source": {"const": "explicit"},
                    "value": {"type": "string", "minLength": 1},
                }
            },
        },
    },
]

DECISION_SCHEMA_VARIANTS: list[JsonValue] = [
    {
        "title": "接受并评分",
        "properties": {
            "input_decision": {"const": "accept"},
            "generated_title": {"type": "string", "minLength": 1},
            "clarification_question": {"type": "null"},
            "evaluation": {"not": {"type": "null"}},
        },
    },
    {
        "title": "要求补充信息",
        "properties": {
            "input_decision": {"const": "clarify"},
            "clarification_question": {"type": "string", "minLength": 1},
            "evaluation": {"type": "null"},
        },
    },
    {
        "title": "拒绝输入",
        "properties": {
            "input_decision": {"const": "reject"},
            "clarification_question": {"type": "null"},
            "evaluation": {"type": "null"},
        },
    },
]


class StrictAIModel(BaseModel):
    """拒绝额外字段和宽松类型转换的 AI 数据边界。"""

    model_config = ConfigDict(extra="forbid", strict=True)


class NormalizedField(StrictAIModel):
    """带有原文证据强度的规范化字段。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        json_schema_extra={
            "oneOf": [
                {
                    "title": "未知字段",
                    "properties": {
                        "source": {"const": "unknown"},
                        "value": {"type": "null"},
                    },
                },
                {
                    "title": "已提取字段",
                    "properties": {
                        "source": {"enum": ["explicit", "inferred"]},
                        "value": {"type": "string", "minLength": 1},
                    },
                },
            ]
        },
    )

    value: str | None
    source: InformationSource

    @model_validator(mode="after")
    def validate_source_and_value(self) -> Self:
        if self.source is InformationSource.UNKNOWN and self.value is not None:
            raise PydanticCustomError(
                "normalized_unknown_has_value",
                "source=unknown 时 value 必须为 null",
            )
        if self.source is not InformationSource.UNKNOWN and (
            self.value is None or not self.value.strip()
        ):
            raise PydanticCustomError(
                "normalized_known_missing_value",
                "已提取字段必须包含非空 value",
            )
        return self


class DimensionScore(StrictAIModel):
    """模型输出的单个商业价值评分维度。"""

    score: int = Field(ge=0, le=5)
    reason: str = Field(min_length=1, max_length=300)
    confidence: ScoreConfidence
    evidence_fields: list[EvidenceField] = Field(min_length=1, max_length=3)


class EvaluationScores(StrictAIModel):
    """AI 五维商业价值原始评分。"""

    demand_breadth: DimensionScore
    pain_intensity: DimensionScore
    willingness_to_pay: DimensionScore
    feasibility: DimensionScore
    novelty: DimensionScore


class NormalizedContent(StrictAIModel):
    """写入 JSONB 的规范化内容和内部审计信息。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        json_schema_extra={"oneOf": SOLUTION_SCHEMA_VARIANTS},
    )

    generated_title: str | None
    target_audience: NormalizedField
    pain_point: NormalizedField
    context: NormalizedField
    frequency_or_severity: NormalizedField
    current_alternative: NormalizedField
    desired_outcome: NormalizedField
    solution_present: bool
    proposed_solution: NormalizedField
    solution_mechanism: NormalizedField
    value_proposition: NormalizedField
    unsupported_claims: list[str] = Field(max_length=10)
    manipulation_signals: list[ManipulationSignal] = Field(max_length=5)
    clarification_question: str | None

    @model_validator(mode="after")
    def validate_solution_fields(self) -> Self:
        solution_fields = (
            self.proposed_solution,
            self.solution_mechanism,
            self.value_proposition,
        )
        if not self.solution_present and any(
            field.source is not InformationSource.UNKNOWN or field.value is not None
            for field in solution_fields
        ):
            raise PydanticCustomError(
                "solution_fields_without_solution",
                "solution_present=false 时方案字段必须为 unknown/null",
            )
        if (
            self.solution_present
            and self.proposed_solution.source is not InformationSource.EXPLICIT
        ):
            raise PydanticCustomError(
                "solution_not_explicit",
                "solution_present=true 时 proposed_solution 必须来自用户明确描述",
            )
        return self


class EvaluationOutput(NormalizedContent):
    """模型一次门禁、规范化和五维评分的完整输出。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        json_schema_extra={
            "allOf": [
                {"oneOf": SOLUTION_SCHEMA_VARIANTS},
                {"oneOf": DECISION_SCHEMA_VARIANTS},
            ]
        },
    )

    input_decision: InputDecision
    decision_reason: str = Field(min_length=1, max_length=300)
    evaluation: EvaluationScores | None

    @model_validator(mode="after")
    def validate_decision_consistency(self) -> Self:
        if self.input_decision is InputDecision.ACCEPT:
            if (
                self.generated_title is None
                or not self.generated_title.strip()
                or self.pain_point.value is None
                or self.evaluation is None
            ):
                raise PydanticCustomError(
                    "accept_result_incomplete",
                    "accept 时必须包含标题、痛点和五维评分",
                )
            if self.clarification_question is not None:
                raise PydanticCustomError(
                    "accept_has_clarification",
                    "accept 时 clarification_question 必须为 null",
                )
        elif self.input_decision is InputDecision.CLARIFY:
            if (
                self.clarification_question is None
                or not self.clarification_question.strip()
                or self.evaluation is not None
            ):
                raise PydanticCustomError(
                    "clarify_result_incomplete",
                    "clarify 时必须包含补充问题且 evaluation 为 null",
                )
        elif self.evaluation is not None or self.clarification_question is not None:
            raise PydanticCustomError(
                "reject_has_evaluation",
                "reject 时 evaluation 和 clarification_question 必须为 null",
            )
        return self

    def normalized_content(self) -> NormalizedContent:
        """从完整输出提取用于持久化的规范化内容。"""

        return NormalizedContent.model_validate(
            self.model_dump(exclude={"input_decision", "decision_reason", "evaluation"})
        )

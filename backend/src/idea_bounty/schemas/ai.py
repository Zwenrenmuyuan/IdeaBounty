from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from idea_bounty.models import (
    InformationSource,
    InputDecision,
    ManipulationSignal,
    ScoreConfidence,
)

NORMALIZED_FIELD_NAMES = {
    "target_audience",
    "pain_point",
    "context",
    "frequency_or_severity",
    "current_alternative",
    "desired_outcome",
    "proposed_solution",
    "solution_mechanism",
    "value_proposition",
}


class StrictAIModel(BaseModel):
    """拒绝额外字段和宽松类型转换的 AI 数据边界。"""

    model_config = ConfigDict(extra="forbid", strict=True)


class NormalizedField(StrictAIModel):
    """带有原文证据强度的规范化字段。"""

    value: str | None
    source: InformationSource

    @model_validator(mode="after")
    def validate_source_and_value(self) -> Self:
        if self.source is InformationSource.UNKNOWN and self.value is not None:
            raise ValueError("source=unknown 时 value 必须为 null")
        if self.source is not InformationSource.UNKNOWN and (
            self.value is None or not self.value.strip()
        ):
            raise ValueError("已提取字段必须包含非空 value")
        return self


class DimensionScore(StrictAIModel):
    """模型输出的单个商业价值评分维度。"""

    score: int = Field(ge=0, le=5)
    reason: str = Field(min_length=1, max_length=300)
    confidence: ScoreConfidence
    evidence_fields: list[str] = Field(max_length=9)

    @model_validator(mode="after")
    def validate_evidence_fields(self) -> Self:
        invalid_fields = set(self.evidence_fields) - NORMALIZED_FIELD_NAMES
        if invalid_fields:
            invalid = ", ".join(sorted(invalid_fields))
            raise ValueError(f"evidence_fields 包含未知字段: {invalid}")
        return self


class EvaluationScores(StrictAIModel):
    """AI 五维商业价值原始评分。"""

    demand_breadth: DimensionScore
    pain_intensity: DimensionScore
    willingness_to_pay: DimensionScore
    feasibility: DimensionScore
    novelty: DimensionScore


class NormalizedContent(StrictAIModel):
    """写入 JSONB 的规范化内容和内部审计信息。"""

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
            raise ValueError("solution_present=false 时方案字段必须为 unknown/null")
        if self.solution_present and self.proposed_solution.source is InformationSource.UNKNOWN:
            raise ValueError("solution_present=true 时 proposed_solution 必须存在")
        return self


class EvaluationOutput(NormalizedContent):
    """模型一次门禁、规范化和五维评分的完整输出。"""

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
                raise ValueError("accept 时必须包含标题、痛点和五维评分")
            if self.clarification_question is not None:
                raise ValueError("accept 时 clarification_question 必须为 null")
        elif self.input_decision is InputDecision.CLARIFY:
            if (
                self.clarification_question is None
                or not self.clarification_question.strip()
                or self.evaluation is not None
            ):
                raise ValueError("clarify 时必须包含补充问题且 evaluation 为 null")
        elif self.evaluation is not None or self.clarification_question is not None:
            raise ValueError("reject 时 evaluation 和 clarification_question 必须为 null")
        return self

    def normalized_content(self) -> NormalizedContent:
        """从完整输出提取用于持久化的规范化内容。"""

        return NormalizedContent.model_validate(
            self.model_dump(exclude={"input_decision", "decision_reason", "evaluation"})
        )

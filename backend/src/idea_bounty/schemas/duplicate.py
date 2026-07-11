from __future__ import annotations

from typing import Self

from pydantic import ConfigDict, Field, JsonValue, ValidationInfo, field_validator, model_validator
from pydantic_core import PydanticCustomError

from idea_bounty.models import (
    ComparisonAspect,
    DuplicateVerdict,
    InformationSource,
    PainRelation,
    ScoreConfidence,
    SolutionRelation,
)
from idea_bounty.schemas.ai import NormalizedContent, NormalizedField, StrictAIModel

DUPLICATE_SCHEMA_VARIANTS: list[JsonValue] = [
    {
        "title": "高度重复",
        "properties": {
            "pain_relation": {"const": "same"},
            "solution_relation": {"enum": ["same", "not_applicable"]},
            "verdict": {"const": "duplicate"},
            "matched_internal_id": {"type": "integer"},
        },
    },
    {
        "title": "存在相关性和新增价值",
        "properties": {
            "pain_relation": {"enum": ["same", "related"]},
            "verdict": {"const": "related"},
            "matched_internal_id": {"type": "integer"},
        },
    },
    {
        "title": "全新痛点",
        "properties": {
            "pain_relation": {"const": "different"},
            "verdict": {"const": "novel"},
            "matched_internal_id": {"type": "null"},
        },
    },
]


class ComparableIdea(StrictAIModel):
    """发送给查重模型的最小规范化点子视图。"""

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
                "comparison_solution_fields_without_solution",
                "solution_present=false 时方案字段必须为 unknown/null",
            )
        if (
            self.solution_present
            and self.proposed_solution.source is not InformationSource.EXPLICIT
        ):
            raise PydanticCustomError(
                "comparison_solution_not_explicit",
                "solution_present=true 时 proposed_solution 必须来自用户明确描述",
            )
        return self

    @classmethod
    def from_normalized_content(cls, content: NormalizedContent) -> ComparableIdea:
        """从已验证的 AI 规范化结果投影安全比较字段。"""

        return cls.model_validate(
            content.model_dump(
                include={
                    "target_audience",
                    "pain_point",
                    "context",
                    "frequency_or_severity",
                    "current_alternative",
                    "desired_outcome",
                    "solution_present",
                    "proposed_solution",
                    "solution_mechanism",
                    "value_proposition",
                }
            )
        )


class DuplicateCandidateInput(StrictAIModel):
    """一条带内部标识的规范化历史候选。"""

    internal_id: int = Field(gt=0)
    content: ComparableIdea


class DuplicateComparisonInput(StrictAIModel):
    """一次查重模型调用的当前点子和候选列表。"""

    current: ComparableIdea
    candidates: list[DuplicateCandidateInput] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def validate_unique_candidate_ids(self) -> Self:
        candidate_ids = [candidate.internal_id for candidate in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise PydanticCustomError(
                "duplicate_candidate_ids",
                "候选 internal_id 不能重复",
            )
        return self


class DuplicateJudgmentOutput(StrictAIModel):
    """查重模型输出及跨字段一致性边界。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        json_schema_extra={"oneOf": DUPLICATE_SCHEMA_VARIANTS},
    )

    pain_relation: PainRelation
    solution_relation: SolutionRelation
    verdict: DuplicateVerdict
    matched_internal_id: int | None
    same_aspects: list[ComparisonAspect] = Field(max_length=9)
    different_aspects: list[ComparisonAspect] = Field(max_length=9)
    added_value: str = Field(min_length=1, max_length=300)
    confidence: ScoreConfidence
    reason: str = Field(min_length=1, max_length=400)

    @field_validator("same_aspects", "different_aspects")
    @classmethod
    def validate_unique_aspects(
        cls,
        value: list[ComparisonAspect],
    ) -> list[ComparisonAspect]:
        if len(value) != len(set(value)):
            raise PydanticCustomError(
                "duplicate_comparison_aspects",
                "比较字段不能重复",
            )
        return value

    @model_validator(mode="after")
    def validate_judgment(self, info: ValidationInfo) -> Self:
        comparison = (info.context or {}).get("comparison")
        if not isinstance(comparison, DuplicateComparisonInput):
            raise PydanticCustomError(
                "duplicate_comparison_context_missing",
                "校验查重输出时必须提供候选上下文",
            )

        if set(self.same_aspects) & set(self.different_aspects):
            raise PydanticCustomError(
                "overlapping_comparison_aspects",
                "相同点和不同点不能引用同一字段",
            )

        candidate_by_id = {candidate.internal_id: candidate for candidate in comparison.candidates}
        if self.matched_internal_id is not None and self.matched_internal_id not in candidate_by_id:
            raise PydanticCustomError(
                "unknown_matched_internal_id",
                "matched_internal_id 必须来自本次候选列表",
            )

        if self.verdict is DuplicateVerdict.DUPLICATE:
            if (
                self.matched_internal_id is None
                or self.pain_relation is not PainRelation.SAME
                or self.solution_relation
                not in {SolutionRelation.SAME, SolutionRelation.NOT_APPLICABLE}
            ):
                raise PydanticCustomError(
                    "invalid_duplicate_verdict",
                    "duplicate 必须匹配相同痛点和相同或不适用的方案",
                )
        elif self.verdict is DuplicateVerdict.RELATED:
            if self.matched_internal_id is None or self.pain_relation not in {
                PainRelation.SAME,
                PainRelation.RELATED,
            }:
                raise PydanticCustomError(
                    "invalid_related_verdict",
                    "related 必须匹配一条相同或相关痛点候选",
                )
            if self.pain_relation is PainRelation.SAME and self.solution_relation in {
                SolutionRelation.SAME,
                SolutionRelation.NOT_APPLICABLE,
            }:
                raise PydanticCustomError(
                    "related_without_added_value",
                    "相同痛点和相同方案不能判为 related",
                )
        elif (
            self.matched_internal_id is not None or self.pain_relation is not PainRelation.DIFFERENT
        ):
            raise PydanticCustomError(
                "invalid_novel_verdict",
                "novel 必须是不同痛点且不能返回匹配 ID",
            )

        if self.solution_relation is SolutionRelation.NOT_APPLICABLE:
            matched_candidate = (
                candidate_by_id.get(self.matched_internal_id)
                if self.matched_internal_id is not None
                else None
            )
            candidate_has_solution = (
                matched_candidate.content.solution_present
                if matched_candidate is not None
                else any(candidate.content.solution_present for candidate in comparison.candidates)
            )
            if comparison.current.solution_present or candidate_has_solution:
                raise PydanticCustomError(
                    "solution_relation_not_applicable_invalid",
                    "not_applicable 只允许双方都没有明确方案",
                )
        matched_candidate = (
            candidate_by_id.get(self.matched_internal_id)
            if self.matched_internal_id is not None
            else None
        )
        if (
            matched_candidate is not None
            and comparison.current.solution_present != matched_candidate.content.solution_present
            and self.solution_relation is not SolutionRelation.DIFFERENT
        ):
            raise PydanticCustomError(
                "missing_solution_relation_invalid",
                "只有一方存在明确方案时 solution_relation 必须为 different",
            )
        return self


class DuplicateComparisonSnapshot(StrictAIModel):
    """允许持久化并向用户投影的查重比较快照。"""

    pain_relation: PainRelation
    solution_relation: SolutionRelation
    same_aspects: list[ComparisonAspect] = Field(max_length=9)
    different_aspects: list[ComparisonAspect] = Field(max_length=9)
    added_value: str = Field(min_length=1, max_length=300)

    @field_validator("same_aspects", "different_aspects")
    @classmethod
    def validate_unique_aspects(
        cls,
        value: list[ComparisonAspect],
    ) -> list[ComparisonAspect]:
        if len(value) != len(set(value)):
            raise PydanticCustomError(
                "duplicate_comparison_aspects",
                "比较字段不能重复",
            )
        return value

    @model_validator(mode="after")
    def validate_disjoint_aspects(self) -> Self:
        if set(self.same_aspects) & set(self.different_aspects):
            raise PydanticCustomError(
                "overlapping_comparison_aspects",
                "相同点和不同点不能引用同一字段",
            )
        return self

    @classmethod
    def from_judgment(cls, output: DuplicateJudgmentOutput) -> DuplicateComparisonSnapshot:
        """从完整模型结论提取不含内部候选 ID 的持久化快照。"""

        return cls(
            pain_relation=output.pain_relation,
            solution_relation=output.solution_relation,
            same_aspects=output.same_aspects,
            different_aspects=output.different_aspects,
            added_value=output.added_value,
        )


def validate_duplicate_judgment_json(
    content: str,
    comparison: DuplicateComparisonInput,
) -> DuplicateJudgmentOutput:
    """结合动态候选集合严格校验一段模型 JSON 输出。"""

    return DuplicateJudgmentOutput.model_validate_json(
        content,
        context={"comparison": comparison},
    )

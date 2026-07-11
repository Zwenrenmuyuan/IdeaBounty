from __future__ import annotations

import copy
import json

import pytest
from pydantic import ValidationError

from idea_bounty.models import ComparisonAspect, DuplicateVerdict
from idea_bounty.schemas.duplicate import (
    ComparableIdea,
    DuplicateJudgmentOutput,
    validate_duplicate_judgment_json,
)
from scripts.probe_duplicate_provider import PROBE_CASES
from tests.ai_fakes import make_evaluation_output


def judgment_data(case_index: int) -> dict[str, object]:
    case = PROBE_CASES[case_index]
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
        "added_value": "存在明确的比较结论",
        "confidence": "high",
        "reason": "根据核心痛点、场景和方案关系得出结论",
    }


@pytest.mark.parametrize("case_index", [0, 3, 6])
def test_duplicate_judgment_accepts_valid_verdicts(case_index: int) -> None:
    case = PROBE_CASES[case_index]

    output = validate_duplicate_judgment_json(
        json.dumps(judgment_data(case_index), ensure_ascii=False),
        case.comparison,
    )

    assert output.verdict is case.expected_verdict
    assert output.matched_internal_id == case.expected_matched_internal_id


def invalid_contracts() -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []

    extra = judgment_data(0)
    extra["unexpected"] = True
    cases.append(extra)

    missing = judgment_data(0)
    missing.pop("reason")
    cases.append(missing)

    wrong_enum = judgment_data(0)
    wrong_enum["verdict"] = "almost_duplicate"
    cases.append(wrong_enum)

    loose_type = judgment_data(0)
    loose_type["matched_internal_id"] = "101"
    cases.append(loose_type)

    duplicate_aspect = judgment_data(0)
    duplicate_aspect["same_aspects"] = ["pain_point", "pain_point"]
    cases.append(duplicate_aspect)

    forbidden_aspect = judgment_data(0)
    forbidden_aspect["same_aspects"] = ["raw_content"]
    cases.append(forbidden_aspect)

    return cases


@pytest.mark.parametrize("invalid_output", invalid_contracts())
def test_duplicate_judgment_rejects_invalid_contracts(
    invalid_output: dict[str, object],
) -> None:
    case = PROBE_CASES[0]

    with pytest.raises(ValidationError):
        validate_duplicate_judgment_json(
            json.dumps(invalid_output, ensure_ascii=False),
            case.comparison,
        )


def test_duplicate_judgment_rejects_unknown_candidate_id() -> None:
    case = PROBE_CASES[0]
    data = judgment_data(0)
    data["matched_internal_id"] = 999999

    with pytest.raises(ValidationError, match="本次候选列表"):
        validate_duplicate_judgment_json(
            json.dumps(data, ensure_ascii=False),
            case.comparison,
        )


@pytest.mark.parametrize(
    ("case_index", "changes"),
    [
        (0, {"pain_relation": "related"}),
        (3, {"pain_relation": "different"}),
        (6, {"matched_internal_id": 701}),
        (6, {"pain_relation": "same"}),
    ],
)
def test_duplicate_judgment_rejects_verdict_relation_conflicts(
    case_index: int,
    changes: dict[str, object],
) -> None:
    case = PROBE_CASES[case_index]
    data = judgment_data(case_index)
    data.update(changes)

    with pytest.raises(ValidationError):
        validate_duplicate_judgment_json(
            json.dumps(data, ensure_ascii=False),
            case.comparison,
        )


def test_duplicate_judgment_rejects_overlapping_aspects() -> None:
    case = PROBE_CASES[0]
    data = judgment_data(0)
    data["different_aspects"] = copy.deepcopy(data["same_aspects"])

    with pytest.raises(ValidationError, match="不能引用同一字段"):
        validate_duplicate_judgment_json(
            json.dumps(data, ensure_ascii=False),
            case.comparison,
        )


def test_duplicate_judgment_requires_different_when_only_one_side_has_solution() -> None:
    case = PROBE_CASES[4]
    data = judgment_data(4)
    data["solution_relation"] = "related"

    with pytest.raises(ValidationError, match="必须为 different"):
        validate_duplicate_judgment_json(
            json.dumps(data, ensure_ascii=False),
            case.comparison,
        )


def test_duplicate_judgment_requires_comparison_context() -> None:
    with pytest.raises(ValidationError, match="候选上下文"):
        DuplicateJudgmentOutput.model_validate_json(
            json.dumps(judgment_data(0), ensure_ascii=False)
        )


def test_comparable_idea_excludes_non_comparison_fields() -> None:
    normalized = make_evaluation_output().normalized_content()

    comparable = ComparableIdea.from_normalized_content(normalized)
    stored = comparable.model_dump(mode="json")

    assert set(stored) == {
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
    assert "unsupported_claims" not in stored
    assert "manipulation_signals" not in stored
    assert "generated_title" not in stored


def test_duplicate_schema_exposes_verdict_and_aspect_constraints() -> None:
    schema = DuplicateJudgmentOutput.model_json_schema()

    assert len(schema["oneOf"]) == 3
    assert set(schema["$defs"]["ComparisonAspect"]["enum"]) == {
        aspect.value for aspect in ComparisonAspect
    }
    verdicts = {variant["properties"]["verdict"]["const"] for variant in schema["oneOf"]}
    assert verdicts == {"duplicate", "related", "novel"}

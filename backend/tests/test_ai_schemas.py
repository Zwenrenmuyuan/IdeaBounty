from __future__ import annotations

import copy
import json

import pytest
from pydantic import ValidationError

from idea_bounty.models import InputDecision
from idea_bounty.schemas.ai import EvaluationOutput
from tests.ai_fakes import evaluation_output_data


@pytest.mark.parametrize("decision", ["accept", "clarify", "reject"])
def test_evaluation_output_accepts_valid_decisions(decision: str) -> None:
    output = EvaluationOutput.model_validate_json(
        json.dumps(evaluation_output_data(decision), ensure_ascii=False)
    )

    assert output.input_decision is InputDecision(decision)


def invalid_output_cases() -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []

    extra_field = evaluation_output_data()
    extra_field["unexpected"] = True
    cases.append(extra_field)

    missing_field = evaluation_output_data()
    missing_field.pop("pain_point")
    cases.append(missing_field)

    score_out_of_range = evaluation_output_data()
    score_out_of_range["evaluation"]["novelty"]["score"] = 6  # type: ignore[index]
    cases.append(score_out_of_range)

    score_wrong_type = evaluation_output_data()
    score_wrong_type["evaluation"]["novelty"]["score"] = "3"  # type: ignore[index]
    cases.append(score_wrong_type)

    unknown_evidence = evaluation_output_data()
    unknown_evidence["evaluation"]["novelty"]["evidence_fields"] = [  # type: ignore[index]
        "raw_content"
    ]
    cases.append(unknown_evidence)

    unknown_with_value = evaluation_output_data()
    unknown_with_value["current_alternative"] = {"value": "猜测值", "source": "unknown"}
    cases.append(unknown_with_value)

    invented_solution = evaluation_output_data()
    invented_solution["proposed_solution"] = {"value": "模型编造的方案", "source": "inferred"}
    cases.append(invented_solution)

    accept_without_scores = evaluation_output_data()
    accept_without_scores["evaluation"] = None
    cases.append(accept_without_scores)

    clarify_without_question = evaluation_output_data("clarify")
    clarify_without_question["clarification_question"] = None
    cases.append(clarify_without_question)

    reject_with_scores = evaluation_output_data("reject")
    reject_with_scores["evaluation"] = copy.deepcopy(evaluation_output_data()["evaluation"])
    cases.append(reject_with_scores)
    return cases


@pytest.mark.parametrize("invalid_output", invalid_output_cases())
def test_evaluation_output_rejects_invalid_contracts(
    invalid_output: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        EvaluationOutput.model_validate_json(json.dumps(invalid_output, ensure_ascii=False))


def test_normalized_content_excludes_decision_and_scores() -> None:
    output = EvaluationOutput.model_validate_json(
        json.dumps(evaluation_output_data(), ensure_ascii=False)
    )

    stored_content = output.normalized_content().model_dump(mode="json")

    assert "input_decision" not in stored_content
    assert "decision_reason" not in stored_content
    assert "evaluation" not in stored_content
    assert "manipulation_signals" in stored_content

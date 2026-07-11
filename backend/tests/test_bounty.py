import json
from decimal import Decimal

import pytest

from idea_bounty.models import DuplicateVerdict
from idea_bounty.schemas.ai import EvaluationScores
from idea_bounty.services.bounty import calculate_bounty
from tests.ai_fakes import evaluation_output_data


def _scores(values: tuple[int, int, int, int, int]) -> EvaluationScores:
    data = evaluation_output_data()["evaluation"]
    assert isinstance(data, dict)
    for field, score in zip(
        (
            "demand_breadth",
            "pain_intensity",
            "willingness_to_pay",
            "feasibility",
            "novelty",
        ),
        values,
        strict=True,
    ):
        dimension = data[field]
        assert isinstance(dimension, dict)
        dimension["score"] = score
    return EvaluationScores.model_validate_json(json.dumps(data, ensure_ascii=False))


@pytest.mark.parametrize(
    ("values", "expected_score", "expected_amount"),
    [
        ((0, 0, 0, 0, 0), 0, Decimal("0.00")),
        ((0, 3, 3, 0, 0), 30, Decimal("0.00")),
        ((5, 4, 0, 0, 0), 40, Decimal("2.04")),
        ((3, 3, 3, 3, 3), 60, Decimal("18.37")),
        ((5, 5, 5, 5, 5), 100, Decimal("100.00")),
    ],
)
def test_bounty_curve_boundaries(
    values: tuple[int, int, int, int, int],
    expected_score: int,
    expected_amount: Decimal,
) -> None:
    result = calculate_bounty(_scores(values), DuplicateVerdict.NOVEL)

    assert result.commercial_score == expected_score
    assert result.base_amount == expected_amount
    assert result.duplicate_deduction == Decimal("0.00")
    assert result.final_amount == expected_amount


def test_related_idea_keeps_base_amount() -> None:
    result = calculate_bounty(_scores((3, 3, 3, 3, 3)), DuplicateVerdict.RELATED)

    assert result.base_amount == Decimal("18.37")
    assert result.duplicate_deduction == Decimal("0.00")
    assert result.final_amount == Decimal("18.37")


def test_duplicate_idea_is_fully_deducted() -> None:
    result = calculate_bounty(_scores((5, 5, 5, 5, 5)), DuplicateVerdict.DUPLICATE)

    assert result.base_amount == Decimal("100.00")
    assert result.duplicate_deduction == Decimal("100.00")
    assert result.final_amount == Decimal("0.00")

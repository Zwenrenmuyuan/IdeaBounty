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
        ((4, 1, 0, 0, 3), 30, Decimal("0.00")),
        ((4, 3, 0, 0, 3), 40, Decimal("2.04")),
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


@pytest.mark.parametrize(
    ("values", "expected_score", "expected_amount"),
    [
        ((5, 5, 5, 5, 0), 85, Decimal("0.00")),
        ((4, 3, 2, 4, 1), 56, Decimal("2.00")),
        ((5, 5, 5, 5, 2), 91, Decimal("8.00")),
        ((5, 5, 5, 5, 3), 94, Decimal("83.59")),
    ],
)
def test_novelty_caps_amount_without_changing_commercial_score(
    values: tuple[int, int, int, int, int],
    expected_score: int,
    expected_amount: Decimal,
) -> None:
    result = calculate_bounty(_scores(values), DuplicateVerdict.NOVEL)

    assert result.commercial_score == expected_score
    assert result.base_amount == expected_amount
    assert result.final_amount == expected_amount


def test_duplicate_idea_is_fully_deducted() -> None:
    result = calculate_bounty(_scores((5, 5, 5, 5, 5)), DuplicateVerdict.DUPLICATE)

    assert result.base_amount == Decimal("100.00")
    assert result.duplicate_deduction == Decimal("100.00")
    assert result.final_amount == Decimal("0.00")


def test_duplicate_deduction_uses_novelty_capped_base_amount() -> None:
    result = calculate_bounty(_scores((4, 3, 2, 4, 1)), DuplicateVerdict.DUPLICATE)

    assert result.commercial_score == 56
    assert result.base_amount == Decimal("2.00")
    assert result.duplicate_deduction == Decimal("2.00")
    assert result.final_amount == Decimal("0.00")

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from idea_bounty.models import DuplicateVerdict
from idea_bounty.schemas.ai import EvaluationScores

MONEY_STEP = Decimal("0.01")
ZERO_AMOUNT = Decimal("0.00")
MAX_AMOUNT = Decimal("100.00")


@dataclass(frozen=True, slots=True)
class BountyCalculation:
    """一次可复现的红包估值结果。"""

    commercial_score: int
    base_amount: Decimal
    duplicate_deduction: Decimal
    final_amount: Decimal


def calculate_bounty(
    scores: EvaluationScores,
    duplicate_verdict: DuplicateVerdict,
) -> BountyCalculation:
    """根据五维评分和有效查重结论计算红包估值。"""

    commercial_score = (
        scores.demand_breadth.score * 4
        + scores.pain_intensity.score * 5
        + scores.willingness_to_pay.score * 5
        + scores.feasibility.score * 3
        + scores.novelty.score * 3
    )
    base_amount = _calculate_base_amount(commercial_score)
    final_amount = ZERO_AMOUNT if duplicate_verdict is DuplicateVerdict.DUPLICATE else base_amount
    return BountyCalculation(
        commercial_score=commercial_score,
        base_amount=base_amount,
        duplicate_deduction=base_amount - final_amount,
        final_amount=final_amount,
    )


def _calculate_base_amount(commercial_score: int) -> Decimal:
    if commercial_score <= 30:
        return ZERO_AMOUNT
    normalized_score = (Decimal(commercial_score) - Decimal(30)) / Decimal(70)
    amount = MAX_AMOUNT * normalized_score**2
    return min(MAX_AMOUNT, amount.quantize(MONEY_STEP, rounding=ROUND_HALF_UP))

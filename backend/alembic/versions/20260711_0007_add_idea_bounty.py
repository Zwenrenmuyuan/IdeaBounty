"""增加红包估值快照。

Revision ID: 20260711_0007
Revises: 20260711_0006
Create Date: 2026-07-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260711_0007"
down_revision: str | None = "20260711_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """增加金额字段，并为已有完成投稿补算结果。"""

    op.add_column("ideas", sa.Column("commercial_score", sa.SmallInteger(), nullable=True))
    op.add_column("ideas", sa.Column("base_amount", sa.Numeric(6, 2), nullable=True))
    op.add_column("ideas", sa.Column("duplicate_deduction", sa.Numeric(6, 2), nullable=True))
    op.add_column("ideas", sa.Column("final_amount", sa.Numeric(6, 2), nullable=True))

    op.execute(
        """
        UPDATE ideas
        SET commercial_score =
            ((dimension_scores -> 'demand_breadth' ->> 'score')::integer * 4)
          + ((dimension_scores -> 'pain_intensity' ->> 'score')::integer * 5)
          + ((dimension_scores -> 'willingness_to_pay' ->> 'score')::integer * 5)
          + ((dimension_scores -> 'feasibility' ->> 'score')::integer * 3)
          + ((dimension_scores -> 'novelty' ->> 'score')::integer * 3)
        WHERE processing_status = 'completed' AND input_decision = 'accept'
        """
    )
    op.execute(
        """
        UPDATE ideas
        SET base_amount = CASE
                WHEN commercial_score <= 30 THEN 0.00
                ELSE ROUND(
                    100 * POWER((commercial_score - 30)::numeric / 70, 2),
                    2
                )
            END
        WHERE commercial_score IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE ideas
        SET final_amount = CASE
                WHEN effective_duplicate_verdict = 'duplicate' THEN 0.00
                ELSE base_amount
            END,
            duplicate_deduction = CASE
                WHEN effective_duplicate_verdict = 'duplicate' THEN base_amount
                ELSE 0.00
            END
        WHERE commercial_score IS NOT NULL
        """
    )

    op.create_check_constraint(
        op.f("ck_ideas_bounty_fields_together"),
        "ideas",
        "((commercial_score IS NULL AND base_amount IS NULL "
        "AND duplicate_deduction IS NULL AND final_amount IS NULL) OR "
        "(commercial_score IS NOT NULL AND base_amount IS NOT NULL "
        "AND duplicate_deduction IS NOT NULL AND final_amount IS NOT NULL))",
    )
    op.create_check_constraint(
        op.f("ck_ideas_bounty_values_valid"),
        "ideas",
        "commercial_score IS NULL OR "
        "(commercial_score BETWEEN 0 AND 100 "
        "AND base_amount BETWEEN 0 AND 100 "
        "AND duplicate_deduction BETWEEN 0 AND base_amount "
        "AND final_amount BETWEEN 0 AND 100 "
        "AND base_amount = duplicate_deduction + final_amount)",
    )
    op.create_check_constraint(
        op.f("ck_ideas_bounty_matches_completed_accept"),
        "ideas",
        "(commercial_score IS NOT NULL) = "
        "(processing_status = 'completed' AND input_decision = 'accept')",
    )


def downgrade() -> None:
    """删除红包估值字段。"""

    for name in (
        "bounty_matches_completed_accept",
        "bounty_values_valid",
        "bounty_fields_together",
    ):
        op.drop_constraint(op.f(f"ck_ideas_{name}"), "ideas", type_="check")
    for column in (
        "final_amount",
        "duplicate_deduction",
        "base_amount",
        "commercial_score",
    ):
        op.drop_column("ideas", column)

"""增加点子查重结果快照和历史匹配关系。

Revision ID: 20260711_0006
Revises: 20260711_0005
Create Date: 2026-07-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260711_0006"
down_revision: str | None = "20260711_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """增加完整查重快照、自外键和数据库不变量。"""

    op.add_column("ideas", sa.Column("duplicate_method", sa.String(length=32), nullable=True))
    op.add_column("ideas", sa.Column("ai_duplicate_verdict", sa.String(length=16), nullable=True))
    op.add_column(
        "ideas",
        sa.Column("effective_duplicate_verdict", sa.String(length=16), nullable=True),
    )
    op.add_column("ideas", sa.Column("duplicate_confidence", sa.String(length=16), nullable=True))
    op.add_column("ideas", sa.Column("matched_idea_id", sa.BigInteger(), nullable=True))
    op.add_column("ideas", sa.Column("duplicate_reason", sa.Text(), nullable=True))
    op.add_column(
        "ideas",
        sa.Column(
            "duplicate_comparison",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column("ideas", sa.Column("duplicate_model", sa.String(length=128), nullable=True))
    op.add_column(
        "ideas", sa.Column("duplicate_prompt_version", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "ideas", sa.Column("duplicate_schema_version", sa.String(length=32), nullable=True)
    )

    op.create_foreign_key(
        op.f("fk_ideas_matched_idea_id_ideas"),
        "ideas",
        "ideas",
        ["matched_idea_id"],
        ["internal_id"],
        ondelete="RESTRICT",
    )
    op.create_index(op.f("ix_ideas_matched_idea_id"), "ideas", ["matched_idea_id"])
    op.create_check_constraint(
        op.f("ck_ideas_duplicate_method_allowed"),
        "ideas",
        "duplicate_method IS NULL OR duplicate_method IN "
        "('exact_hash', 'no_candidates', 'llm_candidates')",
    )
    op.create_check_constraint(
        op.f("ck_ideas_ai_duplicate_verdict_allowed"),
        "ideas",
        "ai_duplicate_verdict IS NULL OR ai_duplicate_verdict IN ('duplicate', 'related', 'novel')",
    )
    op.create_check_constraint(
        op.f("ck_ideas_effective_duplicate_verdict_allowed"),
        "ideas",
        "effective_duplicate_verdict IS NULL OR effective_duplicate_verdict IN "
        "('duplicate', 'related', 'novel')",
    )
    op.create_check_constraint(
        op.f("ck_ideas_duplicate_confidence_allowed"),
        "ideas",
        "duplicate_confidence IS NULL OR duplicate_confidence IN ('high', 'medium', 'low')",
    )
    op.create_check_constraint(
        op.f("ck_ideas_duplicate_result_complete"),
        "ideas",
        "((duplicate_method IS NULL AND ai_duplicate_verdict IS NULL "
        "AND effective_duplicate_verdict IS NULL AND duplicate_confidence IS NULL "
        "AND matched_idea_id IS NULL AND duplicate_reason IS NULL "
        "AND duplicate_comparison IS NULL AND duplicate_model IS NULL "
        "AND duplicate_prompt_version IS NULL AND duplicate_schema_version IS NULL) OR "
        "(duplicate_method IS NOT NULL AND ai_duplicate_verdict IS NOT NULL "
        "AND effective_duplicate_verdict IS NOT NULL AND duplicate_confidence IS NOT NULL "
        "AND duplicate_reason IS NOT NULL))",
    )
    op.create_check_constraint(
        op.f("ck_ideas_duplicate_result_matches_completed_accept"),
        "ideas",
        "(duplicate_method IS NOT NULL) = "
        "(processing_status = 'completed' AND input_decision = 'accept')",
    )
    op.create_check_constraint(
        op.f("ck_ideas_duplicate_match_required"),
        "ideas",
        "((effective_duplicate_verdict IN ('duplicate', 'related') "
        "AND matched_idea_id IS NOT NULL) OR "
        "(effective_duplicate_verdict = 'novel' AND matched_idea_id IS NULL) OR "
        "effective_duplicate_verdict IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_ideas_matched_idea_is_older"),
        "ideas",
        "matched_idea_id IS NULL OR matched_idea_id < internal_id",
    )
    op.create_check_constraint(
        op.f("ck_ideas_effective_duplicate_verdict_policy"),
        "ideas",
        "effective_duplicate_verdict IS NULL "
        "OR effective_duplicate_verdict = ai_duplicate_verdict "
        "OR (ai_duplicate_verdict = 'duplicate' "
        "AND duplicate_confidence IN ('medium', 'low') "
        "AND effective_duplicate_verdict = 'related')",
    )
    op.create_check_constraint(
        op.f("ck_ideas_exact_hash_result_shape"),
        "ideas",
        "duplicate_method <> 'exact_hash' OR "
        "(ai_duplicate_verdict = 'duplicate' "
        "AND effective_duplicate_verdict = 'duplicate' "
        "AND duplicate_confidence = 'high' AND matched_idea_id IS NOT NULL "
        "AND duplicate_comparison IS NULL AND duplicate_model IS NULL "
        "AND duplicate_prompt_version IS NULL AND duplicate_schema_version IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_ideas_no_candidates_result_shape"),
        "ideas",
        "duplicate_method <> 'no_candidates' OR "
        "(ai_duplicate_verdict = 'novel' AND effective_duplicate_verdict = 'novel' "
        "AND duplicate_confidence = 'high' AND matched_idea_id IS NULL "
        "AND duplicate_comparison IS NULL AND duplicate_model IS NULL "
        "AND duplicate_prompt_version IS NULL AND duplicate_schema_version IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_ideas_llm_duplicate_result_shape"),
        "ideas",
        "duplicate_method <> 'llm_candidates' OR "
        "(duplicate_comparison IS NOT NULL AND duplicate_model IS NOT NULL "
        "AND duplicate_prompt_version IS NOT NULL AND duplicate_schema_version IS NOT NULL)",
    )


def downgrade() -> None:
    """删除查重结果字段和匹配关系。"""

    for name in (
        "llm_duplicate_result_shape",
        "no_candidates_result_shape",
        "exact_hash_result_shape",
        "effective_duplicate_verdict_policy",
        "matched_idea_is_older",
        "duplicate_match_required",
        "duplicate_result_matches_completed_accept",
        "duplicate_result_complete",
        "duplicate_confidence_allowed",
        "effective_duplicate_verdict_allowed",
        "ai_duplicate_verdict_allowed",
        "duplicate_method_allowed",
    ):
        op.drop_constraint(op.f(f"ck_ideas_{name}"), "ideas", type_="check")
    op.drop_index(op.f("ix_ideas_matched_idea_id"), table_name="ideas")
    op.drop_constraint(op.f("fk_ideas_matched_idea_id_ideas"), "ideas", type_="foreignkey")
    for column in (
        "duplicate_schema_version",
        "duplicate_prompt_version",
        "duplicate_model",
        "duplicate_comparison",
        "duplicate_reason",
        "matched_idea_id",
        "duplicate_confidence",
        "effective_duplicate_verdict",
        "ai_duplicate_verdict",
        "duplicate_method",
    ):
        op.drop_column("ideas", column)

"""增加 AI 输入门禁与结构化评估字段。

Revision ID: 20260711_0004
Revises: 20260711_0003
Create Date: 2026-07-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260711_0004"
down_revision: str | None = "20260711_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """增加评估结果、版本和安全失败状态。"""

    op.add_column("ideas", sa.Column("input_decision", sa.String(length=16), nullable=True))
    op.add_column("ideas", sa.Column("decision_reason", sa.Text(), nullable=True))
    op.add_column(
        "ideas",
        sa.Column(
            "normalized_content",
            postgresql.JSONB(astext_type=sa.Text(), none_as_null=True),
            nullable=True,
        ),
    )
    op.add_column(
        "ideas",
        sa.Column(
            "dimension_scores",
            postgresql.JSONB(astext_type=sa.Text(), none_as_null=True),
            nullable=True,
        ),
    )
    op.add_column("ideas", sa.Column("evaluation_model", sa.String(length=128), nullable=True))
    op.add_column(
        "ideas",
        sa.Column("evaluation_prompt_version", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "ideas",
        sa.Column("evaluation_schema_version", sa.String(length=32), nullable=True),
    )
    op.add_column("ideas", sa.Column("failure_stage", sa.String(length=32), nullable=True))
    op.add_column("ideas", sa.Column("failure_code", sa.String(length=64), nullable=True))
    op.add_column("ideas", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))

    op.create_check_constraint(
        op.f("ck_ideas_input_decision_allowed"),
        "ideas",
        "input_decision IS NULL OR input_decision IN ('accept', 'clarify', 'reject')",
    )
    op.create_check_constraint(
        op.f("ck_ideas_failure_stage_allowed"),
        "ideas",
        "failure_stage IS NULL OR failure_stage IN "
        "('evaluating', 'embedding', 'checking_duplicate')",
    )
    op.create_check_constraint(
        op.f("ck_ideas_failure_code_allowed"),
        "ideas",
        "failure_code IS NULL OR failure_code IN "
        "('provider_config_error', 'provider_auth_error', 'json_mode_unsupported', "
        "'provider_timeout', 'provider_rate_limited', 'invalid_ai_response', "
        "'invalid_ai_output', 'provider_error')",
    )
    op.create_check_constraint(
        op.f("ck_ideas_failure_fields_together"),
        "ideas",
        "(failure_stage IS NULL) = (failure_code IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_ideas_failure_matches_status"),
        "ideas",
        "(processing_status = 'failed') = (failure_stage IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f("ck_ideas_evaluation_result_complete"),
        "ideas",
        "((input_decision IS NULL AND decision_reason IS NULL "
        "AND normalized_content IS NULL AND dimension_scores IS NULL "
        "AND evaluation_model IS NULL AND evaluation_prompt_version IS NULL "
        "AND evaluation_schema_version IS NULL) OR "
        "(input_decision IS NOT NULL AND decision_reason IS NOT NULL "
        "AND normalized_content IS NOT NULL AND evaluation_model IS NOT NULL "
        "AND evaluation_prompt_version IS NOT NULL AND evaluation_schema_version IS NOT NULL "
        "AND ((input_decision = 'accept' AND dimension_scores IS NOT NULL) "
        "OR (input_decision IN ('clarify', 'reject') AND dimension_scores IS NULL))))",
    )
    op.create_check_constraint(
        op.f("ck_ideas_completed_at_matches_status"),
        "ideas",
        "(processing_status = 'completed') = (completed_at IS NOT NULL)",
    )


def downgrade() -> None:
    """删除 AI 输入门禁与结构化评估字段。"""

    op.drop_constraint(op.f("ck_ideas_completed_at_matches_status"), "ideas", type_="check")
    op.drop_constraint(op.f("ck_ideas_evaluation_result_complete"), "ideas", type_="check")
    op.drop_constraint(op.f("ck_ideas_failure_matches_status"), "ideas", type_="check")
    op.drop_constraint(op.f("ck_ideas_failure_fields_together"), "ideas", type_="check")
    op.drop_constraint(op.f("ck_ideas_failure_code_allowed"), "ideas", type_="check")
    op.drop_constraint(op.f("ck_ideas_failure_stage_allowed"), "ideas", type_="check")
    op.drop_constraint(op.f("ck_ideas_input_decision_allowed"), "ideas", type_="check")
    op.drop_column("ideas", "completed_at")
    op.drop_column("ideas", "failure_code")
    op.drop_column("ideas", "failure_stage")
    op.drop_column("ideas", "evaluation_schema_version")
    op.drop_column("ideas", "evaluation_prompt_version")
    op.drop_column("ideas", "evaluation_model")
    op.drop_column("ideas", "dimension_scores")
    op.drop_column("ideas", "normalized_content")
    op.drop_column("ideas", "decision_reason")
    op.drop_column("ideas", "input_decision")

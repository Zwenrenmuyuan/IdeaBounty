"""增加点子 Embedding 向量和兼容性元数据。

Revision ID: 20260711_0005
Revises: 20260711_0004
Create Date: 2026-07-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import VECTOR

from alembic import op

revision: str = "20260711_0005"
down_revision: str | None = "20260711_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """启用 pgvector 并增加固定 1024 维向量字段。"""

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("ideas", sa.Column("embedding", VECTOR(1024), nullable=True))
    op.add_column("ideas", sa.Column("embedding_model", sa.String(length=128), nullable=True))
    op.add_column("ideas", sa.Column("embedding_dimensions", sa.Integer(), nullable=True))
    op.add_column(
        "ideas",
        sa.Column("embedding_input_version", sa.String(length=32), nullable=True),
    )

    op.drop_constraint(op.f("ck_ideas_failure_code_allowed"), "ideas", type_="check")
    op.create_check_constraint(
        op.f("ck_ideas_failure_code_allowed"),
        "ideas",
        "failure_code IS NULL OR failure_code IN "
        "('provider_config_error', 'provider_auth_error', 'json_mode_unsupported', "
        "'provider_timeout', 'provider_rate_limited', 'invalid_ai_response', "
        "'invalid_ai_output', 'embedding_dimension_mismatch', 'provider_error')",
    )
    op.create_check_constraint(
        op.f("ck_ideas_embedding_fields_together"),
        "ideas",
        "((embedding IS NULL AND embedding_model IS NULL "
        "AND embedding_dimensions IS NULL AND embedding_input_version IS NULL) OR "
        "(embedding IS NOT NULL AND embedding_model IS NOT NULL "
        "AND embedding_dimensions IS NOT NULL AND embedding_input_version IS NOT NULL))",
    )
    op.create_check_constraint(
        op.f("ck_ideas_embedding_dimensions_fixed"),
        "ideas",
        "embedding_dimensions IS NULL OR embedding_dimensions = 1024",
    )
    op.create_check_constraint(
        op.f("ck_ideas_embedding_requires_accept"),
        "ideas",
        "embedding IS NULL OR input_decision IS NOT DISTINCT FROM 'accept'",
    )
    op.create_check_constraint(
        op.f("ck_ideas_checking_duplicate_requires_embedding"),
        "ideas",
        "processing_status <> 'checking_duplicate' OR embedding IS NOT NULL",
    )


def downgrade() -> None:
    """删除应用向量字段，但保留可能被复用的数据库扩展。"""

    op.drop_constraint(
        op.f("ck_ideas_checking_duplicate_requires_embedding"),
        "ideas",
        type_="check",
    )
    op.drop_constraint(op.f("ck_ideas_embedding_requires_accept"), "ideas", type_="check")
    op.drop_constraint(op.f("ck_ideas_embedding_dimensions_fixed"), "ideas", type_="check")
    op.drop_constraint(op.f("ck_ideas_embedding_fields_together"), "ideas", type_="check")
    op.drop_constraint(op.f("ck_ideas_failure_code_allowed"), "ideas", type_="check")
    op.create_check_constraint(
        op.f("ck_ideas_failure_code_allowed"),
        "ideas",
        "failure_code IS NULL OR failure_code IN "
        "('provider_config_error', 'provider_auth_error', 'json_mode_unsupported', "
        "'provider_timeout', 'provider_rate_limited', 'invalid_ai_response', "
        "'invalid_ai_output', 'provider_error')",
    )
    op.drop_column("ideas", "embedding_input_version")
    op.drop_column("ideas", "embedding_dimensions")
    op.drop_column("ideas", "embedding_model")
    op.drop_column("ideas", "embedding")

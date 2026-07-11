"""创建点子投稿基础表。

Revision ID: 20260711_0003
Revises: 20260711_0002
Create Date: 2026-07-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260711_0003"
down_revision: str | None = "20260711_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建投稿入口所需字段、约束和索引。"""

    op.create_table(
        "ideas",
        sa.Column("internal_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("public_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("submission_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("raw_content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.CHAR(length=64), nullable=False),
        sa.Column(
            "processing_status",
            sa.String(length=32),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "retry_count",
            sa.SmallInteger(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "processing_status IN "
            "('pending', 'evaluating', 'embedding', 'checking_duplicate', 'completed', 'failed')",
            name=op.f("ck_ideas_processing_status_allowed"),
        ),
        sa.CheckConstraint(
            "retry_count BETWEEN 0 AND 3",
            name=op.f("ck_ideas_retry_count_range"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_ideas_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("internal_id", name=op.f("pk_ideas")),
        sa.UniqueConstraint("public_id", name=op.f("uq_ideas_public_id")),
        sa.UniqueConstraint(
            "user_id",
            "submission_key",
            name="uq_ideas_user_id_submission_key",
        ),
    )
    op.create_index("ix_ideas_content_hash", "ideas", ["content_hash"], unique=False)
    op.create_index(
        "ix_ideas_processing_status_created_at",
        "ideas",
        ["processing_status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ideas_user_id_created_at",
        "ideas",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """删除点子投稿基础表。"""

    op.drop_index("ix_ideas_user_id_created_at", table_name="ideas")
    op.drop_index("ix_ideas_processing_status_created_at", table_name="ideas")
    op.drop_index("ix_ideas_content_hash", table_name="ideas")
    op.drop_table("ideas")

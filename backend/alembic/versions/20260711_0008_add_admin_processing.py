"""增加管理员最终处理和模拟打款。

Revision ID: 20260711_0008
Revises: 20260711_0007
Create Date: 2026-07-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260711_0008"
down_revision: str | None = "20260711_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """增加一次性管理员动作和正金额模拟流水。"""

    op.add_column("ideas", sa.Column("admin_action", sa.String(length=16), nullable=True))
    op.add_column("ideas", sa.Column("admin_amount", sa.Numeric(6, 2), nullable=True))
    op.add_column("ideas", sa.Column("admin_reason", sa.Text(), nullable=True))
    op.add_column("ideas", sa.Column("processed_by_admin_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "ideas", sa.Column("admin_processed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_ideas_processed_by_admin_id_users"),
        "ideas",
        "users",
        ["processed_by_admin_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        op.f("ck_ideas_admin_action_allowed"),
        "ideas",
        "admin_action IS NULL OR admin_action IN ('confirmed', 'adjusted', 'rejected')",
    )
    op.create_check_constraint(
        op.f("ck_ideas_admin_fields_together"),
        "ideas",
        "((admin_action IS NULL AND admin_amount IS NULL AND admin_reason IS NULL "
        "AND processed_by_admin_id IS NULL AND admin_processed_at IS NULL) OR "
        "(admin_action IS NOT NULL AND admin_amount IS NOT NULL "
        "AND processed_by_admin_id IS NOT NULL AND admin_processed_at IS NOT NULL))",
    )
    op.create_check_constraint(
        op.f("ck_ideas_admin_action_valid"),
        "ideas",
        "admin_action IS NULL OR "
        "(processing_status = 'completed' AND input_decision = 'accept' "
        "AND admin_amount BETWEEN 0 AND 100 "
        "AND (admin_action = 'confirmed' OR admin_reason IS NOT NULL) "
        "AND (admin_action <> 'rejected' OR admin_amount = 0))",
    )
    op.drop_constraint(op.f("ck_ideas_bounty_values_valid"), "ideas", type_="check")
    op.create_check_constraint(
        op.f("ck_ideas_bounty_values_valid"),
        "ideas",
        "commercial_score IS NULL OR "
        "(commercial_score BETWEEN 0 AND 100 "
        "AND base_amount BETWEEN 0 AND 100 "
        "AND duplicate_deduction BETWEEN 0 AND base_amount "
        "AND final_amount BETWEEN 0 AND 100 "
        "AND ((admin_action IS NULL "
        "AND base_amount = duplicate_deduction + final_amount) OR "
        "(admin_action IS NOT NULL AND final_amount = admin_amount)))",
    )

    op.create_table(
        "simulated_payouts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("idea_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.Numeric(6, 2), nullable=False),
        sa.Column("reference", sa.String(length=40), nullable=False),
        sa.Column("confirmed_by_admin_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "confirmed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "amount > 0 AND amount <= 100", name=op.f("ck_simulated_payouts_amount_range")
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by_admin_id"],
            ["users.id"],
            name=op.f("fk_simulated_payouts_confirmed_by_admin_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["idea_id"],
            ["ideas.internal_id"],
            name=op.f("fk_simulated_payouts_idea_id_ideas"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_simulated_payouts")),
        sa.UniqueConstraint("idea_id", name=op.f("uq_simulated_payouts_idea_id")),
        sa.UniqueConstraint("reference", name=op.f("uq_simulated_payouts_reference")),
    )


def downgrade() -> None:
    """删除模拟打款和管理员处理字段。"""

    op.drop_table("simulated_payouts")
    op.drop_constraint(op.f("ck_ideas_bounty_values_valid"), "ideas", type_="check")
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
    for name in ("admin_action_valid", "admin_fields_together", "admin_action_allowed"):
        op.drop_constraint(op.f(f"ck_ideas_{name}"), "ideas", type_="check")
    op.drop_constraint(op.f("fk_ideas_processed_by_admin_id_users"), "ideas", type_="foreignkey")
    for column in (
        "admin_processed_at",
        "processed_by_admin_id",
        "admin_reason",
        "admin_amount",
        "admin_action",
    ):
        op.drop_column("ideas", column)

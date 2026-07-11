"""限制每个用户只保留一个会话。

Revision ID: 20260711_0002
Revises: 20260711_0001
Create Date: 2026-07-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import context, op

revision: str = "20260711_0002"
down_revision: str | None = "20260711_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _assert_no_duplicate_sessions() -> None:
    """拒绝静默删除既有的重复会话数据。"""

    if context.is_offline_mode():
        return

    duplicate_user_id = op.get_bind().scalar(
        sa.text(
            """
            SELECT user_id
            FROM sessions
            GROUP BY user_id
            HAVING count(*) > 1
            LIMIT 1
            """
        )
    )
    if duplicate_user_id is not None:
        raise RuntimeError(f"用户 {duplicate_user_id} 存在多条会话，请人工处理后重新执行迁移")


def upgrade() -> None:
    """用唯一约束在数据库层保证单用户单会话。"""

    _assert_no_duplicate_sessions()
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.create_unique_constraint("uq_sessions_user_id", "sessions", ["user_id"])


def downgrade() -> None:
    """恢复允许一个用户保存多个会话的结构。"""

    op.drop_constraint("uq_sessions_user_id", "sessions", type_="unique")
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], unique=False)

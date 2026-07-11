from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from idea_bounty.db.base import Base
from idea_bounty.models.enums import IdeaProcessingStatus

if TYPE_CHECKING:
    from idea_bounty.models.user import User


class Idea(Base):
    """用户提交并等待后续处理的点子。"""

    __tablename__ = "ideas"
    __table_args__ = (
        CheckConstraint(
            "processing_status IN "
            "('pending', 'evaluating', 'embedding', 'checking_duplicate', 'completed', 'failed')",
            name="processing_status_allowed",
        ),
        CheckConstraint("retry_count BETWEEN 0 AND 3", name="retry_count_range"),
        UniqueConstraint(
            "user_id",
            "submission_key",
            name="uq_ideas_user_id_submission_key",
        ),
        Index("ix_ideas_user_id_created_at", "user_id", "created_at"),
        Index(
            "ix_ideas_processing_status_created_at",
            "processing_status",
            "created_at",
        ),
        Index("ix_ideas_content_hash", "content_hash"),
    )

    internal_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    public_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        default=uuid4,
        unique=True,
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    submission_key: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    processing_status: Mapped[str] = mapped_column(
        String(32),
        default=IdeaProcessingStatus.PENDING.value,
        server_default=IdeaProcessingStatus.PENDING.value,
        nullable=False,
    )
    retry_count: Mapped[int] = mapped_column(
        SmallInteger,
        default=0,
        server_default="0",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="ideas")

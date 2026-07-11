from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from idea_bounty.db.base import Base

if TYPE_CHECKING:
    from idea_bounty.models.idea import Idea


class SimulatedPayout(Base):
    """管理员确认后生成的一条虚拟打款流水。"""

    __tablename__ = "simulated_payouts"
    __table_args__ = (CheckConstraint("amount > 0 AND amount <= 100", name="amount_range"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    idea_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ideas.internal_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    reference: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    confirmed_by_admin_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    idea: Mapped[Idea] = relationship(back_populates="payout")

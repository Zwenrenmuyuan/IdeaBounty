from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from idea_bounty.models import (
    AdminAction,
    DuplicateVerdict,
    Idea,
    IdeaProcessingStatus,
    InputDecision,
    SimulatedPayout,
    User,
    UserRole,
)


class AdminIdeaStateError(Exception):
    """点子尚未完成或已经被管理员处理。"""


@dataclass(frozen=True, slots=True)
class AdminSummary:
    total_submissions: int
    completed_accepts: int
    duplicate_count: int
    estimated_total: Decimal
    confirmed_payout_count: int
    simulated_payout_total: Decimal


def promote_user_to_admin(db_session: Session, username: str) -> bool:
    """将一个已有账号提升为管理员，账号不存在时返回 False。"""

    user = db_session.scalar(select(User).where(User.username == username.strip().lower()))
    if user is None:
        return False
    user.role = UserRole.ADMIN.value
    db_session.commit()
    return True


def list_admin_ideas(
    db_session: Session,
    limit: int,
    offset: int,
) -> tuple[list[tuple[Idea, str]], int]:
    """只返回已经形成金额、可供管理员处理的有效投稿。"""

    reviewable_filters = (
        Idea.processing_status == IdeaProcessingStatus.COMPLETED.value,
        Idea.input_decision == InputDecision.ACCEPT.value,
        Idea.final_amount.is_not(None),
    )

    rows = db_session.execute(
        select(Idea, User.username)
        .join(User, Idea.user_id == User.id)
        .where(*reviewable_filters)
        .order_by(
            Idea.admin_action.is_(None).desc(),
            Idea.created_at.desc(),
            Idea.internal_id.desc(),
        )
        .limit(limit)
        .offset(offset)
    ).all()
    total = db_session.scalar(select(func.count(Idea.internal_id)).where(*reviewable_filters)) or 0
    return [(row[0], row[1]) for row in rows], total


def get_admin_idea(db_session: Session, public_id: UUID) -> tuple[Idea, str] | None:
    """按公开 ID 返回后台点子和投稿用户名。"""

    row = db_session.execute(
        select(Idea, User.username)
        .join(User, Idea.user_id == User.id)
        .options(selectinload(Idea.payout))
        .where(Idea.public_id == public_id)
    ).first()
    return (row[0], row[1]) if row is not None else None


def process_admin_idea(
    db_session: Session,
    public_id: UUID,
    admin_id: int,
    action: AdminAction,
    amount: Decimal | None,
    reason: str | None,
) -> Idea | None:
    """锁定完成投稿，保存管理员结果并按正金额生成模拟流水。"""

    idea = db_session.scalar(
        select(Idea)
        .options(selectinload(Idea.payout))
        .where(Idea.public_id == public_id)
        .with_for_update()
    )
    if idea is None:
        return None
    if (
        idea.processing_status != IdeaProcessingStatus.COMPLETED.value
        or idea.input_decision != InputDecision.ACCEPT.value
        or idea.final_amount is None
        or idea.admin_action is not None
    ):
        raise AdminIdeaStateError

    if action is AdminAction.CONFIRMED:
        final_amount = idea.final_amount
    elif action is AdminAction.ADJUSTED and amount is not None:
        final_amount = amount
    elif action is AdminAction.REJECTED:
        final_amount = Decimal("0.00")
    else:
        raise AdminIdeaStateError

    idea.admin_action = action.value
    idea.admin_amount = final_amount
    idea.admin_reason = reason
    idea.processed_by_admin_id = admin_id
    idea.admin_processed_at = func.now()
    idea.final_amount = final_amount
    if final_amount > 0:
        idea.payout = SimulatedPayout(
            amount=final_amount,
            reference=f"SIM-{uuid4().hex.upper()}",
            confirmed_by_admin_id=admin_id,
        )
    try:
        db_session.commit()
    except Exception:
        db_session.rollback()
        raise
    return idea


def get_admin_summary(db_session: Session) -> AdminSummary:
    """直接聚合当前数据，MVP 不引入缓存或汇总表。"""

    completed_filter = (
        Idea.processing_status == IdeaProcessingStatus.COMPLETED.value,
        Idea.input_decision == InputDecision.ACCEPT.value,
    )
    return AdminSummary(
        total_submissions=db_session.scalar(select(func.count(Idea.internal_id))) or 0,
        completed_accepts=db_session.scalar(
            select(func.count(Idea.internal_id)).where(*completed_filter)
        )
        or 0,
        duplicate_count=db_session.scalar(
            select(func.count(Idea.internal_id)).where(
                *completed_filter,
                Idea.effective_duplicate_verdict == DuplicateVerdict.DUPLICATE.value,
            )
        )
        or 0,
        estimated_total=db_session.scalar(select(func.sum(Idea.final_amount))) or Decimal("0.00"),
        confirmed_payout_count=db_session.scalar(select(func.count(SimulatedPayout.id))) or 0,
        simulated_payout_total=db_session.scalar(select(func.sum(SimulatedPayout.amount)))
        or Decimal("0.00"),
    )

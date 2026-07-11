from dataclasses import dataclass
from hashlib import sha256
from unicodedata import normalize
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from idea_bounty.models import Idea, IdeaProcessingStatus

SUBMISSION_KEY_CONSTRAINT = "uq_ideas_user_id_submission_key"


class SubmissionKeyConflictError(Exception):
    """同一用户将一个幂等键用于不同原文。"""


@dataclass(frozen=True, slots=True)
class IdeaCreationResult:
    """区分首次创建和幂等重放的服务结果。"""

    idea: Idea
    created: bool


def calculate_content_hash(raw_content: str) -> str:
    """计算用于后续精确重复召回的规范化内容哈希。"""

    normalized_content = normalize("NFKC", raw_content).casefold()
    collapsed_content = " ".join(normalized_content.split())
    return sha256(collapsed_content.encode()).hexdigest()


def _find_by_submission_key(
    db_session: Session,
    user_id: int,
    submission_key: UUID,
) -> Idea | None:
    """查询当前用户已经占用该幂等键的点子。"""

    return db_session.scalar(
        select(Idea).where(
            Idea.user_id == user_id,
            Idea.submission_key == submission_key,
        )
    )


def _resolve_existing_idea(existing_idea: Idea, raw_content: str) -> IdeaCreationResult:
    """相同原文视为重放，不同原文视为幂等键冲突。"""

    if existing_idea.raw_content != raw_content:
        raise SubmissionKeyConflictError
    return IdeaCreationResult(idea=existing_idea, created=False)


def _get_constraint_name(exc: IntegrityError) -> str | None:
    """从 psycopg 异常中安全读取 PostgreSQL 约束名。"""

    constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    return constraint_name if isinstance(constraint_name, str) else None


def create_or_get_idea(
    db_session: Session,
    user_id: int,
    submission_key: UUID,
    raw_content: str,
) -> IdeaCreationResult:
    """创建点子，并在重复请求或并发冲突时返回既有结果。"""

    existing_idea = _find_by_submission_key(db_session, user_id, submission_key)
    if existing_idea is not None:
        return _resolve_existing_idea(existing_idea, raw_content)

    idea = Idea(
        user_id=user_id,
        submission_key=submission_key,
        raw_content=raw_content,
        content_hash=calculate_content_hash(raw_content),
        processing_status=IdeaProcessingStatus.PENDING.value,
        retry_count=0,
    )
    db_session.add(idea)
    try:
        db_session.commit()
    except IntegrityError as exc:
        db_session.rollback()
        if _get_constraint_name(exc) != SUBMISSION_KEY_CONSTRAINT:
            raise
        concurrent_idea = _find_by_submission_key(db_session, user_id, submission_key)
        if concurrent_idea is None:
            raise
        return _resolve_existing_idea(concurrent_idea, raw_content)
    except Exception:
        db_session.rollback()
        raise
    return IdeaCreationResult(idea=idea, created=True)


def list_user_ideas(
    db_session: Session,
    user_id: int,
    limit: int,
    offset: int,
) -> tuple[list[Idea], int]:
    """按稳定倒序返回当前用户的一页点子和总数。"""

    ideas = list(
        db_session.scalars(
            select(Idea)
            .where(Idea.user_id == user_id)
            .order_by(Idea.created_at.desc(), Idea.internal_id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    total = db_session.scalar(select(func.count(Idea.internal_id)).where(Idea.user_id == user_id))
    return ideas, total or 0


def get_user_idea(db_session: Session, user_id: int, public_id: UUID) -> Idea | None:
    """只在点子属于当前用户时返回详情。"""

    return db_session.scalar(
        select(Idea).where(
            Idea.user_id == user_id,
            Idea.public_id == public_id,
        )
    )

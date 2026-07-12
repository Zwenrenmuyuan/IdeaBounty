from dataclasses import dataclass
from hashlib import sha256
from unicodedata import normalize
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from idea_bounty.models import Idea, IdeaProcessingStatus, InputDecision

SUBMISSION_KEY_CONSTRAINT = "uq_ideas_user_id_submission_key"


class SubmissionKeyConflictError(Exception):
    """同一用户将一个幂等键用于不同原文。"""


class IdeaSupplementStateError(Exception):
    """点子当前状态不允许补充后重新评估。"""


class IdeaDeleteStateError(Exception):
    """点子已经进入不可删除的业务阶段。"""


@dataclass(frozen=True, slots=True)
class IdeaCreationResult:
    """区分首次创建和幂等重放的服务结果。"""

    idea: Idea
    created: bool


def calculate_content_hash(raw_content: str) -> str:
    """计算用于后续精确重复召回的规范化内容哈希。"""

    return sha256(normalize_content_for_hash(raw_content).encode()).hexdigest()


def normalize_content_for_hash(raw_content: str) -> str:
    """规范化原文，供哈希计算和哈希命中后的二次比较复用。"""

    normalized_content = normalize("NFKC", raw_content).casefold()
    return " ".join(normalized_content.split())


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


def supplement_user_idea(
    db_session: Session,
    user_id: int,
    public_id: UUID,
    raw_content: str,
) -> Idea | None:
    """复用需补充记录，清空旧门禁结果并重新进入处理队列。"""

    idea = db_session.scalar(
        select(Idea)
        .where(
            Idea.user_id == user_id,
            Idea.public_id == public_id,
        )
        .with_for_update()
    )
    if idea is None:
        return None
    if (
        idea.processing_status != IdeaProcessingStatus.COMPLETED.value
        or idea.input_decision != InputDecision.CLARIFY.value
    ):
        raise IdeaSupplementStateError

    idea.raw_content = raw_content
    idea.content_hash = calculate_content_hash(raw_content)
    idea.processing_status = IdeaProcessingStatus.PENDING.value
    idea.retry_count = 0
    idea.input_decision = None
    idea.decision_reason = None
    idea.normalized_content = None
    idea.dimension_scores = None
    idea.evaluation_model = None
    idea.evaluation_prompt_version = None
    idea.evaluation_schema_version = None
    idea.embedding = None
    idea.embedding_model = None
    idea.embedding_dimensions = None
    idea.embedding_input_version = None
    idea.failure_stage = None
    idea.failure_code = None
    idea.completed_at = None
    idea.updated_at = func.now()
    db_session.commit()
    return idea


def delete_user_idea(db_session: Session, user_id: int, public_id: UUID) -> bool | None:
    """删除尚未形成有效评估结果的投稿。"""

    idea = db_session.scalar(
        select(Idea)
        .where(
            Idea.user_id == user_id,
            Idea.public_id == public_id,
        )
        .with_for_update()
    )
    if idea is None:
        return None
    deletable_terminal = (
        idea.processing_status == IdeaProcessingStatus.COMPLETED.value
        and idea.input_decision in {InputDecision.CLARIFY.value, InputDecision.REJECT.value}
    )
    if idea.processing_status != IdeaProcessingStatus.FAILED.value and not deletable_terminal:
        raise IdeaDeleteStateError

    db_session.delete(idea)
    db_session.commit()
    return True


def get_matched_public_id(db_session: Session, idea: Idea) -> UUID | None:
    """把内部匹配关系转换为用户可见的随机公开 ID。"""

    if idea.matched_idea_id is None:
        return None
    return db_session.scalar(select(Idea.public_id).where(Idea.internal_id == idea.matched_idea_id))


def get_public_idea(db_session: Session, public_id: UUID) -> Idea | None:
    """只返回已经完成且允许公开白名单摘要的点子。"""

    return db_session.scalar(
        select(Idea).where(
            Idea.public_id == public_id,
            Idea.processing_status == IdeaProcessingStatus.COMPLETED.value,
            Idea.input_decision == InputDecision.ACCEPT.value,
            Idea.duplicate_method.is_not(None),
        )
    )

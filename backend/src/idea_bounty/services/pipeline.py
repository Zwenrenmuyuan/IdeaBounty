from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from idea_bounty.ai import EvaluationProvider
from idea_bounty.embedding import EmbeddingProvider
from idea_bounty.models import FailureStage, Idea, IdeaProcessingStatus
from idea_bounty.services.embedding import run_claimed_embedding
from idea_bounty.services.evaluation import (
    process_pending_evaluation_stage,
    run_claimed_evaluation,
)
from idea_bounty.services.idea import get_user_idea

MAX_USER_RETRIES = 3


class IdeaRetryStateError(Exception):
    """点子当前状态不允许用户重试。"""


class IdeaRetryLimitError(Exception):
    """点子已经达到用户重试次数上限。"""


def _refresh_idea(db_session: Session, idea: Idea) -> Idea:
    """清除会话缓存并读取数据库最新状态。"""

    db_session.expire(idea)
    db_session.refresh(idea)
    return idea


def process_idea_pipeline(
    db_session: Session,
    idea: Idea,
    evaluation_provider: EvaluationProvider,
    embedding_provider: EmbeddingProvider,
) -> Idea:
    """处理当前请求亲自认领的评估和 Embedding 阶段。"""

    evaluation_result = process_pending_evaluation_stage(
        db_session,
        idea,
        evaluation_provider,
    )
    if not evaluation_result.continue_to_embedding:
        return evaluation_result.idea
    return run_claimed_embedding(db_session, evaluation_result.idea, embedding_provider)


def retry_failed_pipeline(
    db_session: Session,
    user_id: int,
    public_id: UUID,
    evaluation_provider: EvaluationProvider,
    embedding_provider: EmbeddingProvider,
) -> Idea | None:
    """按服务端保存的失败阶段重新发起一轮处理。"""

    idea = get_user_idea(db_session, user_id, public_id)
    if idea is None:
        return None
    if idea.processing_status != IdeaProcessingStatus.FAILED.value or idea.failure_stage not in {
        FailureStage.EVALUATING.value,
        FailureStage.EMBEDDING.value,
    }:
        raise IdeaRetryStateError
    if idea.retry_count >= MAX_USER_RETRIES:
        raise IdeaRetryLimitError

    failure_stage = FailureStage(idea.failure_stage)
    target_status = (
        IdeaProcessingStatus.EVALUATING
        if failure_stage is FailureStage.EVALUATING
        else IdeaProcessingStatus.EMBEDDING
    )
    claimed_id = db_session.scalar(
        update(Idea)
        .where(
            Idea.internal_id == idea.internal_id,
            Idea.processing_status == IdeaProcessingStatus.FAILED.value,
            Idea.failure_stage == failure_stage.value,
            Idea.retry_count < MAX_USER_RETRIES,
        )
        .values(
            processing_status=target_status.value,
            retry_count=Idea.retry_count + 1,
            failure_stage=None,
            failure_code=None,
            completed_at=None,
            updated_at=func.now(),
        )
        .returning(Idea.internal_id)
    )
    db_session.commit()
    if claimed_id is None:
        _refresh_idea(db_session, idea)
        if idea.retry_count >= MAX_USER_RETRIES:
            raise IdeaRetryLimitError
        raise IdeaRetryStateError

    _refresh_idea(db_session, idea)
    if failure_stage is FailureStage.EMBEDDING:
        return run_claimed_embedding(db_session, idea, embedding_provider)

    evaluation_result = run_claimed_evaluation(db_session, idea, evaluation_provider)
    if not evaluation_result.continue_to_embedding:
        return evaluation_result.idea
    return run_claimed_embedding(db_session, evaluation_result.idea, embedding_provider)

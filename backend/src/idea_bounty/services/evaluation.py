from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from idea_bounty.ai import (
    EvaluationProvider,
    EvaluationProviderError,
    EvaluationProviderResult,
)
from idea_bounty.ai.prompts import EVALUATION_PROMPT_VERSION, EVALUATION_SCHEMA_VERSION
from idea_bounty.models import FailureStage, Idea, IdeaProcessingStatus, InputDecision
from idea_bounty.services.idea import get_user_idea

MAX_USER_RETRIES = 3


class IdeaRetryStateError(Exception):
    """点子当前状态不允许用户重试。"""


class IdeaRetryLimitError(Exception):
    """点子已经达到用户重试次数上限。"""


def _refresh_idea(db_session: Session, idea: Idea) -> Idea:
    """清除会话缓存并读取数据库中的最新点子状态。"""

    db_session.expire(idea)
    db_session.refresh(idea)
    return idea


def _claim_pending_evaluation(db_session: Session, idea: Idea) -> bool:
    """原子认领 pending 点子，避免幂等重放重复调用 AI。"""

    claimed_id = db_session.scalar(
        update(Idea)
        .where(
            Idea.internal_id == idea.internal_id,
            Idea.processing_status == IdeaProcessingStatus.PENDING.value,
        )
        .values(
            processing_status=IdeaProcessingStatus.EVALUATING.value,
            updated_at=func.now(),
        )
        .returning(Idea.internal_id)
    )
    db_session.commit()
    return claimed_id is not None


def _store_evaluation_failure(
    db_session: Session,
    idea: Idea,
    error: EvaluationProviderError,
) -> Idea:
    """把安全失败分类写入点子，不保存服务商原始响应。"""

    db_session.execute(
        update(Idea)
        .where(
            Idea.internal_id == idea.internal_id,
            Idea.processing_status == IdeaProcessingStatus.EVALUATING.value,
        )
        .values(
            processing_status=IdeaProcessingStatus.FAILED.value,
            failure_stage=FailureStage.EVALUATING.value,
            failure_code=error.failure_code.value,
            completed_at=None,
            updated_at=func.now(),
        )
    )
    db_session.commit()
    return _refresh_idea(db_session, idea)


def _store_evaluation_success(
    db_session: Session,
    idea: Idea,
    provider_result: EvaluationProviderResult,
) -> Idea:
    """整体保存已校验结果，并推进到下一阶段或门禁终态。"""

    output = provider_result.output
    accepted = output.input_decision is InputDecision.ACCEPT
    processing_status = (
        IdeaProcessingStatus.EMBEDDING.value if accepted else IdeaProcessingStatus.COMPLETED.value
    )
    dimension_scores = (
        output.evaluation.model_dump(mode="json") if output.evaluation is not None else None
    )
    db_session.execute(
        update(Idea)
        .where(
            Idea.internal_id == idea.internal_id,
            Idea.processing_status == IdeaProcessingStatus.EVALUATING.value,
        )
        .values(
            processing_status=processing_status,
            input_decision=output.input_decision.value,
            decision_reason=output.decision_reason,
            normalized_content=output.normalized_content().model_dump(mode="json"),
            dimension_scores=dimension_scores,
            evaluation_model=provider_result.model_id,
            evaluation_prompt_version=EVALUATION_PROMPT_VERSION,
            evaluation_schema_version=EVALUATION_SCHEMA_VERSION,
            failure_stage=None,
            failure_code=None,
            completed_at=func.now() if not accepted else None,
            updated_at=func.now(),
        )
    )
    db_session.commit()
    return _refresh_idea(db_session, idea)


def _run_claimed_evaluation(
    db_session: Session,
    idea: Idea,
    provider: EvaluationProvider,
) -> Idea:
    """在数据库事务外调用 AI，再用短事务保存整体结果。"""

    try:
        provider_result = provider.evaluate(idea.raw_content)
    except EvaluationProviderError as exc:
        return _store_evaluation_failure(db_session, idea, exc)
    return _store_evaluation_success(db_session, idea, provider_result)


def process_pending_evaluation(
    db_session: Session,
    idea: Idea,
    provider: EvaluationProvider,
) -> Idea:
    """认领并处理 pending 投稿，其他状态只返回最新快照。"""

    if not _claim_pending_evaluation(db_session, idea):
        return _refresh_idea(db_session, idea)
    return _run_claimed_evaluation(db_session, idea, provider)


def retry_failed_evaluation(
    db_session: Session,
    user_id: int,
    public_id: UUID,
    provider: EvaluationProvider,
) -> Idea | None:
    """由点子所有者重新发起一整轮 evaluating 阶段处理。"""

    idea = get_user_idea(db_session, user_id, public_id)
    if idea is None:
        return None
    if idea.processing_status != IdeaProcessingStatus.FAILED.value or (
        idea.failure_stage != FailureStage.EVALUATING.value
    ):
        raise IdeaRetryStateError
    if idea.retry_count >= MAX_USER_RETRIES:
        raise IdeaRetryLimitError

    claimed_id = db_session.scalar(
        update(Idea)
        .where(
            Idea.internal_id == idea.internal_id,
            Idea.processing_status == IdeaProcessingStatus.FAILED.value,
            Idea.failure_stage == FailureStage.EVALUATING.value,
            Idea.retry_count < MAX_USER_RETRIES,
        )
        .values(
            processing_status=IdeaProcessingStatus.EVALUATING.value,
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
    return _run_claimed_evaluation(db_session, idea, provider)

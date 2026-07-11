from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from idea_bounty.ai import (
    EvaluationProvider,
    EvaluationProviderError,
    EvaluationProviderResult,
)
from idea_bounty.ai.prompts import EVALUATION_PROMPT_VERSION, EVALUATION_SCHEMA_VERSION
from idea_bounty.models import FailureStage, Idea, IdeaProcessingStatus, InputDecision


@dataclass(frozen=True, slots=True)
class EvaluationStageResult:
    """评估阶段结果及当前调用是否应继续生成向量。"""

    idea: Idea
    continue_to_embedding: bool


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
) -> EvaluationStageResult:
    """在数据库事务外调用 AI，再用短事务保存整体结果。"""

    try:
        provider_result = provider.evaluate(idea.raw_content)
    except EvaluationProviderError as exc:
        failed_idea = _store_evaluation_failure(db_session, idea, exc)
        return EvaluationStageResult(failed_idea, continue_to_embedding=False)
    evaluated_idea = _store_evaluation_success(db_session, idea, provider_result)
    return EvaluationStageResult(
        evaluated_idea,
        continue_to_embedding=(
            evaluated_idea.processing_status == IdeaProcessingStatus.EMBEDDING.value
        ),
    )


def run_claimed_evaluation(
    db_session: Session,
    idea: Idea,
    provider: EvaluationProvider,
) -> EvaluationStageResult:
    """运行已经进入 evaluating 状态的评估阶段。"""

    return _run_claimed_evaluation(db_session, idea, provider)


def process_pending_evaluation_stage(
    db_session: Session,
    idea: Idea,
    provider: EvaluationProvider,
) -> EvaluationStageResult:
    """认领 pending 投稿，并标记当前调用是否可以继续下游阶段。"""

    if not _claim_pending_evaluation(db_session, idea):
        return EvaluationStageResult(
            _refresh_idea(db_session, idea),
            continue_to_embedding=False,
        )
    return _run_claimed_evaluation(db_session, idea, provider)


def process_pending_evaluation(
    db_session: Session,
    idea: Idea,
    provider: EvaluationProvider,
) -> Idea:
    """认领并处理 pending 投稿，其他状态只返回最新快照。"""

    return process_pending_evaluation_stage(db_session, idea, provider).idea

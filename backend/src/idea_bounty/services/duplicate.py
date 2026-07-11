from __future__ import annotations

import json

from pydantic import ValidationError
from sqlalchemy import func, update
from sqlalchemy.orm import Session

from idea_bounty.ai import DuplicateProvider, DuplicateProviderError, DuplicateProviderResult
from idea_bounty.ai.duplicate_prompts import DUPLICATE_PROMPT_VERSION, DUPLICATE_SCHEMA_VERSION
from idea_bounty.models import (
    DuplicateMethod,
    DuplicateVerdict,
    FailureCode,
    FailureStage,
    Idea,
    IdeaProcessingStatus,
    ScoreConfidence,
)
from idea_bounty.schemas.ai import NormalizedContent
from idea_bounty.schemas.duplicate import (
    ComparableIdea,
    DuplicateCandidateInput,
    DuplicateComparisonInput,
    DuplicateComparisonSnapshot,
)
from idea_bounty.services.duplicate_recall import (
    CandidateDataError,
    CandidateRecallStateError,
    DuplicateRecallResult,
    recall_duplicate_candidates,
)

EXACT_HASH_REASON = "投稿内容与历史点子的规范化文本完全一致"
NO_CANDIDATES_REASON = "未召回可比较的历史点子"


def _refresh_idea(db_session: Session, idea: Idea) -> Idea:
    """读取查重阶段提交后的最新点子快照。"""

    db_session.expire(idea)
    db_session.refresh(idea)
    return idea


def _store_duplicate_failure(
    db_session: Session,
    idea: Idea,
    failure_code: FailureCode,
) -> Idea:
    """记录安全失败分类，不保存候选或模型原始输出。"""

    db_session.execute(
        update(Idea)
        .where(
            Idea.internal_id == idea.internal_id,
            Idea.processing_status == IdeaProcessingStatus.CHECKING_DUPLICATE.value,
            Idea.duplicate_method.is_(None),
        )
        .values(
            processing_status=IdeaProcessingStatus.FAILED.value,
            failure_stage=FailureStage.CHECKING_DUPLICATE.value,
            failure_code=failure_code.value,
            completed_at=None,
            updated_at=func.now(),
        )
    )
    db_session.commit()
    return _refresh_idea(db_session, idea)


def _store_duplicate_success(
    db_session: Session,
    idea: Idea,
    *,
    method: DuplicateMethod,
    ai_verdict: DuplicateVerdict,
    effective_verdict: DuplicateVerdict,
    confidence: ScoreConfidence,
    matched_idea_id: int | None,
    reason: str,
    comparison: DuplicateComparisonSnapshot | None = None,
    model_id: str | None = None,
) -> Idea:
    """原子保存完整查重快照并推进到 completed。"""

    db_session.execute(
        update(Idea)
        .where(
            Idea.internal_id == idea.internal_id,
            Idea.processing_status == IdeaProcessingStatus.CHECKING_DUPLICATE.value,
            Idea.duplicate_method.is_(None),
        )
        .values(
            processing_status=IdeaProcessingStatus.COMPLETED.value,
            duplicate_method=method.value,
            ai_duplicate_verdict=ai_verdict.value,
            effective_duplicate_verdict=effective_verdict.value,
            duplicate_confidence=confidence.value,
            matched_idea_id=matched_idea_id,
            duplicate_reason=reason,
            duplicate_comparison=(
                comparison.model_dump(mode="json") if comparison is not None else None
            ),
            duplicate_model=model_id,
            duplicate_prompt_version=(
                DUPLICATE_PROMPT_VERSION if method is DuplicateMethod.LLM_CANDIDATES else None
            ),
            duplicate_schema_version=(
                DUPLICATE_SCHEMA_VERSION if method is DuplicateMethod.LLM_CANDIDATES else None
            ),
            failure_stage=None,
            failure_code=None,
            completed_at=func.now(),
            updated_at=func.now(),
        )
    )
    db_session.commit()
    return _refresh_idea(db_session, idea)


def _parse_current_content(idea: Idea) -> NormalizedContent:
    """重新校验当前点子的规范化快照。"""

    try:
        return NormalizedContent.model_validate_json(
            json.dumps(idea.normalized_content, ensure_ascii=False)
        )
    except (TypeError, ValidationError) as exc:
        raise CandidateDataError("当前点子的规范化内容无效") from exc


def _build_comparison(idea: Idea, recall: DuplicateRecallResult) -> DuplicateComparisonInput:
    """把召回结果投影为不包含相似度的模型输入。"""

    current = ComparableIdea.from_normalized_content(_parse_current_content(idea))
    return DuplicateComparisonInput(
        current=current,
        candidates=[
            DuplicateCandidateInput(
                internal_id=candidate.internal_id,
                content=ComparableIdea.from_normalized_content(candidate.normalized_content),
            )
            for candidate in recall.semantic_candidates
        ],
    )


def _store_provider_result(
    db_session: Session,
    idea: Idea,
    result: DuplicateProviderResult,
) -> Idea:
    output = result.output
    effective_verdict = output.verdict
    if output.verdict is DuplicateVerdict.DUPLICATE and output.confidence in {
        ScoreConfidence.MEDIUM,
        ScoreConfidence.LOW,
    }:
        effective_verdict = DuplicateVerdict.RELATED
    return _store_duplicate_success(
        db_session,
        idea,
        method=DuplicateMethod.LLM_CANDIDATES,
        ai_verdict=output.verdict,
        effective_verdict=effective_verdict,
        confidence=output.confidence,
        matched_idea_id=output.matched_internal_id,
        reason=output.reason,
        comparison=DuplicateComparisonSnapshot.from_judgment(output),
        model_id=result.model_id,
    )


def run_claimed_duplicate(
    db_session: Session,
    idea: Idea,
    provider: DuplicateProvider,
) -> Idea:
    """召回候选，并在数据库事务外执行必要的 LLM 查重。"""

    try:
        recall = recall_duplicate_candidates(db_session, idea)
        if recall.exact_match is not None:
            return _store_duplicate_success(
                db_session,
                idea,
                method=DuplicateMethod.EXACT_HASH,
                ai_verdict=DuplicateVerdict.DUPLICATE,
                effective_verdict=DuplicateVerdict.DUPLICATE,
                confidence=ScoreConfidence.HIGH,
                matched_idea_id=recall.exact_match,
                reason=EXACT_HASH_REASON,
            )
        if not recall.semantic_candidates:
            return _store_duplicate_success(
                db_session,
                idea,
                method=DuplicateMethod.NO_CANDIDATES,
                ai_verdict=DuplicateVerdict.NOVEL,
                effective_verdict=DuplicateVerdict.NOVEL,
                confidence=ScoreConfidence.HIGH,
                matched_idea_id=None,
                reason=NO_CANDIDATES_REASON,
            )
        comparison = _build_comparison(idea, recall)
    except (CandidateDataError, CandidateRecallStateError):
        return _store_duplicate_failure(db_session, idea, FailureCode.INVALID_AI_OUTPUT)

    # 关闭候选查询开启的只读事务，等待外部服务时不占用数据库事务。
    db_session.commit()
    try:
        provider_result = provider.judge(comparison)
    except DuplicateProviderError as exc:
        return _store_duplicate_failure(db_session, idea, exc.failure_code)
    return _store_provider_result(db_session, idea, provider_result)

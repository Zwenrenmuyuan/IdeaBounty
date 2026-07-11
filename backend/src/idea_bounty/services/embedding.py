from __future__ import annotations

import json

from pydantic import ValidationError
from sqlalchemy import func, update
from sqlalchemy.orm import Session

from idea_bounty.embedding import (
    EMBEDDING_INPUT_VERSION,
    EmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingProviderResult,
    build_embedding_text,
)
from idea_bounty.models import FailureCode, FailureStage, Idea, IdeaProcessingStatus
from idea_bounty.schemas.ai import NormalizedContent


def _refresh_idea(db_session: Session, idea: Idea) -> Idea:
    """读取 Embedding 阶段提交后的最新点子快照。"""

    db_session.expire(idea)
    db_session.refresh(idea)
    return idea


def _build_idea_embedding_text(idea: Idea) -> str:
    """重新校验已保存的规范化内容，再构建中性向量文本。"""

    try:
        content = NormalizedContent.model_validate_json(
            json.dumps(idea.normalized_content, ensure_ascii=False)
        )
    except ValidationError as exc:
        raise EmbeddingProviderError(
            FailureCode.INVALID_AI_OUTPUT,
            "已保存的规范化内容无法用于 Embedding",
            retryable=False,
        ) from exc
    text = build_embedding_text(content)
    if not text:
        raise EmbeddingProviderError(
            FailureCode.INVALID_AI_OUTPUT,
            "规范化内容没有可用的 Embedding 字段",
            retryable=False,
        )
    return text


def _store_embedding_failure(
    db_session: Session,
    idea: Idea,
    error: EmbeddingProviderError,
) -> Idea:
    """保存安全失败分类，并保留上游 AI 评估结果。"""

    db_session.execute(
        update(Idea)
        .where(
            Idea.internal_id == idea.internal_id,
            Idea.processing_status == IdeaProcessingStatus.EMBEDDING.value,
            Idea.embedding.is_(None),
        )
        .values(
            processing_status=IdeaProcessingStatus.FAILED.value,
            failure_stage=FailureStage.EMBEDDING.value,
            failure_code=error.failure_code.value,
            completed_at=None,
            updated_at=func.now(),
        )
    )
    db_session.commit()
    return _refresh_idea(db_session, idea)


def _store_embedding_success(
    db_session: Session,
    idea: Idea,
    result: EmbeddingProviderResult,
) -> Idea:
    """原子保存向量快照并推进到待查重状态。"""

    db_session.execute(
        update(Idea)
        .where(
            Idea.internal_id == idea.internal_id,
            Idea.processing_status == IdeaProcessingStatus.EMBEDDING.value,
            Idea.embedding.is_(None),
        )
        .values(
            processing_status=IdeaProcessingStatus.CHECKING_DUPLICATE.value,
            embedding=list(result.vector),
            embedding_model=result.model_id,
            embedding_dimensions=result.dimensions,
            embedding_input_version=EMBEDDING_INPUT_VERSION,
            failure_stage=None,
            failure_code=None,
            completed_at=None,
            updated_at=func.now(),
        )
    )
    db_session.commit()
    return _refresh_idea(db_session, idea)


def run_claimed_embedding(
    db_session: Session,
    idea: Idea,
    provider: EmbeddingProvider,
) -> Idea:
    """在事务外生成向量，再用短事务保存结果。"""

    try:
        text = _build_idea_embedding_text(idea)
        result = provider.embed(text)
    except EmbeddingProviderError as exc:
        return _store_embedding_failure(db_session, idea, exc)
    return _store_embedding_success(db_session, idea, result)

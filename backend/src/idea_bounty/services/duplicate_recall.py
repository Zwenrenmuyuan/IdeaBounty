from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from idea_bounty.embedding import EXPECTED_EMBEDDING_DIMENSIONS
from idea_bounty.models import Idea, IdeaProcessingStatus, InputDecision
from idea_bounty.schemas.ai import NormalizedContent
from idea_bounty.services.idea import normalize_content_for_hash

SEMANTIC_CANDIDATE_LIMIT = 10


class CandidateRecallStateError(Exception):
    """当前点子没有处于可执行候选召回的完整状态。"""


class CandidateDataError(Exception):
    """历史候选的规范化快照无法通过正式数据契约。"""


@dataclass(frozen=True, slots=True)
class SemanticCandidate:
    """供后续查重判定使用的内部语义候选。"""

    internal_id: int
    normalized_content: NormalizedContent
    cosine_similarity: float


@dataclass(frozen=True, slots=True)
class DuplicateRecallResult:
    """精确匹配优先的候选召回结果。"""

    exact_match: int | None
    semantic_candidates: tuple[SemanticCandidate, ...]


def _validate_source_idea(idea: Idea) -> list[float]:
    """校验召回源点子的状态和完整向量快照。"""

    embedding = idea.embedding
    if (
        idea.processing_status != IdeaProcessingStatus.CHECKING_DUPLICATE.value
        or idea.input_decision != InputDecision.ACCEPT.value
        or embedding is None
        or idea.embedding_dimensions != EXPECTED_EMBEDDING_DIMENSIONS
        or len(embedding) != idea.embedding_dimensions
        or idea.embedding_model is None
        or not idea.embedding_model.strip()
        or idea.embedding_input_version is None
        or not idea.embedding_input_version.strip()
    ):
        raise CandidateRecallStateError("点子不处于可执行候选召回的完整状态")
    return list(embedding)


def _find_exact_match(db_session: Session, idea: Idea) -> int | None:
    """查找规范化原文完全一致的最早历史点子。"""

    source_content = normalize_content_for_hash(idea.raw_content)
    rows = db_session.execute(
        select(Idea.internal_id, Idea.raw_content)
        .where(
            Idea.internal_id < idea.internal_id,
            Idea.processing_status == IdeaProcessingStatus.COMPLETED.value,
            Idea.input_decision == InputDecision.ACCEPT.value,
            Idea.content_hash == idea.content_hash,
        )
        .order_by(Idea.internal_id.asc())
    )
    for internal_id, raw_content in rows:
        if normalize_content_for_hash(raw_content) == source_content:
            return int(internal_id)
    return None


def _parse_candidate_content(internal_id: int, value: Any) -> NormalizedContent:
    """重新校验候选 JSONB，不把损坏快照静默交给下游。"""

    try:
        return NormalizedContent.model_validate_json(json.dumps(value, ensure_ascii=False))
    except (TypeError, ValidationError) as exc:
        raise CandidateDataError(f"候选 {internal_id} 的规范化内容无效") from exc


def _find_semantic_candidates(
    db_session: Session,
    idea: Idea,
    source_embedding: list[float],
) -> tuple[SemanticCandidate, ...]:
    """使用 pgvector 精确余弦距离查询兼容的历史 Top 10。"""

    distance = Idea.embedding.cosine_distance(source_embedding).label("cosine_distance")
    rows = db_session.execute(
        select(Idea.internal_id, Idea.normalized_content, distance)
        .where(
            Idea.internal_id < idea.internal_id,
            Idea.processing_status == IdeaProcessingStatus.COMPLETED.value,
            Idea.input_decision == InputDecision.ACCEPT.value,
            Idea.embedding.is_not(None),
            Idea.embedding_model == idea.embedding_model,
            Idea.embedding_dimensions == idea.embedding_dimensions,
            Idea.embedding_input_version == idea.embedding_input_version,
            Idea.normalized_content.is_not(None),
        )
        .order_by(distance.asc(), Idea.internal_id.asc())
        .limit(SEMANTIC_CANDIDATE_LIMIT)
    )
    return tuple(
        SemanticCandidate(
            internal_id=int(internal_id),
            normalized_content=_parse_candidate_content(int(internal_id), normalized_content),
            cosine_similarity=1.0 - float(cosine_distance),
        )
        for internal_id, normalized_content, cosine_distance in rows
    )


def recall_duplicate_candidates(db_session: Session, idea: Idea) -> DuplicateRecallResult:
    """先查找精确重复，未命中时再召回语义候选。"""

    source_embedding = _validate_source_idea(idea)
    exact_match = _find_exact_match(db_session, idea)
    if exact_match is not None:
        return DuplicateRecallResult(exact_match=exact_match, semantic_candidates=())
    return DuplicateRecallResult(
        exact_match=None,
        semantic_candidates=_find_semantic_candidates(db_session, idea, source_embedding),
    )

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from idea_bounty.models import Idea, IdeaProcessingStatus, User
from idea_bounty.services.duplicate_recall import (
    CandidateDataError,
    CandidateRecallStateError,
    recall_duplicate_candidates,
)
from idea_bounty.services.idea import calculate_content_hash, normalize_content_for_hash
from tests.ai_fakes import make_evaluation_output

EMBEDDING_MODEL = "BAAI/bge-m3"
EMBEDDING_INPUT_VERSION = "embedding-input-v1"


def _vector(first: float = 1.0, second: float = 0.0) -> list[float]:
    return [first, second, *([0.0] * 1022)]


def _add_user(db_session: Session, username: str) -> User:
    user = User(username=username, password_hash="hash")
    db_session.add(user)
    db_session.commit()
    return user


def _add_idea(
    db_session: Session,
    user_id: int,
    raw_content: str,
    *,
    status: str = IdeaProcessingStatus.COMPLETED.value,
    decision: str = "accept",
    embedding: list[float] | None = None,
    embedding_model: str = EMBEDDING_MODEL,
    embedding_input_version: str = EMBEDDING_INPUT_VERSION,
    content_hash: str | None = None,
    duplicate_verdict: str = "novel",
    matched_idea_id: int | None = None,
) -> Idea:
    output = make_evaluation_output(decision)
    idea = Idea(
        user_id=user_id,
        submission_key=uuid4(),
        raw_content=raw_content,
        content_hash=content_hash or calculate_content_hash(raw_content),
        processing_status=status,
        retry_count=0,
        input_decision=decision,
        decision_reason=output.decision_reason,
        normalized_content=output.normalized_content().model_dump(mode="json"),
        dimension_scores=(
            output.evaluation.model_dump(mode="json") if output.evaluation is not None else None
        ),
        evaluation_model="fake-evaluation-model",
        evaluation_prompt_version="evaluation-v2",
        evaluation_schema_version="evaluation-v2",
        embedding=embedding,
        embedding_model=embedding_model if embedding is not None else None,
        embedding_dimensions=len(embedding) if embedding is not None else None,
        embedding_input_version=embedding_input_version if embedding is not None else None,
        duplicate_method=(
            ("exact_hash" if duplicate_verdict == "duplicate" else "no_candidates")
            if status == IdeaProcessingStatus.COMPLETED.value and decision == "accept"
            else None
        ),
        ai_duplicate_verdict=(
            duplicate_verdict
            if status == IdeaProcessingStatus.COMPLETED.value and decision == "accept"
            else None
        ),
        effective_duplicate_verdict=(
            duplicate_verdict
            if status == IdeaProcessingStatus.COMPLETED.value and decision == "accept"
            else None
        ),
        duplicate_confidence=(
            "high"
            if status == IdeaProcessingStatus.COMPLETED.value and decision == "accept"
            else None
        ),
        matched_idea_id=(
            matched_idea_id
            if status == IdeaProcessingStatus.COMPLETED.value and decision == "accept"
            else None
        ),
        duplicate_reason=(
            "历史查重测试快照"
            if status == IdeaProcessingStatus.COMPLETED.value and decision == "accept"
            else None
        ),
        failure_stage="checking_duplicate" if status == IdeaProcessingStatus.FAILED.value else None,
        failure_code="provider_error" if status == IdeaProcessingStatus.FAILED.value else None,
        completed_at=(
            datetime.now(UTC) if status == IdeaProcessingStatus.COMPLETED.value else None
        ),
    )
    db_session.add(idea)
    db_session.commit()
    return idea


def test_hash_normalization_is_reusable_and_backward_compatible() -> None:
    original = "  ＡＢＣ\t这是  一个测试痛点\n"
    equivalent = "abc 这是 一个测试痛点"

    assert normalize_content_for_hash(original) == equivalent
    assert calculate_content_hash(original) == calculate_content_hash(equivalent)


def test_exact_match_is_cross_user_and_selects_earliest(
    db_session: Session,
) -> None:
    alice = _add_user(db_session, "alice")
    bob = _add_user(db_session, "bob")
    earliest = _add_idea(db_session, bob.id, "ＡＢＣ   发票核对很耗时")
    _add_idea(db_session, alice.id, "abc\n发票核对很耗时")
    source = _add_idea(
        db_session,
        alice.id,
        "abc 发票核对很耗时",
        status=IdeaProcessingStatus.CHECKING_DUPLICATE.value,
        embedding=_vector(),
    )

    result = recall_duplicate_candidates(db_session, source)

    assert result.exact_match == earliest.internal_id
    assert result.semantic_candidates == ()


def test_exact_match_can_match_same_user(db_session: Session) -> None:
    user = _add_user(db_session, "alice")
    candidate = _add_idea(db_session, user.id, "餐厅每天都要人工检查食材日期")
    source = _add_idea(
        db_session,
        user.id,
        "餐厅每天都要人工检查食材日期",
        status=IdeaProcessingStatus.CHECKING_DUPLICATE.value,
        embedding=_vector(),
    )

    result = recall_duplicate_candidates(db_session, source)

    assert result.exact_match == candidate.internal_id


def test_hash_collision_requires_normalized_content_equality(
    db_session: Session,
) -> None:
    user = _add_user(db_session, "alice")
    source_raw_content = "小型诊所需要减少预约爽约"
    forced_hash = calculate_content_hash(source_raw_content)
    _add_idea(
        db_session,
        user.id,
        "餐饮门店需要管理食材保质期",
        content_hash=forced_hash,
    )
    source = _add_idea(
        db_session,
        user.id,
        source_raw_content,
        status=IdeaProcessingStatus.CHECKING_DUPLICATE.value,
        embedding=_vector(),
        content_hash=forced_hash,
    )

    result = recall_duplicate_candidates(db_session, source)

    assert result.exact_match is None
    assert result.semantic_candidates == ()


def test_exact_match_skips_semantic_candidate_parsing(db_session: Session) -> None:
    user = _add_user(db_session, "alice")
    invalid_candidate = _add_idea(
        db_session,
        user.id,
        "另一条语义候选",
        embedding=_vector(),
    )
    invalid_candidate.normalized_content = {"invalid": True}
    exact_candidate = _add_idea(db_session, user.id, "发票录入非常耗时")
    source = _add_idea(
        db_session,
        user.id,
        "发票录入非常耗时",
        status=IdeaProcessingStatus.CHECKING_DUPLICATE.value,
        embedding=_vector(),
    )
    db_session.commit()

    result = recall_duplicate_candidates(db_session, source)

    assert result.exact_match == exact_candidate.internal_id
    assert result.semantic_candidates == ()


def test_semantic_recall_returns_stable_top_ten(db_session: Session) -> None:
    user = _add_user(db_session, "alice")
    candidates = [
        _add_idea(
            db_session,
            user.id,
            f"候选点子 {index}",
            embedding=_vector(1.0, index / 10),
        )
        for index in range(1, 13)
    ]
    source = _add_idea(
        db_session,
        user.id,
        "当前待查重点子",
        status=IdeaProcessingStatus.CHECKING_DUPLICATE.value,
        embedding=_vector(),
    )

    result = recall_duplicate_candidates(db_session, source)

    assert result.exact_match is None
    assert [candidate.internal_id for candidate in result.semantic_candidates] == [
        candidate.internal_id for candidate in candidates[:10]
    ]
    similarities = [candidate.cosine_similarity for candidate in result.semantic_candidates]
    assert similarities == sorted(similarities, reverse=True)
    assert similarities[0] == pytest.approx(1 / (1.01**0.5))


def test_semantic_recall_breaks_distance_ties_by_internal_id(
    db_session: Session,
) -> None:
    user = _add_user(db_session, "alice")
    candidates = [
        _add_idea(db_session, user.id, f"同距离候选 {index}", embedding=_vector(1.0, 1.0))
        for index in range(3)
    ]
    source = _add_idea(
        db_session,
        user.id,
        "同距离排序的当前点子",
        status=IdeaProcessingStatus.CHECKING_DUPLICATE.value,
        embedding=_vector(),
    )

    result = recall_duplicate_candidates(db_session, source)

    assert [candidate.internal_id for candidate in result.semantic_candidates] == [
        candidate.internal_id for candidate in candidates
    ]


def test_semantic_recall_filters_ineligible_candidates(db_session: Session) -> None:
    alice = _add_user(db_session, "alice")
    bob = _add_user(db_session, "bob")
    eligible = _add_idea(db_session, bob.id, "跨用户有效候选", embedding=_vector())
    _add_idea(
        db_session,
        bob.id,
        "应被排除的有效重复记录",
        embedding=_vector(),
        duplicate_verdict="duplicate",
        matched_idea_id=eligible.internal_id,
    )
    _add_idea(
        db_session,
        alice.id,
        "仍在待查重",
        status=IdeaProcessingStatus.CHECKING_DUPLICATE.value,
        embedding=_vector(),
    )
    _add_idea(
        db_session,
        alice.id,
        "查重阶段失败",
        status=IdeaProcessingStatus.FAILED.value,
        embedding=_vector(),
    )
    _add_idea(db_session, alice.id, "需要补充信息", decision="clarify")
    _add_idea(db_session, alice.id, "输入已经拒绝", decision="reject")
    _add_idea(db_session, alice.id, "没有历史向量")
    _add_idea(
        db_session,
        alice.id,
        "向量模型不兼容",
        embedding=_vector(),
        embedding_model="another-model",
    )
    _add_idea(
        db_session,
        alice.id,
        "输入版本不兼容",
        embedding=_vector(),
        embedding_input_version="embedding-input-v0",
    )
    source = _add_idea(
        db_session,
        alice.id,
        "当前点子",
        status=IdeaProcessingStatus.CHECKING_DUPLICATE.value,
        embedding=_vector(),
    )
    _add_idea(db_session, bob.id, "创建时间更晚", embedding=_vector())

    result = recall_duplicate_candidates(db_session, source)

    assert [candidate.internal_id for candidate in result.semantic_candidates] == [
        eligible.internal_id
    ]


def test_semantic_recall_returns_empty_without_candidates(db_session: Session) -> None:
    user = _add_user(db_session, "alice")
    source = _add_idea(
        db_session,
        user.id,
        "没有任何历史候选",
        status=IdeaProcessingStatus.CHECKING_DUPLICATE.value,
        embedding=_vector(),
    )

    result = recall_duplicate_candidates(db_session, source)

    assert result.exact_match is None
    assert result.semantic_candidates == ()
    assert source.processing_status == IdeaProcessingStatus.CHECKING_DUPLICATE.value


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("processing_status", IdeaProcessingStatus.COMPLETED.value),
        ("input_decision", "reject"),
        ("embedding", None),
        ("embedding_dimensions", None),
        ("embedding_dimensions", 2),
        ("embedding_model", None),
        ("embedding_model", ""),
        ("embedding_input_version", None),
        ("embedding_input_version", ""),
    ],
)
def test_recall_rejects_incomplete_source_state(
    db_session: Session,
    field: str,
    value: object,
) -> None:
    idea = Idea(
        internal_id=1,
        processing_status=IdeaProcessingStatus.CHECKING_DUPLICATE.value,
        input_decision="accept",
        raw_content="当前点子",
        content_hash="a" * 64,
        embedding=_vector(),
        embedding_dimensions=1024,
        embedding_model=EMBEDDING_MODEL,
        embedding_input_version=EMBEDDING_INPUT_VERSION,
    )
    setattr(idea, field, value)

    with pytest.raises(CandidateRecallStateError):
        recall_duplicate_candidates(db_session, idea)


def test_recall_rejects_invalid_candidate_snapshot(db_session: Session) -> None:
    user = _add_user(db_session, "alice")
    candidate = _add_idea(db_session, user.id, "损坏的历史候选", embedding=_vector())
    candidate.normalized_content = {"invalid": True}
    db_session.commit()
    source = _add_idea(
        db_session,
        user.id,
        "当前待查重点子",
        status=IdeaProcessingStatus.CHECKING_DUPLICATE.value,
        embedding=_vector(),
    )

    with pytest.raises(CandidateDataError, match=str(candidate.internal_id)):
        recall_duplicate_candidates(db_session, source)

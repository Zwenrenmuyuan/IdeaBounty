from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import Engine, delete, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from idea_bounty.models import (
    Idea,
    IdeaProcessingStatus,
    InputDecision,
    User,
    UserRole,
    UserSession,
    UserStatus,
)
from idea_bounty.schemas.ai import EvaluationScores, NormalizedContent
from tests.ai_fakes import make_evaluation_output


def _make_user(username: str = "alice") -> User:
    return User(username=username, password_hash="argon2id-placeholder")


def _make_session(user: User, token_character: str = "a") -> UserSession:
    return UserSession(
        token_hash=token_character * 64,
        user=user,
        expires_at=datetime.now(UTC) + timedelta(days=3),
    )


def _make_idea(user: User, content: str = "这是一个用于数据库测试的点子") -> Idea:
    return Idea(
        user=user,
        submission_key=uuid4(),
        raw_content=content,
        content_hash="c" * 64,
    )


def test_migration_creates_expected_schema(test_engine: Engine) -> None:
    inspector = inspect(test_engine)

    assert {"alembic_version", "ideas", "sessions", "users"} <= set(inspector.get_table_names())
    assert {constraint["name"] for constraint in inspector.get_unique_constraints("users")} == {
        "uq_users_username"
    }
    assert {constraint["name"] for constraint in inspector.get_unique_constraints("sessions")} == {
        "uq_sessions_token_hash",
        "uq_sessions_user_id",
    }
    assert {constraint["name"] for constraint in inspector.get_check_constraints("users")} == {
        "ck_users_role_allowed",
        "ck_users_status_allowed",
    }

    foreign_key = inspector.get_foreign_keys("sessions")[0]
    assert foreign_key["name"] == "fk_sessions_user_id_users"
    assert foreign_key["options"]["ondelete"] == "CASCADE"

    assert {constraint["name"] for constraint in inspector.get_unique_constraints("ideas")} == {
        "uq_ideas_public_id",
        "uq_ideas_user_id_submission_key",
    }
    assert {constraint["name"] for constraint in inspector.get_check_constraints("ideas")} == {
        "ck_ideas_completed_at_matches_status",
        "ck_ideas_evaluation_result_complete",
        "ck_ideas_failure_code_allowed",
        "ck_ideas_failure_fields_together",
        "ck_ideas_failure_matches_status",
        "ck_ideas_failure_stage_allowed",
        "ck_ideas_input_decision_allowed",
        "ck_ideas_processing_status_allowed",
        "ck_ideas_retry_count_range",
    }
    idea_columns = {column["name"] for column in inspector.get_columns("ideas")}
    assert {
        "input_decision",
        "decision_reason",
        "normalized_content",
        "dimension_scores",
        "evaluation_model",
        "evaluation_prompt_version",
        "evaluation_schema_version",
        "failure_stage",
        "failure_code",
        "completed_at",
    } <= idea_columns
    assert {index["name"] for index in inspector.get_indexes("ideas") if not index["unique"]} == {
        "ix_ideas_content_hash",
        "ix_ideas_processing_status_created_at",
        "ix_ideas_user_id_created_at",
    }
    idea_foreign_key = inspector.get_foreign_keys("ideas")[0]
    assert idea_foreign_key["name"] == "fk_ideas_user_id_users"
    assert idea_foreign_key["options"]["ondelete"] == "CASCADE"


def test_user_and_session_can_be_persisted(db_session: Session) -> None:
    user = _make_user()
    user.session = _make_session(user)
    db_session.add(user)
    db_session.commit()

    stored_session = db_session.scalar(select(UserSession))

    assert user.id == 1
    assert user.role == UserRole.USER.value
    assert user.status == UserStatus.ACTIVE.value
    assert user.created_at.tzinfo is not None
    assert stored_session is not None
    assert stored_session.user.username == "alice"
    assert stored_session.expires_at.utcoffset() == timedelta(0)


def test_duplicate_username_is_rejected(db_session: Session) -> None:
    db_session.add(_make_user())
    db_session.commit()
    db_session.add(_make_user())

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_duplicate_token_hash_is_rejected(db_session: Session) -> None:
    first_user = _make_user("alice")
    second_user = _make_user("bob")
    first_user.session = _make_session(first_user)
    second_user.session = _make_session(second_user)
    db_session.add_all([first_user, second_user])

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_duplicate_user_session_is_rejected(db_session: Session) -> None:
    user = _make_user()
    db_session.add(user)
    db_session.commit()
    db_session.add_all(
        [
            UserSession(
                token_hash="a" * 64,
                user_id=user.id,
                expires_at=datetime.now(UTC) + timedelta(days=3),
            ),
            UserSession(
                token_hash="b" * 64,
                user_id=user.id,
                expires_at=datetime.now(UTC) + timedelta(days=3),
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


@pytest.mark.parametrize(("field", "value"), [("role", "owner"), ("status", "blocked")])
def test_invalid_user_enum_value_is_rejected(
    db_session: Session,
    field: str,
    value: str,
) -> None:
    user = _make_user()
    setattr(user, field, value)
    db_session.add(user)

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_deleting_user_cascades_to_sessions(db_session: Session) -> None:
    user = _make_user()
    user.session = _make_session(user)
    db_session.add(user)
    db_session.commit()

    db_session.execute(delete(User).where(User.id == user.id))
    db_session.commit()

    assert db_session.scalar(select(UserSession)) is None


def test_user_and_idea_can_be_persisted(db_session: Session) -> None:
    user = _make_user()
    user.ideas.append(_make_idea(user))
    db_session.add(user)
    db_session.commit()

    stored_idea = db_session.scalar(select(Idea))

    assert stored_idea is not None
    assert stored_idea.internal_id == 1
    assert stored_idea.public_id.version == 4
    assert stored_idea.processing_status == IdeaProcessingStatus.PENDING.value
    assert stored_idea.retry_count == 0
    assert stored_idea.user.username == "alice"
    assert stored_idea.created_at.tzinfo is not None
    assert stored_idea.updated_at.tzinfo is not None


def test_duplicate_submission_key_for_same_user_is_rejected(db_session: Session) -> None:
    user = _make_user()
    submission_key = uuid4()
    first_idea = _make_idea(user, "第一个满足长度要求的点子内容")
    second_idea = _make_idea(user, "第二个满足长度要求的点子内容")
    first_idea.submission_key = submission_key
    second_idea.submission_key = submission_key
    db_session.add_all([user, first_idea, second_idea])

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_same_submission_key_is_allowed_for_different_users(db_session: Session) -> None:
    submission_key = uuid4()
    first_user = _make_user("alice")
    second_user = _make_user("bob")
    first_idea = _make_idea(first_user)
    second_idea = _make_idea(second_user)
    first_idea.submission_key = submission_key
    second_idea.submission_key = submission_key
    db_session.add_all([first_user, second_user, first_idea, second_idea])
    db_session.commit()

    assert len(list(db_session.scalars(select(Idea)))) == 2


@pytest.mark.parametrize(
    ("field", "value"),
    [("processing_status", "unknown"), ("retry_count", -1), ("retry_count", 4)],
)
def test_invalid_idea_state_is_rejected(
    db_session: Session,
    field: str,
    value: str | int,
) -> None:
    user = _make_user()
    idea = _make_idea(user)
    setattr(idea, field, value)
    db_session.add_all([user, idea])

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_deleting_user_cascades_to_ideas(db_session: Session) -> None:
    user = _make_user()
    user.ideas.append(_make_idea(user))
    db_session.add(user)
    db_session.commit()

    db_session.execute(delete(User).where(User.id == user.id))
    db_session.commit()

    assert db_session.scalar(select(Idea)) is None


def test_valid_ai_evaluation_can_be_persisted_and_revalidated(db_session: Session) -> None:
    user = _make_user()
    idea = _make_idea(user)
    output = make_evaluation_output()
    idea.processing_status = IdeaProcessingStatus.EMBEDDING.value
    idea.input_decision = InputDecision.ACCEPT.value
    idea.decision_reason = output.decision_reason
    idea.normalized_content = output.normalized_content().model_dump(mode="json")
    assert output.evaluation is not None
    idea.dimension_scores = output.evaluation.model_dump(mode="json")
    idea.evaluation_model = "fake-model"
    idea.evaluation_prompt_version = "evaluation-v1"
    idea.evaluation_schema_version = "evaluation-v1"
    db_session.add_all([user, idea])
    db_session.commit()

    stored_idea = db_session.scalar(select(Idea))

    assert stored_idea is not None
    assert NormalizedContent.model_validate_json(json.dumps(stored_idea.normalized_content))
    assert EvaluationScores.model_validate_json(json.dumps(stored_idea.dimension_scores))


@pytest.mark.parametrize(
    "invalid_state",
    [
        "invalid_decision",
        "failed_without_code",
        "failure_on_pending",
        "accept_without_scores",
        "clarify_with_scores",
    ],
)
def test_database_rejects_incomplete_ai_states(
    db_session: Session,
    invalid_state: str,
) -> None:
    user = _make_user()
    idea = _make_idea(user)
    output = make_evaluation_output()

    if invalid_state == "invalid_decision":
        idea.input_decision = "maybe"
    elif invalid_state == "failed_without_code":
        idea.processing_status = IdeaProcessingStatus.FAILED.value
    elif invalid_state == "failure_on_pending":
        idea.failure_stage = "evaluating"
        idea.failure_code = "provider_timeout"
    else:
        idea.processing_status = IdeaProcessingStatus.EMBEDDING.value
        idea.input_decision = (
            InputDecision.ACCEPT.value
            if invalid_state == "accept_without_scores"
            else InputDecision.CLARIFY.value
        )
        idea.decision_reason = output.decision_reason
        idea.normalized_content = output.normalized_content().model_dump(mode="json")
        idea.dimension_scores = (
            None
            if invalid_state == "accept_without_scores"
            else output.evaluation.model_dump(mode="json")  # type: ignore[union-attr]
        )
        idea.evaluation_model = "fake-model"
        idea.evaluation_prompt_version = "evaluation-v1"
        idea.evaluation_schema_version = "evaluation-v1"
    db_session.add_all([user, idea])

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

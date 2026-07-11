from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, delete, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from idea_bounty.models import User, UserRole, UserSession, UserStatus


def _make_user(username: str = "alice") -> User:
    return User(username=username, password_hash="argon2id-placeholder")


def _make_session(user: User, token_character: str = "a") -> UserSession:
    return UserSession(
        token_hash=token_character * 64,
        user=user,
        expires_at=datetime.now(UTC) + timedelta(days=3),
    )


def test_migration_creates_expected_schema(test_engine: Engine) -> None:
    inspector = inspect(test_engine)

    assert {"alembic_version", "sessions", "users"} <= set(inspector.get_table_names())
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

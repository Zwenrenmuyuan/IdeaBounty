from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from idea_bounty.config import Settings, get_settings
from idea_bounty.models import User, UserSession, UserStatus
from idea_bounty.services.auth import SESSION_COOKIE_NAME, SESSION_MAX_AGE

USERNAME = "alice_01"
PASSWORD = "correct horse battery staple"


def _register(client: TestClient, username: str = USERNAME, password: str = PASSWORD) -> str:
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": password},
    )
    assert response.status_code == 201
    token = response.cookies.get(SESSION_COOKIE_NAME)
    assert token is not None
    return token


def test_register_normalizes_username_and_stores_only_hashes(
    client: TestClient,
    db_session: Session,
) -> None:
    before_register = datetime.now(UTC)
    response = client.post(
        "/api/auth/register",
        json={"username": "  Alice_01  ", "password": PASSWORD},
    )
    after_register = datetime.now(UTC)

    assert response.status_code == 201
    assert response.json()["username"] == USERNAME
    assert response.json()["role"] == "user"
    assert response.json()["status"] == "active"
    assert "password" not in response.text

    token = response.cookies.get(SESSION_COOKIE_NAME)
    assert token is not None
    stored_user = db_session.scalar(select(User).where(User.username == USERNAME))
    stored_session = db_session.scalar(select(UserSession))
    assert stored_user is not None
    assert stored_session is not None
    assert stored_user.password_hash.startswith("$argon2id$")
    assert stored_user.password_hash != PASSWORD
    assert stored_session.token_hash == sha256(token.encode()).hexdigest()
    assert token not in stored_session.token_hash
    assert before_register + timedelta(days=3) <= stored_session.expires_at
    assert stored_session.expires_at <= after_register + timedelta(days=3)

    set_cookie = response.headers["set-cookie"]
    assert f"Max-Age={SESSION_MAX_AGE}" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Path=/" in set_cookie
    assert "SameSite=strict" in set_cookie
    assert "Secure" not in set_cookie


@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("ab", PASSWORD),
        ("alice!", PASSWORD),
        (USERNAME, "short"),
        (USERNAME, "x" * 129),
    ],
)
def test_register_rejects_invalid_credentials(
    client: TestClient,
    username: str,
    password: str,
) -> None:
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": password},
    )

    assert response.status_code == 422


def test_register_rejects_server_owned_fields(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register",
        json={"username": USERNAME, "password": PASSWORD, "role": "admin"},
    )

    assert response.status_code == 422


def test_duplicate_username_returns_conflict(client: TestClient) -> None:
    _register(client, "Alice_01")

    response = client.post(
        "/api/auth/register",
        json={"username": " alice_01 ", "password": PASSWORD},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "用户名已存在"}


def test_register_creates_an_authenticated_session(client: TestClient) -> None:
    _register(client)

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["username"] == USERNAME


def test_login_accepts_normalized_username(client: TestClient) -> None:
    _register(client)
    client.cookies.clear()

    response = client.post(
        "/api/auth/login",
        json={"username": " Alice_01 ", "password": PASSWORD},
    )

    assert response.status_code == 200
    assert response.cookies.get(SESSION_COOKIE_NAME) is not None


@pytest.mark.parametrize(
    ("username", "password"),
    [(USERNAME, "wrong password"), ("missing_user", PASSWORD)],
)
def test_login_failure_uses_a_generic_error(
    client: TestClient,
    username: str,
    password: str,
) -> None:
    _register(client)
    client.cookies.clear()

    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "用户名或密码错误"}
    assert response.cookies.get(SESSION_COOKIE_NAME) is None


def test_disabled_user_cannot_login_or_use_existing_session(
    client: TestClient,
    db_session: Session,
) -> None:
    _register(client)
    user = db_session.scalar(select(User).where(User.username == USERNAME))
    assert user is not None
    user.status = UserStatus.DISABLED.value
    db_session.commit()

    me_response = client.get("/api/auth/me")
    login_response = client.post(
        "/api/auth/login",
        json={"username": USERNAME, "password": PASSWORD},
    )

    assert me_response.status_code == 401
    assert login_response.status_code == 401
    assert login_response.json() == {"detail": "用户名或密码错误"}


def test_new_login_invalidates_the_previous_cookie(
    app: FastAPI,
    client: TestClient,
    db_session: Session,
) -> None:
    old_token = _register(client)
    login_response = client.post(
        "/api/auth/login",
        json={"username": USERNAME, "password": PASSWORD},
    )
    new_token = login_response.cookies.get(SESSION_COOKIE_NAME)

    assert login_response.status_code == 200
    assert new_token is not None
    assert new_token != old_token
    assert db_session.scalar(select(func.count()).select_from(UserSession)) == 1

    with TestClient(app) as old_client:
        old_client.cookies.set(SESSION_COOKIE_NAME, old_token)
        assert old_client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me").status_code == 200


@pytest.mark.parametrize("invalid_state", ["expired", "revoked"])
def test_invalid_session_is_rejected(
    client: TestClient,
    db_session: Session,
    invalid_state: str,
) -> None:
    _register(client)
    stored_session = db_session.scalar(select(UserSession))
    assert stored_session is not None
    if invalid_state == "expired":
        stored_session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    else:
        stored_session.revoked_at = datetime.now(UTC)
    db_session.commit()

    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json() == {"detail": "未登录或会话已失效"}


def test_logout_revokes_session_and_clears_cookie(
    client: TestClient,
    db_session: Session,
) -> None:
    _register(client)

    response = client.post("/api/auth/logout")
    repeated_response = client.post("/api/auth/logout")

    assert response.status_code == 204
    assert response.content == b""
    assert "content-type" not in response.headers
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert repeated_response.status_code == 204
    stored_session = db_session.scalar(select(UserSession))
    assert stored_session is not None
    db_session.refresh(stored_session)
    assert stored_session.revoked_at is not None
    assert client.get("/api/auth/me").status_code == 401


def test_logout_without_cookie_is_idempotent(client: TestClient) -> None:
    response = client.post("/api/auth/logout")

    assert response.status_code == 204
    assert response.content == b""


def test_production_cookie_is_secure(app: FastAPI, client: TestClient) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(app_env="production")

    response = client.post(
        "/api/auth/register",
        json={"username": USERNAME, "password": PASSWORD},
    )

    assert response.status_code == 201
    assert "Secure" in response.headers["set-cookie"]


def test_auth_routes_are_documented(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert {
        "/api/auth/register",
        "/api/auth/login",
        "/api/auth/me",
        "/api/auth/logout",
    } <= set(paths)

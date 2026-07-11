from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid1, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from idea_bounty.models import Idea, IdeaProcessingStatus, InputDecision
from tests.ai_fakes import FakeEvaluationProvider

PASSWORD = "correct horse battery staple"


def _register(client: TestClient, username: str) -> None:
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": PASSWORD},
    )
    assert response.status_code == 201


def _submit(
    client: TestClient,
    raw_content: str,
    submission_key: UUID | None = None,
) -> tuple[UUID, Response]:
    key = submission_key or uuid4()
    response = client.post(
        "/api/me/ideas",
        json={"submission_key": str(key), "raw_content": raw_content},
    )
    return key, response


def test_create_idea_preserves_raw_content_and_hides_internal_fields(
    client: TestClient,
    db_session: Session,
) -> None:
    _register(client, "alice")
    submission_key = uuid4()
    raw_content = "  我希望解决社区老人买菜不方便的问题。\n"

    response = client.post(
        "/api/me/ideas",
        json={"submission_key": str(submission_key), "raw_content": raw_content},
    )

    assert response.status_code == 201
    assert set(response.json()) == {
        "public_id",
        "submission_key",
        "raw_content",
        "generated_title",
        "processing_status",
        "input_decision",
        "retry_count",
        "created_at",
        "updated_at",
        "decision_reason",
        "clarification_question",
        "evaluation",
        "duplicate_result",
        "commercial_score",
        "base_amount",
        "duplicate_deduction",
        "final_amount",
        "admin_action",
        "payout_status",
        "payout",
    }
    assert response.json()["submission_key"] == str(submission_key)
    assert response.json()["raw_content"] == raw_content
    assert response.json()["processing_status"] == "completed"
    assert response.json()["input_decision"] == "accept"
    assert response.json()["evaluation"]["demand_breadth"]["score"] == 3
    assert response.json()["commercial_score"] == 60
    assert response.json()["base_amount"] == 18.37
    assert response.json()["duplicate_deduction"] == 0.0
    assert response.json()["final_amount"] == 18.37
    assert response.json()["retry_count"] == 0
    assert UUID(response.json()["public_id"]).version == 4

    stored_idea = db_session.scalar(select(Idea))
    assert stored_idea is not None
    assert stored_idea.raw_content == raw_content
    assert len(stored_idea.content_hash) == 64
    assert stored_idea.processing_status == IdeaProcessingStatus.COMPLETED.value
    assert stored_idea.embedding_model == "fake-embedding-model"
    assert stored_idea.embedding_dimensions == 1024
    assert stored_idea.embedding_input_version == "embedding-input-v1"
    assert stored_idea.input_decision == InputDecision.ACCEPT.value
    assert stored_idea.commercial_score == 60
    assert stored_idea.final_amount == Decimal("18.37")


@pytest.mark.parametrize("length", [8, 2000])
def test_create_idea_accepts_content_length_boundaries(
    client: TestClient,
    length: int,
) -> None:
    _register(client, "alice")

    _, response = _submit(client, "点" * length)

    assert response.status_code == 201


@pytest.mark.parametrize(
    ("submission_key", "raw_content"),
    [
        (str(uuid4()), "七" * 7),
        (str(uuid4()), "长" * 2001),
        (str(uuid4()), " " * 20),
        (str(uuid4()), "这是包含\x00空字符的投稿"),
        (str(uuid1()), "这是使用非四版 UUID 的投稿内容"),
        ("not-a-uuid", "这是使用非法 UUID 的投稿内容"),
    ],
)
def test_create_idea_rejects_invalid_input(
    client: TestClient,
    submission_key: str,
    raw_content: str,
) -> None:
    _register(client, "alice")

    response = client.post(
        "/api/me/ideas",
        json={"submission_key": submission_key, "raw_content": raw_content},
    )

    assert response.status_code == 422


@pytest.mark.parametrize("extra_field", [{"user_id": 999}, {"final_amount": 100}])
def test_create_idea_rejects_extra_fields(
    client: TestClient,
    extra_field: dict[str, int],
) -> None:
    _register(client, "alice")

    response = client.post(
        "/api/me/ideas",
        json={
            "submission_key": str(uuid4()),
            "raw_content": "这是字段完整且长度足够的投稿内容",
            **extra_field,
        },
    )

    assert response.status_code == 422


def test_content_hash_normalizes_unicode_case_and_whitespace(
    client: TestClient,
    db_session: Session,
) -> None:
    _register(client, "alice")
    first_key, first_response = _submit(client, "ＡＢＣ   这是一个测试痛点")
    second_key, second_response = _submit(client, "abc\n这是一个测试痛点")
    _, different_response = _submit(client, "abc 这是另一个测试痛点")

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert different_response.status_code == 201
    first_idea = db_session.scalar(select(Idea).where(Idea.submission_key == first_key))
    second_idea = db_session.scalar(select(Idea).where(Idea.submission_key == second_key))
    ideas = list(db_session.scalars(select(Idea).order_by(Idea.internal_id)))
    assert first_idea is not None
    assert second_idea is not None
    assert first_idea.content_hash == second_idea.content_hash
    assert ideas[2].content_hash != first_idea.content_hash


def test_identical_request_returns_existing_idea(
    client: TestClient,
    db_session: Session,
    evaluation_provider: FakeEvaluationProvider,
) -> None:
    _register(client, "alice")
    submission_key = uuid4()
    raw_content = "这是用于验证幂等重放的点子内容"

    _, first_response = _submit(client, raw_content, submission_key)
    _, replay_response = _submit(client, raw_content, submission_key)

    assert first_response.status_code == 201
    assert replay_response.status_code == 200
    assert replay_response.json()["public_id"] == first_response.json()["public_id"]
    assert db_session.scalar(select(func.count()).select_from(Idea)) == 1
    assert evaluation_provider.call_count == 1


def test_reused_submission_key_with_different_content_returns_conflict(
    client: TestClient,
) -> None:
    _register(client, "alice")
    submission_key = uuid4()
    _submit(client, "ＡＢＣ  这是用于验证幂等冲突的点子", submission_key)

    _, response = _submit(client, "abc\n这是用于验证幂等冲突的点子", submission_key)

    assert response.status_code == 409
    assert response.json() == {"detail": "submission_key 已被其他内容使用"}


def test_different_users_can_reuse_submission_key(
    app: FastAPI,
    client: TestClient,
    db_session: Session,
) -> None:
    submission_key = uuid4()
    _register(client, "alice")
    _, first_response = _submit(client, "这是 Alice 提交的点子内容", submission_key)

    with TestClient(app) as second_client:
        _register(second_client, "bob")
        _, second_response = _submit(second_client, "这是 Bob 提交的点子内容", submission_key)

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert first_response.json()["public_id"] != second_response.json()["public_id"]
    assert db_session.scalar(select(func.count()).select_from(Idea)) == 2


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        (
            "post",
            "/api/me/ideas",
            {"submission_key": str(uuid4()), "raw_content": "这是未登录用户的投稿内容"},
        ),
        ("get", "/api/me/ideas", None),
        ("get", f"/api/me/ideas/{uuid4()}", None),
    ],
)
def test_idea_routes_require_authentication(
    client: TestClient,
    method: str,
    path: str,
    json_body: dict[str, str] | None,
) -> None:
    response = client.request(method, path, json=json_body)

    assert response.status_code == 401


def test_list_ideas_is_paginated_and_stably_ordered(client: TestClient) -> None:
    _register(client, "alice")
    public_ids = []
    for index in range(3):
        _, response = _submit(client, f"这是第 {index} 条满足长度要求的点子内容")
        public_ids.append(response.json()["public_id"])

    response = client.get("/api/me/ideas", params={"limit": 1, "offset": 1})

    assert response.status_code == 200
    assert response.json()["total"] == 3
    assert response.json()["limit"] == 1
    assert response.json()["offset"] == 1
    assert [item["public_id"] for item in response.json()["items"]] == [public_ids[1]]


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
def test_list_ideas_rejects_invalid_pagination(
    client: TestClient,
    params: dict[str, int],
) -> None:
    _register(client, "alice")

    response = client.get("/api/me/ideas", params=params)

    assert response.status_code == 422


def test_user_cannot_list_or_get_another_users_idea(
    app: FastAPI,
    client: TestClient,
) -> None:
    _register(client, "alice")
    _, create_response = _submit(client, "这是 Alice 私有的点子内容")
    public_id = create_response.json()["public_id"]

    with TestClient(app) as second_client:
        _register(second_client, "bob")
        list_response = second_client.get("/api/me/ideas")
        detail_response = second_client.get(f"/api/me/ideas/{public_id}")

    assert list_response.status_code == 200
    assert list_response.json()["items"] == []
    assert list_response.json()["total"] == 0
    assert detail_response.status_code == 404
    assert detail_response.json() == {"detail": "点子不存在"}


def test_get_unknown_idea_returns_not_found(client: TestClient) -> None:
    _register(client, "alice")

    response = client.get(f"/api/me/ideas/{uuid4()}")

    assert response.status_code == 404


def test_get_owned_idea_returns_detail(client: TestClient) -> None:
    _register(client, "alice")
    _, create_response = _submit(client, "这是当前用户可以查看详情的点子")

    response = client.get(f"/api/me/ideas/{create_response.json()['public_id']}")

    assert response.status_code == 200
    assert response.json() == create_response.json()


def test_idea_routes_are_documented(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    create_responses = paths["/api/me/ideas"]["post"]["responses"]
    assert {"200", "201", "409", "422"} <= set(create_responses)
    assert "get" in paths["/api/me/ideas"]
    assert "get" in paths["/api/me/ideas/{public_id}"]
    assert "post" in paths["/api/me/ideas/{public_id}/retry"]

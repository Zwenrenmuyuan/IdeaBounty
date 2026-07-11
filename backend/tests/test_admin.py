from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from idea_bounty.models import Idea, SimulatedPayout
from idea_bounty.services.admin import promote_user_to_admin
from tests.ai_fakes import FakeEvaluationProvider, make_evaluation_output

PASSWORD = "correct horse battery staple"


def register(client: TestClient, username: str = "admin") -> None:
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": PASSWORD},
    )
    assert response.status_code == 201


def submit(client: TestClient, content: str = "社区老人行动不便时买菜很困难") -> str:
    response = client.post(
        "/api/me/ideas",
        json={"submission_key": str(uuid4()), "raw_content": content},
    )
    assert response.status_code == 201
    return str(response.json()["public_id"])


def make_admin(client: TestClient, db_session: Session) -> None:
    register(client)
    assert promote_user_to_admin(db_session, "admin")


def test_regular_user_cannot_access_admin_api(client: TestClient) -> None:
    register(client, "alice")

    for path in ("/api/admin/summary", "/api/admin/ideas"):
        response = client.get(path)
        assert response.status_code == 403
        assert response.json() == {"detail": "需要管理员权限"}


def test_confirm_creates_one_simulated_payout_and_locks_result(
    client: TestClient,
    db_session: Session,
) -> None:
    make_admin(client, db_session)
    public_id = submit(client)

    response = client.post(
        f"/api/admin/ideas/{public_id}/process",
        json={"action": "confirmed"},
    )
    repeated = client.post(
        f"/api/admin/ideas/{public_id}/process",
        json={"action": "confirmed"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["idea"]["admin_action"] == "confirmed"
    assert body["idea"]["payout_status"] == "confirmed"
    assert body["idea"]["payout"]["amount"] == 18.37
    assert body["idea"]["payout"]["reference"].startswith("SIM-")
    owner_detail = client.get(f"/api/me/ideas/{public_id}")
    assert owner_detail.json()["payout_status"] == "confirmed"
    assert owner_detail.json()["payout"] == body["idea"]["payout"]
    assert repeated.status_code == 409
    assert db_session.scalar(select(func.count()).select_from(SimulatedPayout)) == 1


def test_adjust_updates_final_amount_and_uses_adjusted_payout(
    client: TestClient,
    db_session: Session,
) -> None:
    make_admin(client, db_session)
    public_id = submit(client)

    response = client.post(
        f"/api/admin/ideas/{public_id}/process",
        json={"action": "adjusted", "amount": 25.5, "reason": "人工复核后调整"},
    )

    assert response.status_code == 200
    assert response.json()["idea"]["final_amount"] == 25.5
    assert response.json()["idea"]["payout"]["amount"] == 25.5
    idea = db_session.scalar(select(Idea))
    assert idea is not None
    assert idea.base_amount == Decimal("18.37")
    assert idea.duplicate_deduction == Decimal("0.00")
    assert idea.admin_amount == Decimal("25.50")


def test_reject_sets_zero_without_payout(
    client: TestClient,
    db_session: Session,
) -> None:
    make_admin(client, db_session)
    public_id = submit(client)

    response = client.post(
        f"/api/admin/ideas/{public_id}/process",
        json={"action": "rejected", "reason": "内容不适合收录"},
    )

    assert response.status_code == 200
    assert response.json()["idea"]["final_amount"] == 0.0
    assert response.json()["idea"]["payout_status"] == "not_applicable"
    assert response.json()["idea"]["payout"] is None
    assert db_session.scalar(select(SimulatedPayout)) is None


def test_adjust_to_zero_does_not_create_payout(
    client: TestClient,
    db_session: Session,
) -> None:
    make_admin(client, db_session)
    public_id = submit(client)

    response = client.post(
        f"/api/admin/ideas/{public_id}/process",
        json={"action": "adjusted", "amount": 0, "reason": "暂不奖励"},
    )

    assert response.status_code == 200
    assert response.json()["idea"]["payout_status"] == "not_applicable"
    assert response.json()["idea"]["payout"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "confirmed", "amount": 10},
        {"action": "adjusted", "amount": 10},
        {"action": "adjusted", "reason": "缺少金额"},
        {"action": "rejected"},
        {"action": "adjusted", "amount": 101, "reason": "金额越界"},
    ],
)
def test_process_request_rejects_invalid_action_fields(
    client: TestClient,
    db_session: Session,
    payload: dict[str, object],
) -> None:
    make_admin(client, db_session)

    response = client.post(f"/api/admin/ideas/{uuid4()}/process", json=payload)

    assert response.status_code == 422


def test_incomplete_idea_cannot_be_processed(
    client: TestClient,
    db_session: Session,
    evaluation_provider: FakeEvaluationProvider,
) -> None:
    evaluation_provider.outcomes = [make_evaluation_output("clarify")]
    make_admin(client, db_session)
    public_id = submit(client, "我有一个还没有描述清楚的生活问题")

    response = client.post(
        f"/api/admin/ideas/{public_id}/process",
        json={"action": "confirmed"},
    )

    assert response.status_code == 409


def test_admin_list_detail_and_summary(
    client: TestClient,
    db_session: Session,
) -> None:
    make_admin(client, db_session)
    public_id = submit(client)
    client.post(f"/api/admin/ideas/{public_id}/process", json={"action": "confirmed"})

    list_response = client.get("/api/admin/ideas")
    detail_response = client.get(f"/api/admin/ideas/{public_id}")
    summary_response = client.get("/api/admin/summary")

    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["username"] == "admin"
    assert detail_response.status_code == 200
    assert detail_response.json()["idea"]["raw_content"]
    assert summary_response.json() == {
        "total_submissions": 1,
        "completed_accepts": 1,
        "duplicate_count": 0,
        "estimated_total": 18.37,
        "confirmed_payout_count": 1,
        "simulated_payout_total": 18.37,
    }


def test_unknown_admin_idea_returns_not_found(
    client: TestClient,
    db_session: Session,
) -> None:
    make_admin(client, db_session)

    assert client.get(f"/api/admin/ideas/{uuid4()}").status_code == 404


def test_admin_routes_are_documented(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert "/api/admin/summary" in paths
    assert "/api/admin/ideas" in paths
    assert "/api/admin/ideas/{public_id}" in paths
    assert "/api/admin/ideas/{public_id}/process" in paths

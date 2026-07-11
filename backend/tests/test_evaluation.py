from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from idea_bounty.ai import EvaluationProviderError
from idea_bounty.models import (
    FailureCode,
    Idea,
    IdeaProcessingStatus,
    InputDecision,
    ManipulationSignal,
)
from idea_bounty.services.evaluation import process_pending_evaluation
from idea_bounty.services.idea import create_or_get_idea
from tests.ai_fakes import FakeEvaluationProvider, make_evaluation_output

PASSWORD = "correct horse battery staple"


def register(client: TestClient, username: str = "alice") -> None:
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": PASSWORD},
    )
    assert response.status_code == 201


def submit(client: TestClient, raw_content: str = "社区老人行动不便时买菜很困难") -> Response:
    return client.post(
        "/api/me/ideas",
        json={"submission_key": str(uuid4()), "raw_content": raw_content},
    )


@pytest.mark.parametrize(
    ("decision", "expected_status"),
    [
        ("accept", IdeaProcessingStatus.EMBEDDING.value),
        ("clarify", IdeaProcessingStatus.COMPLETED.value),
        ("reject", IdeaProcessingStatus.COMPLETED.value),
    ],
)
def test_evaluation_decision_advances_expected_state(
    client: TestClient,
    db_session: Session,
    evaluation_provider: FakeEvaluationProvider,
    decision: str,
    expected_status: str,
) -> None:
    evaluation_provider.outcomes = [make_evaluation_output(decision)]
    register(client)

    response = submit(client)

    assert response.status_code == 201
    assert response.json()["processing_status"] == expected_status
    assert response.json()["input_decision"] == decision
    stored_idea = db_session.scalar(select(Idea))
    assert stored_idea is not None
    assert stored_idea.input_decision == decision
    assert stored_idea.evaluation_model == "fake-evaluation-model"
    assert stored_idea.evaluation_prompt_version == "evaluation-v1"
    assert stored_idea.evaluation_schema_version == "evaluation-v1"
    assert stored_idea.normalized_content is not None
    if decision == InputDecision.ACCEPT.value:
        assert response.json()["evaluation"] is not None
        assert stored_idea.dimension_scores is not None
        assert stored_idea.completed_at is None
    else:
        assert response.json()["evaluation"] is None
        assert stored_idea.dimension_scores is None
        assert stored_idea.completed_at is not None


def test_list_returns_summary_while_detail_hides_internal_ai_fields(
    client: TestClient,
    evaluation_provider: FakeEvaluationProvider,
) -> None:
    output = make_evaluation_output()
    output.unsupported_claims.append("百亿市场")
    output.manipulation_signals.append(ManipulationSignal.PROMPT_INJECTION)
    evaluation_provider.outcomes = [output]
    register(client)
    create_response = submit(client)
    public_id = create_response.json()["public_id"]

    list_response = client.get("/api/me/ideas")
    detail_response = client.get(f"/api/me/ideas/{public_id}")

    assert set(list_response.json()["items"][0]) == {
        "public_id",
        "submission_key",
        "raw_content",
        "generated_title",
        "processing_status",
        "input_decision",
        "retry_count",
        "created_at",
        "updated_at",
    }
    detail_body = detail_response.json()
    assert detail_body["decision_reason"]
    assert detail_body["evaluation"]
    for internal_field in {
        "normalized_content",
        "unsupported_claims",
        "manipulation_signals",
        "evaluation_model",
        "failure_stage",
        "failure_code",
        "internal_id",
        "user_id",
        "content_hash",
    }:
        assert internal_field not in detail_body


def test_provider_failure_keeps_created_idea_with_safe_failure_state(
    client: TestClient,
    db_session: Session,
    evaluation_provider: FakeEvaluationProvider,
) -> None:
    evaluation_provider.outcomes = [
        EvaluationProviderError(
            FailureCode.PROVIDER_TIMEOUT,
            "包含服务商内部信息的错误",
            retryable=True,
        )
    ]
    register(client)

    response = submit(client)

    assert response.status_code == 201
    assert response.json()["processing_status"] == "failed"
    assert response.json()["input_decision"] is None
    assert "failure_code" not in response.json()
    stored_idea = db_session.scalar(select(Idea))
    assert stored_idea is not None
    assert stored_idea.failure_stage == "evaluating"
    assert stored_idea.failure_code == FailureCode.PROVIDER_TIMEOUT.value
    assert stored_idea.normalized_content is None


def test_external_call_observes_committed_evaluating_state(
    client: TestClient,
    test_engine: Engine,
    evaluation_provider: FakeEvaluationProvider,
) -> None:
    observed_statuses: list[str] = []

    def observe_status() -> None:
        with Session(test_engine) as separate_session:
            idea = separate_session.scalar(select(Idea))
            assert idea is not None
            observed_statuses.append(idea.processing_status)

    evaluation_provider.on_evaluate = observe_status
    register(client)

    response = submit(client)

    assert response.status_code == 201
    assert observed_statuses == [IdeaProcessingStatus.EVALUATING.value]


def test_user_can_retry_failed_evaluation(
    client: TestClient,
    evaluation_provider: FakeEvaluationProvider,
) -> None:
    evaluation_provider.outcomes = [
        EvaluationProviderError(
            FailureCode.PROVIDER_TIMEOUT,
            "第一次失败",
            retryable=True,
        ),
        make_evaluation_output(),
    ]
    register(client)
    create_response = submit(client)

    retry_response = client.post(f"/api/me/ideas/{create_response.json()['public_id']}/retry")

    assert create_response.json()["processing_status"] == "failed"
    assert retry_response.status_code == 200
    assert retry_response.json()["processing_status"] == "embedding"
    assert retry_response.json()["retry_count"] == 1
    assert evaluation_provider.call_count == 2


def test_retry_rejects_non_failed_and_exhausted_ideas(
    client: TestClient,
    db_session: Session,
) -> None:
    register(client)
    create_response = submit(client)
    public_id = create_response.json()["public_id"]

    state_response = client.post(f"/api/me/ideas/{public_id}/retry")
    idea = db_session.scalar(select(Idea))
    assert idea is not None
    idea.processing_status = IdeaProcessingStatus.FAILED.value
    idea.failure_stage = "evaluating"
    idea.failure_code = FailureCode.PROVIDER_TIMEOUT.value
    idea.retry_count = 3
    idea.input_decision = None
    idea.decision_reason = None
    idea.normalized_content = None
    idea.dimension_scores = None
    idea.evaluation_model = None
    idea.evaluation_prompt_version = None
    idea.evaluation_schema_version = None
    db_session.commit()
    limit_response = client.post(f"/api/me/ideas/{public_id}/retry")

    assert state_response.status_code == 409
    assert state_response.json() == {"detail": "当前状态不可重试"}
    assert limit_response.status_code == 409
    assert limit_response.json() == {"detail": "已达到最大重试次数"}


def test_retry_hides_another_users_idea(
    app: FastAPI,
    client: TestClient,
    evaluation_provider: FakeEvaluationProvider,
) -> None:
    evaluation_provider.outcomes = [
        EvaluationProviderError(
            FailureCode.PROVIDER_TIMEOUT,
            "第一次失败",
            retryable=True,
        )
    ]
    register(client, "alice")
    create_response = submit(client)

    with TestClient(app) as other_client:
        register(other_client, "bob")
        response = other_client.post(f"/api/me/ideas/{create_response.json()['public_id']}/retry")

    assert response.status_code == 404
    assert response.json() == {"detail": "点子不存在"}


def test_concurrent_replay_cannot_claim_evaluating_idea(
    db_session: Session,
    test_engine: Engine,
) -> None:
    from idea_bounty.models import User

    user = User(username="alice", password_hash="hash")
    db_session.add(user)
    db_session.commit()
    creation = create_or_get_idea(db_session, user.id, uuid4(), "并发重放不应重复调用模型")
    second_provider = FakeEvaluationProvider()

    def replay_during_call() -> None:
        with Session(test_engine, expire_on_commit=False) as separate_session:
            same_idea = separate_session.get(Idea, creation.idea.internal_id)
            assert same_idea is not None
            process_pending_evaluation(separate_session, same_idea, second_provider)

    first_provider = FakeEvaluationProvider(on_evaluate=replay_during_call)

    processed = process_pending_evaluation(db_session, creation.idea, first_provider)

    assert processed.processing_status == IdeaProcessingStatus.EMBEDDING.value
    assert first_provider.call_count == 1
    assert second_provider.call_count == 0

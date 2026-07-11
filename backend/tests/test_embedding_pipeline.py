from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from idea_bounty.embedding import EmbeddingProviderError
from idea_bounty.models import FailureCode, Idea, IdeaProcessingStatus, User
from idea_bounty.services.idea import create_or_get_idea
from idea_bounty.services.pipeline import process_idea_pipeline
from tests.ai_fakes import FakeEvaluationProvider, make_evaluation_output
from tests.embedding_fakes import FakeEmbeddingProvider, make_embedding_result

PASSWORD = "correct horse battery staple"


def register(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": PASSWORD},
    )
    assert response.status_code == 201


def submit(client: TestClient, submission_key: str | None = None) -> Response:
    return client.post(
        "/api/me/ideas",
        json={
            "submission_key": submission_key or str(uuid4()),
            "raw_content": "社区独居老人行动不便时很难购买日常食材",
        },
    )


def test_accept_calls_embedding_once_and_persists_vector_snapshot(
    client: TestClient,
    db_session: Session,
    embedding_provider: FakeEmbeddingProvider,
) -> None:
    register(client)

    response = submit(client)

    assert response.status_code == 201
    assert response.json()["processing_status"] == "checking_duplicate"
    assert embedding_provider.call_count == 1
    assert embedding_provider.texts == [
        "目标用户：社区独居老人\n"
        "核心痛点：行动不便时买菜困难\n"
        "发生场景：日常居家生活\n"
        "期望结果：更方便地获得日常食材"
    ]
    idea = db_session.scalar(select(Idea))
    assert idea is not None
    assert idea.embedding is not None
    assert len(idea.embedding) == 1024
    assert idea.embedding_model == "fake-embedding-model"
    assert idea.embedding_dimensions == 1024
    assert idea.embedding_input_version == "embedding-input-v1"


def test_clarify_and_reject_do_not_call_embedding(
    client: TestClient,
    evaluation_provider: FakeEvaluationProvider,
    embedding_provider: FakeEmbeddingProvider,
) -> None:
    evaluation_provider.outcomes = [
        make_evaluation_output("clarify"),
        make_evaluation_output("reject"),
    ]
    register(client)

    clarify_response = submit(client)
    reject_response = submit(client)

    assert clarify_response.json()["processing_status"] == "completed"
    assert reject_response.json()["processing_status"] == "completed"
    assert embedding_provider.call_count == 0


def test_embedding_failure_keeps_evaluation_and_safe_stage(
    client: TestClient,
    db_session: Session,
    embedding_provider: FakeEmbeddingProvider,
) -> None:
    embedding_provider.outcomes = [
        EmbeddingProviderError(
            FailureCode.PROVIDER_TIMEOUT,
            "不应暴露的服务商错误",
            retryable=True,
        )
    ]
    register(client)

    response = submit(client)

    assert response.status_code == 201
    assert response.json()["processing_status"] == "failed"
    assert response.json()["input_decision"] == "accept"
    assert "failure_code" not in response.json()
    idea = db_session.scalar(select(Idea))
    assert idea is not None
    assert idea.failure_stage == "embedding"
    assert idea.failure_code == "provider_timeout"
    assert idea.normalized_content is not None
    assert idea.dimension_scores is not None
    assert idea.embedding is None
    assert idea.embedding_model is None


def test_embedding_call_observes_committed_embedding_state(
    client: TestClient,
    test_engine: Engine,
    embedding_provider: FakeEmbeddingProvider,
) -> None:
    observed_statuses: list[str] = []

    def observe_status() -> None:
        with Session(test_engine) as separate_session:
            idea = separate_session.scalar(select(Idea))
            assert idea is not None
            observed_statuses.append(idea.processing_status)

    embedding_provider.on_embed = observe_status
    register(client)

    response = submit(client)

    assert response.status_code == 201
    assert observed_statuses == [IdeaProcessingStatus.EMBEDDING.value]


def test_idempotent_replay_does_not_repeat_embedding(
    client: TestClient,
    embedding_provider: FakeEmbeddingProvider,
) -> None:
    register(client)
    submission_key = str(uuid4())

    first_response = submit(client, submission_key)
    replay_response = submit(client, submission_key)

    assert first_response.status_code == 201
    assert replay_response.status_code == 200
    assert replay_response.json()["processing_status"] == "checking_duplicate"
    assert embedding_provider.call_count == 1


def test_concurrent_replay_during_embedding_does_not_call_second_provider(
    db_session: Session,
    test_engine: Engine,
) -> None:
    user = User(username="alice", password_hash="hash")
    db_session.add(user)
    db_session.commit()
    creation = create_or_get_idea(
        db_session,
        user.id,
        uuid4(),
        "并发重放不应该重复调用 Embedding 服务",
    )
    second_evaluation = FakeEvaluationProvider()
    second_embedding = FakeEmbeddingProvider()

    def replay_during_embedding() -> None:
        with Session(test_engine, expire_on_commit=False) as separate_session:
            same_idea = separate_session.get(Idea, creation.idea.internal_id)
            assert same_idea is not None
            process_idea_pipeline(
                separate_session,
                same_idea,
                second_evaluation,
                second_embedding,
            )

    first_embedding = FakeEmbeddingProvider(on_embed=replay_during_embedding)
    processed = process_idea_pipeline(
        db_session,
        creation.idea,
        FakeEvaluationProvider(),
        first_embedding,
    )

    assert processed.processing_status == IdeaProcessingStatus.CHECKING_DUPLICATE.value
    assert first_embedding.call_count == 1
    assert second_evaluation.call_count == 0
    assert second_embedding.call_count == 0


def test_retry_embedding_failure_does_not_repeat_evaluation(
    client: TestClient,
    evaluation_provider: FakeEvaluationProvider,
    embedding_provider: FakeEmbeddingProvider,
) -> None:
    embedding_provider.outcomes = [
        EmbeddingProviderError(
            FailureCode.PROVIDER_TIMEOUT,
            "第一次 Embedding 失败",
            retryable=True,
        ),
        make_embedding_result(),
    ]
    register(client)
    create_response = submit(client)

    retry_response = client.post(f"/api/me/ideas/{create_response.json()['public_id']}/retry")

    assert create_response.json()["processing_status"] == "failed"
    assert retry_response.status_code == 200
    assert retry_response.json()["processing_status"] == "checking_duplicate"
    assert retry_response.json()["retry_count"] == 1
    assert evaluation_provider.call_count == 1
    assert embedding_provider.call_count == 2

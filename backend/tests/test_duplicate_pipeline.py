from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import Engine, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from idea_bounty.ai import DuplicateProviderError
from idea_bounty.models import (
    ComparisonAspect,
    DuplicateVerdict,
    FailureCode,
    Idea,
    IdeaProcessingStatus,
    PainRelation,
    ScoreConfidence,
    SolutionRelation,
)
from idea_bounty.schemas.duplicate import DuplicateJudgmentOutput
from tests.ai_fakes import FakeEvaluationProvider
from tests.duplicate_fakes import FakeDuplicateProvider
from tests.embedding_fakes import FakeEmbeddingProvider

PASSWORD = "correct horse battery staple"


def register(client: TestClient, username: str = "alice") -> None:
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": PASSWORD},
    )
    assert response.status_code == 201


def submit(
    client: TestClient,
    raw_content: str,
    *,
    submission_key: str | None = None,
) -> Response:
    return client.post(
        "/api/me/ideas",
        json={
            "submission_key": submission_key or str(uuid4()),
            "raw_content": raw_content,
        },
    )


def judgment(
    verdict: DuplicateVerdict,
    *,
    matched_internal_id: int | None,
    confidence: ScoreConfidence = ScoreConfidence.HIGH,
) -> DuplicateJudgmentOutput:
    pain_relation = (
        PainRelation.DIFFERENT if verdict is DuplicateVerdict.NOVEL else PainRelation.SAME
    )
    solution_relation = (
        SolutionRelation.DIFFERENT
        if verdict in {DuplicateVerdict.RELATED, DuplicateVerdict.NOVEL}
        else SolutionRelation.NOT_APPLICABLE
    )
    return DuplicateJudgmentOutput.model_construct(
        pain_relation=pain_relation,
        solution_relation=solution_relation,
        verdict=verdict,
        matched_internal_id=matched_internal_id,
        same_aspects=(
            [ComparisonAspect.PAIN_POINT] if verdict is not DuplicateVerdict.NOVEL else []
        ),
        different_aspects=(
            [ComparisonAspect.PROPOSED_SOLUTION]
            if verdict is DuplicateVerdict.RELATED
            else ([ComparisonAspect.PAIN_POINT] if verdict is DuplicateVerdict.NOVEL else [])
        ),
        added_value="当前点子与历史候选的比较结果",
        confidence=confidence,
        reason="这是用于流水线测试的查重理由",
    )


def test_first_idea_without_candidates_completes_as_novel(
    client: TestClient,
    db_session: Session,
    duplicate_provider: FakeDuplicateProvider,
) -> None:
    register(client)

    response = submit(client, "社区独居老人行动不便时买菜很困难")

    assert response.status_code == 201
    assert response.json()["processing_status"] == "completed"
    assert response.json()["duplicate_result"] == {
        "verdict": "novel",
        "matched_public_id": None,
        "matched_idea_url": None,
        "same_aspects": [],
        "different_aspects": [],
        "reason": "未召回可比较的历史点子",
    }
    idea = db_session.scalar(select(Idea))
    assert idea is not None
    assert idea.duplicate_method == "no_candidates"
    assert idea.duplicate_confidence == "high"
    assert idea.commercial_score == 60
    assert idea.base_amount == Decimal("18.37")
    assert idea.duplicate_deduction == Decimal("0.00")
    assert idea.final_amount == Decimal("18.37")
    assert duplicate_provider.call_count == 0


def test_database_rejects_partial_duplicate_snapshot(
    client: TestClient,
    db_session: Session,
) -> None:
    register(client)
    submit(client, "社区老人行动不便时难以购买生活用品")
    idea = db_session.scalar(select(Idea))
    assert idea is not None
    idea.duplicate_confidence = None

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_database_rejects_inconsistent_bounty_snapshot(
    client: TestClient,
    db_session: Session,
) -> None:
    register(client)
    submit(client, "社区老人行动不便时难以购买生活用品")
    idea = db_session.scalar(select(Idea))
    assert idea is not None
    idea.final_amount = Decimal("99.00")

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_exact_hash_match_skips_llm_and_returns_public_match(
    client: TestClient,
    duplicate_provider: FakeDuplicateProvider,
) -> None:
    register(client)
    original = submit(client, "小型餐厅每天人工检查食材日期很耗时")

    duplicate = submit(client, "小型餐厅每天人工检查食材日期很耗时")

    assert duplicate.json()["duplicate_result"]["verdict"] == "duplicate"
    assert duplicate.json()["duplicate_result"]["matched_public_id"] == original.json()["public_id"]
    assert duplicate.json()["duplicate_result"]["matched_idea_url"].endswith("/summary")
    assert duplicate.json()["base_amount"] == 18.37
    assert duplicate.json()["duplicate_deduction"] == 18.37
    assert duplicate.json()["final_amount"] == 0.0
    assert duplicate_provider.call_count == 0


def test_matched_history_is_restricted_from_hard_delete(
    client: TestClient,
    db_session: Session,
) -> None:
    register(client)
    submit(client, "门店每天人工登记临期食材很容易发生遗漏")
    submit(client, "门店每天人工登记临期食材很容易发生遗漏")

    with pytest.raises(IntegrityError):
        db_session.execute(delete(Idea).where(Idea.internal_id == 1))
        db_session.commit()
    db_session.rollback()


def test_llm_result_is_saved_and_medium_duplicate_becomes_related(
    client: TestClient,
    db_session: Session,
    duplicate_provider: FakeDuplicateProvider,
) -> None:
    register(client)
    original = submit(client, "诊所预约患者经常爽约导致医生时间浪费")
    duplicate_provider.outcomes = [
        judgment(
            DuplicateVerdict.DUPLICATE,
            matched_internal_id=1,
            confidence=ScoreConfidence.MEDIUM,
        )
    ]

    response = submit(client, "门诊预约后病人不来造成号源空置和浪费")

    assert response.json()["processing_status"] == "completed"
    result = response.json()["duplicate_result"]
    assert result["verdict"] == "related"
    assert result["matched_public_id"] == original.json()["public_id"]
    assert result["same_aspects"] == ["pain_point"]
    idea = db_session.scalar(select(Idea).order_by(Idea.internal_id.desc()))
    assert idea is not None
    assert idea.duplicate_method == "llm_candidates"
    assert idea.ai_duplicate_verdict == "duplicate"
    assert idea.effective_duplicate_verdict == "related"
    assert idea.duplicate_model == "fake-duplicate-model"
    assert idea.duplicate_prompt_version == "duplicate-evaluation-v2"
    assert idea.duplicate_schema_version == "duplicate-evaluation-v2"
    assert idea.duplicate_comparison is not None
    assert "matched_internal_id" not in idea.duplicate_comparison
    assert idea.duplicate_deduction == Decimal("0.00")
    assert idea.final_amount == idea.base_amount


def test_duplicate_call_observes_committed_stage_and_replay_does_not_repeat(
    client: TestClient,
    test_engine: Engine,
    duplicate_provider: FakeDuplicateProvider,
) -> None:
    register(client)
    submit(client, "装修公司每周人工检查员工报销发票字段")
    observed_statuses: list[str] = []

    def observe_status() -> None:
        with Session(test_engine) as session:
            current = session.scalar(select(Idea).order_by(Idea.internal_id.desc()))
            assert current is not None
            observed_statuses.append(current.processing_status)

    duplicate_provider.on_judge = observe_status
    key = str(uuid4())
    first = submit(client, "财务每周核对报销票据抬头金额非常耗时", submission_key=key)
    replay = submit(client, "财务每周核对报销票据抬头金额非常耗时", submission_key=key)

    assert first.status_code == 201
    assert replay.status_code == 200
    assert observed_statuses == [IdeaProcessingStatus.CHECKING_DUPLICATE.value]
    assert duplicate_provider.call_count == 1


def test_duplicate_failure_retries_only_duplicate_stage(
    client: TestClient,
    db_session: Session,
    evaluation_provider: FakeEvaluationProvider,
    embedding_provider: FakeEmbeddingProvider,
    duplicate_provider: FakeDuplicateProvider,
) -> None:
    register(client)
    submit(client, "餐饮门店库存食材临期时经常无法及时发现")
    duplicate_provider.outcomes = [
        DuplicateProviderError(
            FailureCode.PROVIDER_TIMEOUT,
            "不应保存的服务商错误",
            retryable=True,
        ),
        judgment(DuplicateVerdict.NOVEL, matched_internal_id=None),
    ]
    failed = submit(client, "小餐馆每天盘点时容易遗漏快过期的食材")

    retry = client.post(f"/api/me/ideas/{failed.json()['public_id']}/retry")

    assert failed.json()["processing_status"] == "failed"
    assert retry.status_code == 200
    assert retry.json()["processing_status"] == "completed"
    assert retry.json()["retry_count"] == 1
    idea = db_session.scalar(select(Idea).order_by(Idea.internal_id.desc()))
    assert idea is not None
    assert idea.failure_stage is None
    assert evaluation_provider.call_count == 2
    assert embedding_provider.call_count == 2
    assert duplicate_provider.call_count == 2


def test_invalid_candidate_snapshot_fails_safely_without_calling_provider(
    client: TestClient,
    db_session: Session,
    duplicate_provider: FakeDuplicateProvider,
) -> None:
    register(client)
    candidate_response = submit(client, "社区团购负责人每天需要人工汇总居民订单")
    candidate = db_session.scalar(select(Idea))
    assert candidate is not None
    candidate.normalized_content = {"invalid": True}
    db_session.commit()

    response = submit(client, "小区团购订单依靠手工整理经常遗漏商品")

    assert response.json()["processing_status"] == "failed"
    failed = db_session.scalar(select(Idea).order_by(Idea.internal_id.desc()))
    assert failed is not None
    assert failed.failure_stage == "checking_duplicate"
    assert failed.failure_code == "invalid_ai_output"
    assert duplicate_provider.call_count == 0
    unavailable = client.get(f"/api/ideas/{candidate_response.json()['public_id']}/summary")
    assert unavailable.status_code == 404


def test_public_summary_requires_login_and_redacts_sensitive_fields(
    app: FastAPI,
    client: TestClient,
    db_session: Session,
) -> None:
    register(client)
    response = submit(client, "小型诊所需要减少患者预约后爽约的问题")
    idea = db_session.scalar(select(Idea))
    assert idea is not None
    assert idea.normalized_content is not None
    normalized_content = dict(idea.normalized_content)
    normalized_content["generated_title"] = "联系 13800138000 处理预约"
    normalized_content["target_audience"] = {
        "value": "联系人 test@example.com",
        "source": "explicit",
    }
    normalized_content["pain_point"] = {
        "value": "身份证 110101199001011234 暴露",
        "source": "explicit",
    }
    normalized_content["context"] = {
        "value": "北京市朝阳区建国路88号诊所",
        "source": "explicit",
    }
    idea.normalized_content = normalized_content
    db_session.commit()

    with TestClient(app) as anonymous:
        unauthenticated = anonymous.get(f"/api/ideas/{response.json()['public_id']}/summary")
    with TestClient(app) as other_user:
        register(other_user, "bob")
        summary = other_user.get(f"/api/ideas/{response.json()['public_id']}/summary")
        missing = other_user.get(f"/api/ideas/{uuid4()}/summary")

    assert unauthenticated.status_code == 401
    assert summary.status_code == 200
    assert missing.status_code == 404
    assert summary.json()["generated_title"] is None
    assert summary.json()["target_audience"] is None
    assert summary.json()["pain_point"] is None
    assert summary.json()["context"] is None
    assert "raw_content" not in summary.json()
    assert "user_id" not in summary.json()

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from idea_bounty.db.base import Base
from idea_bounty.models.enums import IdeaProcessingStatus

if TYPE_CHECKING:
    from idea_bounty.models.user import User


class Idea(Base):
    """用户提交并等待后续处理的点子。"""

    __tablename__ = "ideas"
    __table_args__ = (
        CheckConstraint(
            "processing_status IN "
            "('pending', 'evaluating', 'embedding', 'checking_duplicate', 'completed', 'failed')",
            name="processing_status_allowed",
        ),
        CheckConstraint("retry_count BETWEEN 0 AND 3", name="retry_count_range"),
        CheckConstraint(
            "input_decision IS NULL OR input_decision IN ('accept', 'clarify', 'reject')",
            name="input_decision_allowed",
        ),
        CheckConstraint(
            "failure_stage IS NULL OR failure_stage IN "
            "('evaluating', 'embedding', 'checking_duplicate')",
            name="failure_stage_allowed",
        ),
        CheckConstraint(
            "failure_code IS NULL OR failure_code IN "
            "('provider_config_error', 'provider_auth_error', 'json_mode_unsupported', "
            "'provider_timeout', 'provider_rate_limited', 'invalid_ai_response', "
            "'invalid_ai_output', 'embedding_dimension_mismatch', 'provider_error')",
            name="failure_code_allowed",
        ),
        CheckConstraint(
            "(failure_stage IS NULL) = (failure_code IS NULL)",
            name="failure_fields_together",
        ),
        CheckConstraint(
            "(processing_status = 'failed') = (failure_stage IS NOT NULL)",
            name="failure_matches_status",
        ),
        CheckConstraint(
            "((input_decision IS NULL AND decision_reason IS NULL "
            "AND normalized_content IS NULL AND dimension_scores IS NULL "
            "AND evaluation_model IS NULL AND evaluation_prompt_version IS NULL "
            "AND evaluation_schema_version IS NULL) OR "
            "(input_decision IS NOT NULL AND decision_reason IS NOT NULL "
            "AND normalized_content IS NOT NULL AND evaluation_model IS NOT NULL "
            "AND evaluation_prompt_version IS NOT NULL AND evaluation_schema_version IS NOT NULL "
            "AND ((input_decision = 'accept' AND dimension_scores IS NOT NULL) "
            "OR (input_decision IN ('clarify', 'reject') AND dimension_scores IS NULL))))",
            name="evaluation_result_complete",
        ),
        CheckConstraint(
            "(processing_status = 'completed') = (completed_at IS NOT NULL)",
            name="completed_at_matches_status",
        ),
        CheckConstraint(
            "((embedding IS NULL AND embedding_model IS NULL "
            "AND embedding_dimensions IS NULL AND embedding_input_version IS NULL) OR "
            "(embedding IS NOT NULL AND embedding_model IS NOT NULL "
            "AND embedding_dimensions IS NOT NULL AND embedding_input_version IS NOT NULL))",
            name="embedding_fields_together",
        ),
        CheckConstraint(
            "embedding_dimensions IS NULL OR embedding_dimensions = 1024",
            name="embedding_dimensions_fixed",
        ),
        CheckConstraint(
            "embedding IS NULL OR input_decision IS NOT DISTINCT FROM 'accept'",
            name="embedding_requires_accept",
        ),
        CheckConstraint(
            "processing_status <> 'checking_duplicate' OR embedding IS NOT NULL",
            name="checking_duplicate_requires_embedding",
        ),
        CheckConstraint(
            "duplicate_method IS NULL OR duplicate_method IN "
            "('exact_hash', 'no_candidates', 'llm_candidates')",
            name="duplicate_method_allowed",
        ),
        CheckConstraint(
            "ai_duplicate_verdict IS NULL OR ai_duplicate_verdict IN "
            "('duplicate', 'related', 'novel')",
            name="ai_duplicate_verdict_allowed",
        ),
        CheckConstraint(
            "effective_duplicate_verdict IS NULL OR effective_duplicate_verdict IN "
            "('duplicate', 'related', 'novel')",
            name="effective_duplicate_verdict_allowed",
        ),
        CheckConstraint(
            "duplicate_confidence IS NULL OR duplicate_confidence IN ('high', 'medium', 'low')",
            name="duplicate_confidence_allowed",
        ),
        CheckConstraint(
            "((duplicate_method IS NULL AND ai_duplicate_verdict IS NULL "
            "AND effective_duplicate_verdict IS NULL AND duplicate_confidence IS NULL "
            "AND matched_idea_id IS NULL AND duplicate_reason IS NULL "
            "AND duplicate_comparison IS NULL AND duplicate_model IS NULL "
            "AND duplicate_prompt_version IS NULL AND duplicate_schema_version IS NULL) OR "
            "(duplicate_method IS NOT NULL AND ai_duplicate_verdict IS NOT NULL "
            "AND effective_duplicate_verdict IS NOT NULL AND duplicate_confidence IS NOT NULL "
            "AND duplicate_reason IS NOT NULL))",
            name="duplicate_result_complete",
        ),
        CheckConstraint(
            "(duplicate_method IS NOT NULL) = "
            "(processing_status = 'completed' AND input_decision = 'accept')",
            name="duplicate_result_matches_completed_accept",
        ),
        CheckConstraint(
            "((effective_duplicate_verdict IN ('duplicate', 'related') "
            "AND matched_idea_id IS NOT NULL) OR "
            "(effective_duplicate_verdict = 'novel' AND matched_idea_id IS NULL) OR "
            "effective_duplicate_verdict IS NULL)",
            name="duplicate_match_required",
        ),
        CheckConstraint(
            "matched_idea_id IS NULL OR matched_idea_id < internal_id",
            name="matched_idea_is_older",
        ),
        CheckConstraint(
            "effective_duplicate_verdict IS NULL "
            "OR effective_duplicate_verdict = ai_duplicate_verdict "
            "OR (ai_duplicate_verdict = 'duplicate' "
            "AND duplicate_confidence IN ('medium', 'low') "
            "AND effective_duplicate_verdict = 'related')",
            name="effective_duplicate_verdict_policy",
        ),
        CheckConstraint(
            "duplicate_method <> 'exact_hash' OR "
            "(ai_duplicate_verdict = 'duplicate' "
            "AND effective_duplicate_verdict = 'duplicate' "
            "AND duplicate_confidence = 'high' AND matched_idea_id IS NOT NULL "
            "AND duplicate_comparison IS NULL AND duplicate_model IS NULL "
            "AND duplicate_prompt_version IS NULL AND duplicate_schema_version IS NULL)",
            name="exact_hash_result_shape",
        ),
        CheckConstraint(
            "duplicate_method <> 'no_candidates' OR "
            "(ai_duplicate_verdict = 'novel' AND effective_duplicate_verdict = 'novel' "
            "AND duplicate_confidence = 'high' AND matched_idea_id IS NULL "
            "AND duplicate_comparison IS NULL AND duplicate_model IS NULL "
            "AND duplicate_prompt_version IS NULL AND duplicate_schema_version IS NULL)",
            name="no_candidates_result_shape",
        ),
        CheckConstraint(
            "duplicate_method <> 'llm_candidates' OR "
            "(duplicate_comparison IS NOT NULL AND duplicate_model IS NOT NULL "
            "AND duplicate_prompt_version IS NOT NULL AND duplicate_schema_version IS NOT NULL)",
            name="llm_duplicate_result_shape",
        ),
        UniqueConstraint(
            "user_id",
            "submission_key",
            name="uq_ideas_user_id_submission_key",
        ),
        Index("ix_ideas_user_id_created_at", "user_id", "created_at"),
        Index(
            "ix_ideas_processing_status_created_at",
            "processing_status",
            "created_at",
        ),
        Index("ix_ideas_content_hash", "content_hash"),
        Index("ix_ideas_matched_idea_id", "matched_idea_id"),
    )

    internal_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    public_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        default=uuid4,
        unique=True,
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    submission_key: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    processing_status: Mapped[str] = mapped_column(
        String(32),
        default=IdeaProcessingStatus.PENDING.value,
        server_default=IdeaProcessingStatus.PENDING.value,
        nullable=False,
    )
    retry_count: Mapped[int] = mapped_column(
        SmallInteger,
        default=0,
        server_default="0",
        nullable=False,
    )
    input_decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_content: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=True),
        nullable=True,
    )
    dimension_scores: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=True),
        nullable=True,
    )
    evaluation_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    evaluation_prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    evaluation_schema_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(
        VECTOR(1024),
        nullable=True,
        deferred=True,
    )
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    embedding_dimensions: Mapped[int | None] = mapped_column(nullable=True)
    embedding_input_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    duplicate_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ai_duplicate_verdict: Mapped[str | None] = mapped_column(String(16), nullable=True)
    effective_duplicate_verdict: Mapped[str | None] = mapped_column(String(16), nullable=True)
    duplicate_confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    matched_idea_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("ideas.internal_id", ondelete="RESTRICT"),
        nullable=True,
    )
    duplicate_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    duplicate_comparison: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=True),
        nullable=True,
    )
    duplicate_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    duplicate_prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    duplicate_schema_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    failure_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="ideas")

from enum import StrEnum


class UserRole(StrEnum):
    """用户在系统中的权限角色。"""

    USER = "user"
    ADMIN = "admin"


class UserStatus(StrEnum):
    """用户账号当前是否允许使用。"""

    ACTIVE = "active"
    DISABLED = "disabled"


class IdeaProcessingStatus(StrEnum):
    """点子处理流水线当前所处的阶段。"""

    PENDING = "pending"
    EVALUATING = "evaluating"
    EMBEDDING = "embedding"
    CHECKING_DUPLICATE = "checking_duplicate"
    COMPLETED = "completed"
    FAILED = "failed"


class InputDecision(StrEnum):
    """AI 输入门禁结论。"""

    ACCEPT = "accept"
    CLARIFY = "clarify"
    REJECT = "reject"


class FailureStage(StrEnum):
    """点子处理失败时所在的流水线阶段。"""

    EVALUATING = "evaluating"
    EMBEDDING = "embedding"
    CHECKING_DUPLICATE = "checking_duplicate"


class FailureCode(StrEnum):
    """可以安全持久化和记录的失败分类。"""

    PROVIDER_CONFIG_ERROR = "provider_config_error"
    PROVIDER_AUTH_ERROR = "provider_auth_error"
    JSON_MODE_UNSUPPORTED = "json_mode_unsupported"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_RATE_LIMITED = "provider_rate_limited"
    INVALID_AI_RESPONSE = "invalid_ai_response"
    INVALID_AI_OUTPUT = "invalid_ai_output"
    EMBEDDING_DIMENSION_MISMATCH = "embedding_dimension_mismatch"
    PROVIDER_ERROR = "provider_error"


class InformationSource(StrEnum):
    """规范化字段的信息来源。"""

    EXPLICIT = "explicit"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


class ScoreConfidence(StrEnum):
    """模型对单个评分维度的置信度。"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EvidenceField(StrEnum):
    """评分理由允许引用的规范化字段。"""

    TARGET_AUDIENCE = "target_audience"
    PAIN_POINT = "pain_point"
    CONTEXT = "context"
    FREQUENCY_OR_SEVERITY = "frequency_or_severity"
    CURRENT_ALTERNATIVE = "current_alternative"
    DESIRED_OUTCOME = "desired_outcome"
    PROPOSED_SOLUTION = "proposed_solution"
    SOLUTION_MECHANISM = "solution_mechanism"
    VALUE_PROPOSITION = "value_proposition"


class ManipulationSignal(StrEnum):
    """用户试图影响模型判断的内部审计信号。"""

    PROMPT_INJECTION = "prompt_injection"
    SCORE_OR_AMOUNT_INSTRUCTION = "score_or_amount_instruction"
    ROLE_OR_SYSTEM_IMPERSONATION = "role_or_system_impersonation"
    IRRELEVANT_PADDING = "irrelevant_padding"
    SPAM_OR_GIBBERISH = "spam_or_gibberish"

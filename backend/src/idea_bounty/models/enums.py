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

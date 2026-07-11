from idea_bounty.models import InformationSource
from idea_bounty.schemas.ai import NormalizedContent, NormalizedField

EMBEDDING_INPUT_VERSION = "embedding-input-v1"


def _append_field(lines: list[str], label: str, field: NormalizedField) -> None:
    """只加入明确或低风险推断出的白名单字段。"""

    if field.source in {InformationSource.EXPLICIT, InformationSource.INFERRED} and field.value:
        lines.append(f"{label}：{field.value}")


def build_embedding_text(content: NormalizedContent) -> str:
    """按固定顺序构建不含宣传、指令和方案的中性向量文本。"""

    lines: list[str] = []
    _append_field(lines, "目标用户", content.target_audience)
    _append_field(lines, "核心痛点", content.pain_point)
    _append_field(lines, "发生场景", content.context)
    _append_field(lines, "期望结果", content.desired_outcome)
    return "\n".join(lines)

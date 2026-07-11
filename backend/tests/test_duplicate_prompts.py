from __future__ import annotations

import json

from idea_bounty.ai.duplicate_prompts import (
    DUPLICATE_PROMPT_VERSION,
    DUPLICATE_SCHEMA_VERSION,
    build_duplicate_payload,
)
from scripts.probe_duplicate_provider import PROBE_CASES


def test_duplicate_payload_contains_schema_matrix_and_allowed_ids() -> None:
    comparison = PROBE_CASES[0].comparison

    payload = build_duplicate_payload("test-model", comparison)

    assert payload["model"] == "test-model"
    assert payload["temperature"] == 0.2
    assert payload["response_format"] == {"type": "json_object"}
    system_prompt = payload["messages"][0]["content"]
    assert "痛点相同，双方都没有方案" in system_prompt
    assert "同一流程和根因" in system_prompt
    assert "不得编造候选 ID" in system_prompt
    assert "只有一方存在明确方案时" in system_prompt
    assert "101, 102" in system_prompt
    assert '"DuplicateVerdict"' in system_prompt

    user_data = json.loads(payload["messages"][1]["content"])
    assert user_data == comparison.model_dump(mode="json")
    serialized = json.dumps(user_data, ensure_ascii=False)
    for forbidden in (
        "raw_content",
        "user_id",
        "public_id",
        "cosine_similarity",
        "embedding",
        "dimension_scores",
        "unsupported_claims",
        "manipulation_signals",
    ):
        assert forbidden not in serialized


def test_duplicate_prompt_and_schema_versions_are_fixed() -> None:
    assert DUPLICATE_PROMPT_VERSION == "duplicate-evaluation-v1"
    assert DUPLICATE_SCHEMA_VERSION == "duplicate-evaluation-v1"

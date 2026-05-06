"""Shared fixtures for agent-replay tests.

A "transcript" is a list of (tool_name, args, expected_envelope_invariants).
We replay each step through the dispatcher and assert envelope invariants —
not exact equality, but the load-bearing fields (`ok`, `error.code`,
`error.next_action`, presence of `data_truncated`, etc.).

This catches behaviour drift caused by code changes — the same way unit tests
catch regressions, but at the agent-tool-call layer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def transcripts_dir() -> Path:
    return Path(__file__).parent / "transcripts"


@pytest.fixture
def fake_dispatcher_factory(tmp_path):
    """Return a factory that builds a dispatcher with all-fake repos. Same
    factory the integration test uses, so we share its plumbing."""
    from tests.integration.test_tool_dispatcher import _build_fake_dispatcher

    def factory():
        return _build_fake_dispatcher(tmp_path)

    return factory


def assert_envelope_invariants(envelope: dict, expected: dict) -> None:
    """Check the load-bearing fields of an envelope match expected.

    `expected` keys (all optional):
      ok: bool
      error_code: str
      next_action: str
      contains_data_truncated: bool
      data_type: 'list' | 'dict' | 'str' | 'null'
      data_min_len: int       (lists/strs)
    """
    if "ok" in expected:
        assert envelope.get("ok") is expected["ok"], (
            f"ok: expected {expected['ok']}, got {envelope.get('ok')}; envelope={envelope}"
        )
    if "error_code" in expected:
        err = envelope.get("error") or {}
        assert err.get("code") == expected["error_code"], (
            f"error.code: expected {expected['error_code']!r}, got {err.get('code')!r}"
        )
    if "next_action" in expected:
        err = envelope.get("error") or {}
        assert err.get("next_action") == expected["next_action"], (
            f"error.next_action: expected {expected['next_action']!r}, "
            f"got {err.get('next_action')!r}"
        )
    if expected.get("contains_data_truncated"):
        assert envelope.get("data_truncated") is True
    if "data_type" in expected:
        actual = envelope.get("data")
        type_map = {
            "list": list, "dict": dict, "str": str, "null": type(None),
        }
        assert isinstance(actual, type_map[expected["data_type"]]), (
            f"data type: expected {expected['data_type']}, got {type(actual).__name__}"
        )
    if "data_min_len" in expected:
        actual = envelope.get("data")
        assert hasattr(actual, "__len__"), f"data has no len(): {actual!r}"
        assert len(actual) >= expected["data_min_len"], (
            f"data_min_len: expected ≥ {expected['data_min_len']}, got {len(actual)}"
        )


def load_transcript(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))

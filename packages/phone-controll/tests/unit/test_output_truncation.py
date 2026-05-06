"""Output truncation behaviour for small-LLM context safety."""

from __future__ import annotations

from mcp_phone_controll.presentation.output_truncation import (
    DEFAULT_MAX_LIST_ITEMS,
    DEFAULT_MAX_STRING_BYTES,
    truncate_envelope,
)


def test_short_envelope_passes_through():
    env = {"ok": True, "data": "hello"}
    out = truncate_envelope(env)
    assert out["data"] == "hello"
    assert "data_truncated" not in out


def test_long_string_is_capped():
    big = "x" * (DEFAULT_MAX_STRING_BYTES + 1000)
    env = {"ok": True, "data": big}
    out = truncate_envelope(env)
    assert out["data_truncated"] is True
    assert "...<truncated" in out["data"]
    assert out["next_action"] == "fetch_full_artifact_if_needed"


def test_long_list_is_capped_with_sentinel():
    items = list(range(DEFAULT_MAX_LIST_ITEMS + 50))
    env = {"ok": True, "data": items}
    out = truncate_envelope(env)
    assert len(out["data"]) == DEFAULT_MAX_LIST_ITEMS + 1
    sentinel = out["data"][-1]
    assert sentinel["_truncated"] == 50
    assert sentinel["_total"] == DEFAULT_MAX_LIST_ITEMS + 50
    assert out["data_truncated"] is True


def test_nested_dict_string_capped():
    big = "y" * (DEFAULT_MAX_STRING_BYTES + 1000)
    env = {"ok": True, "data": {"path": "/short", "content": big}}
    out = truncate_envelope(env)
    assert out["data"]["path"] == "/short"
    assert "...<truncated" in out["data"]["content"]
    assert out["data_truncated"] is True


def test_error_details_also_truncated():
    big = "z" * (DEFAULT_MAX_STRING_BYTES + 100)
    env = {"ok": False, "error": {"code": "X", "message": "m", "details": {"stderr": big}}}
    out = truncate_envelope(env)
    assert out["data_truncated"] is True
    assert "...<truncated" in out["error"]["details"]["stderr"]


def test_next_action_not_overwritten_for_errors():
    env = {
        "ok": False,
        "error": {
            "code": "X",
            "message": "m",
            "next_action": "fix_arguments",
            "details": {"stderr": "x" * (DEFAULT_MAX_STRING_BYTES + 1)},
        },
    }
    out = truncate_envelope(env)
    assert out["error"]["next_action"] == "fix_arguments"
    # Top-level next_action only added on ok=True envelopes
    assert "next_action" not in out


def test_truncation_does_not_grow_output():
    """Repeated truncation never increases the byte size."""
    env = {"ok": True, "data": "x" * (DEFAULT_MAX_STRING_BYTES + 100)}
    once = truncate_envelope(env)
    twice = truncate_envelope(once)
    assert len(twice["data"]) <= len(once["data"])

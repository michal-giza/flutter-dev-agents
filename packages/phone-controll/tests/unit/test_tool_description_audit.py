"""Tool descriptions are precious context — keep BASIC ones tight.

Small (4B) models pay context cost in linear time per tool. The audit below
caps the BASIC tier at 35 words per description to leave headroom for the
small-LLM context window.
"""

from __future__ import annotations

from mcp_phone_controll.container import build_runtime
from mcp_phone_controll.domain.tool_levels import BASIC_TOOLS

_BASIC_WORD_LIMIT = 35
_HARD_WORD_LIMIT = 70


def _word_count(text: str) -> int:
    return len(text.split())


def test_basic_tool_descriptions_within_word_limit():
    _, dispatcher = build_runtime()
    by_name = {d.name: d for d in dispatcher.descriptors}
    too_long: list[str] = []
    for name in BASIC_TOOLS:
        descriptor = by_name.get(name)
        assert descriptor is not None, f"BASIC tool not registered: {name}"
        wc = _word_count(descriptor.description)
        if wc > _BASIC_WORD_LIMIT:
            too_long.append(f"{name} ({wc} words)")
    assert not too_long, (
        f"BASIC tool descriptions exceed {_BASIC_WORD_LIMIT} words: {too_long}"
    )


def test_no_tool_description_is_excessive():
    _, dispatcher = build_runtime()
    too_long: list[str] = []
    for descriptor in dispatcher.descriptors:
        wc = _word_count(descriptor.description)
        if wc > _HARD_WORD_LIMIT:
            too_long.append(f"{descriptor.name} ({wc} words)")
    assert not too_long, (
        f"Tool descriptions exceed hard limit of {_HARD_WORD_LIMIT} words: "
        f"{too_long}"
    )


def test_every_tool_has_a_description():
    _, dispatcher = build_runtime()
    missing = [
        d.name for d in dispatcher.descriptors if not d.description.strip()
    ]
    assert not missing, f"tools missing descriptions: {missing}"

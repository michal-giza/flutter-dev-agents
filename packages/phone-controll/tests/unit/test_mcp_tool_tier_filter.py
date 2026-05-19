"""MCP_TOOL_TIER env filter — hosts with tool-count ceilings (Cursor,
Claude Desktop UI) get a curated subset instead of the full 109-tool
surface.

Setting matters in production: Claude Desktop's Connectors UI showed
"no tools available" when our 109-tool list arrived (May 2026
incident). Setting `MCP_TOOL_TIER=basic` brings the surface to 24
tools — well under any practical host ceiling.

These tests pin the contract end-to-end + the failure modes:
  - default = no filtering
  - "basic" = exactly BASIC_TOOLS set
  - "intermediate" = BASIC + INTERMEDIATE
  - "all" / "expert" = no filtering
  - unknown value = fail-open (no filtering — a typo doesn't
    silently strip tools)
"""

from __future__ import annotations

from mcp_phone_controll.domain.tool_levels import (
    BASIC_TOOLS,
    INTERMEDIATE_TOOLS,
)
from mcp_phone_controll.presentation.mcp_server import _allowed_tool_names


def test_unset_returns_none_no_filtering(monkeypatch):
    monkeypatch.delenv("MCP_TOOL_TIER", raising=False)
    assert _allowed_tool_names(["a", "b", "c"]) is None


def test_empty_returns_none(monkeypatch):
    monkeypatch.setenv("MCP_TOOL_TIER", "")
    assert _allowed_tool_names(["a"]) is None


def test_expert_returns_none(monkeypatch):
    monkeypatch.setenv("MCP_TOOL_TIER", "expert")
    assert _allowed_tool_names(["a"]) is None


def test_all_returns_none(monkeypatch):
    monkeypatch.setenv("MCP_TOOL_TIER", "all")
    assert _allowed_tool_names(["a"]) is None


def test_basic_returns_basic_set(monkeypatch):
    monkeypatch.setenv("MCP_TOOL_TIER", "basic")
    result = _allowed_tool_names(list(BASIC_TOOLS))
    assert result == set(BASIC_TOOLS)


def test_intermediate_returns_basic_plus_intermediate(monkeypatch):
    monkeypatch.setenv("MCP_TOOL_TIER", "intermediate")
    result = _allowed_tool_names([])
    assert result == set(BASIC_TOOLS) | set(INTERMEDIATE_TOOLS)


def test_case_insensitive(monkeypatch):
    """Operators set `MCP_TOOL_TIER=Basic` or `BASIC` from terminal
    convenience — both should work without surprises."""
    monkeypatch.setenv("MCP_TOOL_TIER", "BASIC")
    assert _allowed_tool_names([]) == set(BASIC_TOOLS)


def test_unknown_value_fails_open_with_none(monkeypatch):
    """`MCP_TOOL_TIER=baisc` (typo) must NOT silently strip every
    tool — that's exactly the silent-failure mode users hate. Fail
    open so the typo is harmless instead of dangerous."""
    monkeypatch.setenv("MCP_TOOL_TIER", "baisc-typo")
    assert _allowed_tool_names([]) is None


def test_compress_png_lives_in_basic_tier():
    """Field incident, May 2026: an overnight bot grabbed screenshots
    via raw `adb exec-out screencap` (bypassing take_screenshot's
    1600px cap), accumulated 6 oversized PNGs, then crashed with
    "image exceeds 2000px dimension limit". `compress_png` is the
    escape hatch — must be on the BASIC tier so agents never get
    stuck holding a 2400px PNG with no way out."""
    assert "compress_png" in BASIC_TOOLS, (
        "compress_png must stay on BASIC so agents using raw adb "
        "screencap always have a remediation tool available without "
        "escalating to expert tier."
    )


def test_take_screenshot_is_also_in_basic_tier():
    """The preferred path (caps automatically). If an agent has both
    available, take_screenshot beats raw adb + compress_png."""
    assert "take_screenshot" in BASIC_TOOLS


def test_basic_subset_is_reasonable_for_host_ceilings():
    """Cursor caps at 40 tools; Claude Desktop's UI dropped 109.
    BASIC tier must stay well under 40 so we never trip that
    ceiling. Anchor the count so a future BASIC expansion that
    breaks this invariant fails CI loudly instead of silently."""
    assert len(BASIC_TOOLS) <= 30, (
        f"BASIC_TOOLS has {len(BASIC_TOOLS)} entries — risks host "
        "ceilings (Cursor=40, others undocumented). Keep BASIC lean."
    )


def test_intermediate_subset_stays_under_typical_ceiling():
    """Intermediate is allowed to grow more than BASIC but should
    still stay under what mainstream hosts accept."""
    total = len(set(BASIC_TOOLS) | set(INTERMEDIATE_TOOLS))
    # Cursor's 40 ceiling is the canary; warn if we cross it.
    assert total <= 60, (
        f"BASIC + INTERMEDIATE = {total} tools. Above 60 risks "
        "exceeding mainstream MCP-host tool-list limits."
    )

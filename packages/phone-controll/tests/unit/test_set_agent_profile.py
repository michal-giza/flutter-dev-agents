"""set_agent_profile — applies known model configs in one call."""

from __future__ import annotations

import pytest

from mcp_phone_controll.domain.result import Err
from mcp_phone_controll.domain.usecases.set_agent_profile import (
    PROFILES,
    SetAgentProfile,
    SetAgentProfileParams,
)
from mcp_phone_controll.presentation.middleware import AutoNarrateMiddleware


def test_profiles_cover_known_models():
    assert {"claude", "qwen2.5-7b", "qwen2.5-14b", "llava", "haiku", "default"} <= set(
        PROFILES
    )


def test_profile_settings_have_required_keys():
    for name, settings in PROFILES.items():
        assert "image_cap" in settings, f"{name} missing image_cap"
        assert "auto_narrate_every" in settings, name
        assert "strict_tools" in settings, name
        assert "reflexion_retries" in settings, name


@pytest.mark.asyncio
async def test_unknown_profile_rejected():
    uc = SetAgentProfile(middleware_provider=lambda: [], env_setter=lambda _k, _v: None)
    res = await uc.execute(SetAgentProfileParams(name="does-not-exist"))
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"
    assert "available" in res.failure.details


@pytest.mark.asyncio
async def test_qwen_profile_updates_live_middleware_and_env():
    narrate = AutoNarrateMiddleware(every=0)
    captured: dict[str, str] = {}
    uc = SetAgentProfile(
        middleware_provider=lambda: [narrate],
        env_setter=captured.__setitem__,
    )
    res = await uc.execute(SetAgentProfileParams(name="qwen2.5-7b"))
    assert res.is_ok
    # Live middleware was updated.
    assert narrate._every == 5
    # Env vars were set.
    assert captured["MCP_MAX_IMAGE_DIM"] == "896"
    assert captured["MCP_STRICT_TOOLS"] == "1"
    assert captured["MCP_REFLEXION_RETRIES"] == "2"
    assert res.value.profile == "qwen2.5-7b"


@pytest.mark.asyncio
async def test_claude_profile_disables_narrate_and_strict():
    narrate = AutoNarrateMiddleware(every=5)  # was 5; should become 0
    captured: dict[str, str] = {}
    uc = SetAgentProfile(
        middleware_provider=lambda: [narrate],
        env_setter=captured.__setitem__,
    )
    res = await uc.execute(SetAgentProfileParams(name="claude"))
    assert res.is_ok
    assert narrate._every == 0
    assert captured["MCP_STRICT_TOOLS"] == "0"
    assert captured["MCP_REFLEXION_RETRIES"] == "0"


@pytest.mark.asyncio
async def test_summary_string_human_readable():
    uc = SetAgentProfile(middleware_provider=lambda: [], env_setter=lambda _k, _v: None)
    res = await uc.execute(SetAgentProfileParams(name="qwen2.5-7b"))
    assert res.is_ok
    s = res.value.summary
    assert "qwen2.5-7b" in s
    assert "image_cap=896" in s
    assert "strict=True" in s

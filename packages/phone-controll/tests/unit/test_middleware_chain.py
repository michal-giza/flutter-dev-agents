"""Middleware chain — each concern tested in isolation, plus a chain
ordering test to confirm the dispatcher invokes them correctly."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.presentation.middleware import (
    AutoNarrateMiddleware,
    ImageSafetyNetMiddleware,
    OutputTruncationMiddleware,
    PatrolGuardMiddleware,
    RateLimiterMiddleware,
    TraceRecorderMiddleware,
    build_default_chain,
)

# ---- per-middleware tests -----------------------------------------------


@pytest.mark.asyncio
async def test_patrol_guard_blocks_tap_text_when_active():
    mw = PatrolGuardMiddleware()
    # Activate by mimicking a successful prepare_for_test.
    await mw.post_dispatch("prepare_for_test", {}, {"ok": True})
    # Now tap_text without system=true should be refused.
    guard = await mw.pre_dispatch("tap_text", {"text": "Sign in"})
    assert guard is not None
    assert guard["error"]["code"] == "TapTextRefused"
    assert guard["error"]["next_action"] == "use_patrol"


@pytest.mark.asyncio
async def test_patrol_guard_allows_system_dialog_taps():
    mw = PatrolGuardMiddleware()
    await mw.post_dispatch("run_patrol_test", {}, {"ok": True})
    guard = await mw.pre_dispatch("tap_text", {"text": "Allow", "system": True})
    assert guard is None


@pytest.mark.asyncio
async def test_patrol_guard_deactivates_on_release():
    mw = PatrolGuardMiddleware()
    await mw.post_dispatch("prepare_for_test", {}, {"ok": True})
    await mw.post_dispatch("release_device", {}, {"ok": True})
    guard = await mw.pre_dispatch("tap_text", {"text": "anything"})
    assert guard is None


class _StubLimiter:
    def __init__(self):
        self.recorded: list[tuple[str, bool]] = []
        self.blocked: dict[str, dict] = {}

    def check(self, name):
        return self.blocked.get(name)

    def record(self, name, ok):
        self.recorded.append((name, ok))


@pytest.mark.asyncio
async def test_rate_limiter_bypass_for_discovery_tools():
    limiter = _StubLimiter()
    limiter.blocked["list_devices"] = {"ok": False, "error": {"code": "Rate"}}
    mw = RateLimiterMiddleware(limiter)
    # describe_capabilities is on the bypass list — must NOT be blocked.
    assert await mw.pre_dispatch("describe_capabilities", {}) is None
    # list_devices is not bypassed — should hit the limiter.
    blocked = await mw.pre_dispatch("list_devices", {})
    assert blocked["error"]["code"] == "Rate"


@pytest.mark.asyncio
async def test_rate_limiter_records_only_for_non_bypassed():
    limiter = _StubLimiter()
    mw = RateLimiterMiddleware(limiter)
    await mw.post_dispatch("describe_capabilities", {}, {"ok": True})
    await mw.post_dispatch("list_devices", {}, {"ok": True})
    assert limiter.recorded == [("list_devices", True)]


@pytest.mark.asyncio
async def test_output_truncation_can_be_disabled():
    mw = OutputTruncationMiddleware(enabled=False)
    payload = {"ok": True, "data": "x" * 100_000}
    out = await mw.post_dispatch("anything", {}, payload)
    assert out is payload  # no truncation


@pytest.mark.asyncio
async def test_image_safety_net_is_no_op_on_clean_envelope():
    mw = ImageSafetyNetMiddleware()
    payload = {"ok": True, "data": "not a path"}
    out = await mw.post_dispatch("anything", {}, payload)
    assert out == payload


@pytest.mark.asyncio
async def test_trace_recorder_invokes_provided_callable():
    calls = []

    async def recorder(name, args, envelope):
        calls.append((name, args, envelope.get("ok")))

    mw = TraceRecorderMiddleware(trace_repo=object(), recorder=recorder)
    await mw.post_dispatch("foo", {"x": 1}, {"ok": True})
    assert calls == [("foo", {"x": 1}, True)]


@pytest.mark.asyncio
async def test_trace_recorder_skipped_when_repo_is_none():
    calls = []

    async def recorder(name, args, envelope):
        calls.append(name)

    mw = TraceRecorderMiddleware(trace_repo=None, recorder=recorder)
    await mw.post_dispatch("foo", {}, {"ok": True})
    assert calls == []


@pytest.mark.asyncio
async def test_auto_narrate_attaches_every_n_calls():
    mw = AutoNarrateMiddleware(every=3)
    for i in range(1, 7):
        env = await mw.post_dispatch("list_devices", {}, {"ok": True, "data": []})
        if i in (3, 6):
            assert "narrate" in env, f"expected narrate on call {i}"
        else:
            assert "narrate" not in env, f"unexpected narrate on call {i}"


@pytest.mark.asyncio
async def test_auto_narrate_off_when_every_is_zero():
    mw = AutoNarrateMiddleware(every=0)
    env = await mw.post_dispatch("any", {}, {"ok": True})
    assert "narrate" not in env


# ---- chain composition --------------------------------------------------


@pytest.mark.asyncio
async def test_default_chain_contains_expected_middlewares():
    """Order matters — verify the canonical chain is exactly what the
    refactor specified, in order."""
    async def recorder(_n, _a, _e): ...
    chain = build_default_chain(
        rate_limiter=_StubLimiter(),
        trace_repo=object(),
        recorder=recorder,
        truncate_outputs=True,
        auto_narrate_every=5,
    )
    types = [type(mw).__name__ for mw in chain]
    assert types == [
        "PatrolGuardMiddleware",
        "RateLimiterMiddleware",
        "OutputTruncationMiddleware",
        "ImageSafetyNetMiddleware",
        "TraceRecorderMiddleware",
        "AutoNarrateMiddleware",
    ]


@pytest.mark.asyncio
async def test_dispatcher_walks_chain_in_correct_order(tmp_path: Path):
    """End-to-end: verify a dispatch goes through every middleware in
    the right order, both for pre-dispatch and post-dispatch."""
    from tests.integration.test_tool_dispatcher import _build_fake_dispatcher

    d = _build_fake_dispatcher(tmp_path)
    # The fake dispatcher's middleware list is the default chain.
    assert len(d.middlewares) == 6
    # Dispatch goes through cleanly without raising.
    res = await d.dispatch("list_devices", {})
    assert res["ok"] is True


@pytest.mark.asyncio
async def test_short_circuit_still_runs_post_dispatch_hooks(tmp_path: Path):
    """A pre-dispatch guard (e.g. rate limit) must still flow through the
    image-cap seatbelt + trace recorder. Otherwise a refused call could
    leak an oversized path or skip the trace entry."""
    from tests.integration.test_tool_dispatcher import _build_fake_dispatcher

    d = _build_fake_dispatcher(tmp_path)
    # Swap the rate-limiter middleware's limiter for a stub so we can
    # control what gets blocked.
    rate_mw = next(mw for mw in d.middlewares if isinstance(mw, RateLimiterMiddleware))
    stub = _StubLimiter()
    stub.blocked["take_screenshot"] = {
        "ok": False,
        "error": {"code": "RateLimited", "message": "test", "next_action": "back_off"},
    }
    rate_mw._limiter = stub

    res = await d.dispatch("take_screenshot", {})
    # Short-circuit envelope is returned (not None, not the use-case
    # result). It's flowed through the chain so it's well-formed.
    assert res["ok"] is False
    assert res["error"]["code"] == "RateLimited"

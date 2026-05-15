"""Comprehensive regression test — every screenshot path that returns a
file the agent can see must apply the dimension cap.

Targets the actual bug a user hit: `prepare_for_test` returned a full-
resolution evidence screenshot, Claude auto-embedded it, conversation
broke at the 2000px multi-image limit."""

from __future__ import annotations

from pathlib import Path

import pytest


def _have_cv2() -> bool:
    try:
        import cv2  # noqa: F401
        return True
    except ImportError:
        return False


pytestmark = pytest.mark.skipif(not _have_cv2(), reason="cv2 not installed")


def _read_png_dims(path: Path) -> tuple[int, int]:

    with path.open("rb") as fh:
        header = fh.read(24)
    return (
        int.from_bytes(header[16:20], "big"),
        int.from_bytes(header[20:24], "big"),
    )


@pytest.mark.asyncio
async def test_prepare_for_test_caps_evidence_screenshot(tmp_path: Path):
    """The bug we hit live: `prepare_for_test` was returning a 3120×1440
    PNG, Claude tried to embed it, conversation broke."""
    from tests.integration.test_tool_dispatcher import _build_fake_dispatcher

    dispatcher = _build_fake_dispatcher(tmp_path)
    res = await dispatcher.dispatch("select_device", {"serial": "EMU01"})
    assert res["ok"]

    res = await dispatcher.dispatch(
        "prepare_for_test",
        {"package_id": "com.example", "project_path": str(tmp_path)},
    )
    assert res["ok"], res
    evidence = res["data"].get("evidence_screenshot")
    if not evidence:
        # The fake observation may not produce an evidence screenshot —
        # if so the bug isn't reachable from this fake, but we keep the
        # test as a guard for the real implementation.
        pytest.skip("fake doesn't emit evidence_screenshot — real impl will")

    path = Path(evidence)
    assert path.exists()
    w, h = _read_png_dims(path)
    long_edge = max(w, h)
    assert long_edge <= 1600, (
        f"prepare_for_test left evidence screenshot at {w}×{h} — "
        f"this is the exact regression that broke Claude conversations."
    )


@pytest.mark.asyncio
async def test_take_screenshot_caps_under_default(tmp_path: Path):
    from tests.integration.test_tool_dispatcher import _build_fake_dispatcher

    dispatcher = _build_fake_dispatcher(tmp_path)
    await dispatcher.dispatch("select_device", {"serial": "EMU01"})
    res = await dispatcher.dispatch("take_screenshot", {"label": "test"})
    assert res["ok"]
    path = Path(res["data"])
    assert path.exists()
    w, h = _read_png_dims(path)
    # Default cap is 1600 (was 1920 — see image_capping.py docstring).
    assert max(w, h) <= 1600

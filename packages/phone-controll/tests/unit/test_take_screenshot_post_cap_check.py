"""Defense-in-depth: TakeScreenshot verifies the cap actually ran.

The May 2026 incident: a real user kept hitting the 2000px API
limit despite the cap path being shipped, because the MCP
subprocess was stale and `cap_image_in_place` silently didn't run.
The dispatcher safety-net middleware should have caught it — but
if the middleware itself is from a stale subprocess, BOTH layers
are broken.

This third check sits INSIDE the use case where every screenshot
path must pass through. If the file on disk is over the 1900-px
hard ceiling after `cap_image_in_place` returns, return a
structured failure instead of the oversized path. The agent
gets `next_action="install_image_backend"` plus a hint pointing
at `mcp_ping` for diagnosis.

These tests pin the new contract.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

import pytest

from mcp_phone_controll.domain.entities import Artifact, Session
from mcp_phone_controll.domain.result import Err, ok
from mcp_phone_controll.domain.usecases.observation import (
    TakeScreenshot,
    TakeScreenshotParams,
)

# ---- minimal PNG writer (no PIL dep) ----------------------------------


def _write_png(path: Path, width: int, height: int) -> None:
    """Write a smallest-possible valid PNG of `width`x`height`. Pure
    stdlib so the test runs even if Pillow is unavailable in CI."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(
        b"IHDR",
        struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0),  # RGB
    )
    # IDAT — one row at a time, zero-filled
    row = b"\x00" + b"\x00\x00\x00" * width
    raw = row * height
    idat = chunk(b"IDAT", zlib.compress(raw))
    iend = chunk(b"IEND", b"")
    path.write_bytes(sig + ihdr + idat + iend)


# ---- fakes ------------------------------------------------------------


@dataclass
class _FakeSession:
    serial: str = "EMU01"


class _FakeState:
    """Mimics SessionStateRepository surface — `_helpers.resolve_serial`
    calls `get_selected_serial`. We just hand back the same serial."""

    def __init__(self, serial: str = "EMU01"):
        self._serial = serial

    async def get_selected_serial(self):
        return ok(self._serial)


class _FakeArtifacts:
    def __init__(self, tmp_path: Path):
        self._tmp = tmp_path
        self.registered: list[Artifact] = []

    async def allocate_path(self, kind: str, suffix: str, label: str | None):
        from mcp_phone_controll.domain.result import ok

        name = f"{label or 'shot'}{suffix}"
        return ok(self._tmp / name)

    async def register(self, artifact: Artifact):
        self.registered.append(artifact)

    async def current_session(self):
        from mcp_phone_controll.domain.result import ok

        return ok(Session(id="s1", root=self._tmp))


class _FakeObservation:
    """Writes a PNG of arbitrary dimensions to whatever path
    `screenshot()` is asked to write to. Used to simulate the stale-
    subprocess case: the on-device shot is 1080×2340 but no cap runs."""

    def __init__(self, width: int, height: int):
        self._w = width
        self._h = height

    async def screenshot(self, _serial: str, target_path: Path):
        _write_png(target_path, self._w, self._h)
        return ok(target_path)


# ---- tests ------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_path_when_screenshot_is_within_cap(tmp_path: Path):
    """Sanity: normal-sized screenshot passes the post-check and
    returns the path. We must not regress the happy path while
    adding defence."""
    uc = TakeScreenshot(
        observation=_FakeObservation(800, 1200),
        artifacts=_FakeArtifacts(tmp_path),
        state=_FakeState(),
    )
    res = await uc.execute(TakeScreenshotParams(label="ok"))
    assert res.is_ok
    assert res.value.exists()


@pytest.mark.asyncio
async def test_returns_structured_failure_when_post_cap_check_fails(
    tmp_path: Path, monkeypatch
):
    """The real-world failure mode: cap_image_in_place silently does
    nothing (stale subprocess / no backends), and a 1080×2340 file
    on disk would otherwise leak through and crash the conversation.

    Force the cap to be a no-op via monkeypatch; assert the use case
    returns Err with the structured next_action.
    """
    from mcp_phone_controll.data import image_capping

    # Make cap_image_in_place a no-op AS IMPORTED INTO observation.
    # We patch the cap module's symbol so the local-import inside
    # the use case picks up our fake.
    monkeypatch.setattr(image_capping, "cap_image_in_place", lambda *a, **k: False)
    # Also patch the alias if the use case imports it locally — the
    # `from ... import cap_image_in_place` inside execute() reads
    # from the module each call.

    uc = TakeScreenshot(
        observation=_FakeObservation(1080, 2340),  # over the 1900 ceiling
        artifacts=_FakeArtifacts(tmp_path),
        state=_FakeState(),
    )

    res = await uc.execute(TakeScreenshotParams(label="leaky"))

    assert isinstance(res, Err)
    assert res.failure.next_action == "install_image_backend"
    assert res.failure.details["width"] == 1080
    assert res.failure.details["height"] == 2340
    assert res.failure.details["max_allowed_px"] == 1900
    # Diagnostic hint mentions mcp_ping — operator's next step.
    assert "mcp_ping" in res.failure.message


@pytest.mark.asyncio
async def test_does_not_register_artifact_when_cap_check_fails(
    tmp_path: Path, monkeypatch
):
    """If the post-cap check fails, the file is NOT registered as an
    artifact — we don't want a poisoned reference in the session
    trace."""
    from mcp_phone_controll.data import image_capping

    monkeypatch.setattr(image_capping, "cap_image_in_place", lambda *a, **k: False)

    artifacts = _FakeArtifacts(tmp_path)
    uc = TakeScreenshot(
        observation=_FakeObservation(1080, 2340),
        artifacts=artifacts,
        state=_FakeState(),
    )
    res = await uc.execute(TakeScreenshotParams(label="leaky"))
    assert isinstance(res, Err)
    assert artifacts.registered == []


@pytest.mark.asyncio
async def test_within_cap_path_still_registers_artifact(tmp_path: Path):
    """The happy path must still register the artifact — otherwise
    session_summary loses the audit trail."""
    artifacts = _FakeArtifacts(tmp_path)
    uc = TakeScreenshot(
        observation=_FakeObservation(800, 1200),
        artifacts=artifacts,
        state=_FakeState(),
    )
    res = await uc.execute(TakeScreenshotParams(label="ok"))
    assert res.is_ok
    assert len(artifacts.registered) == 1
    assert artifacts.registered[0].label == "ok"

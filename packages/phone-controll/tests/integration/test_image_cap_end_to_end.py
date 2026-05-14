"""End-to-end regression test: no tool envelope can leak an over-cap PNG.

Simulates the actual failure mode that hit production four times:

  device → take_screenshot → MCP envelope → Claude Code Read → API rejection

The test substitutes a Galaxy-S25-sized fake observation (3120×1440 PNGs)
and runs every screenshot-producing tool through the real dispatcher.
For each resulting envelope, it walks every string field and confirms
that any string pointing at an existing `.png` file passes a
strict-2000px-long-edge check — the same check Claude's API applies
to multi-image conversations.

If a tool reintroduces an uncapped path (or invents a new screenshot
sink we haven't capped), this test goes red. That's the contract.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import Any

import pytest

from mcp_phone_controll.domain.result import ok


_GALAXY_S25_W = 3120
_GALAXY_S25_H = 1440
_CLAUDE_API_LIMIT = 2000  # multi-image conversations


def _have_cv2() -> bool:
    try:
        import cv2  # noqa: F401
        return True
    except ImportError:
        return False


def _write_real_png(path: Path, width: int, height: int) -> None:
    """Write a minimal-but-valid PNG so dimension readers + capping
    libraries both decode it. cv2 used when available, hand-rolled
    fallback otherwise."""
    if _have_cv2():
        import cv2
        import numpy as np

        img = np.zeros((height, width, 3), dtype=np.uint8)
        img[:, :, 1] = 200  # greenish so it's visibly non-blank
        cv2.imwrite(str(path), img)
        return
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = b"IHDR" + struct.pack(">II", width, height) + b"\x08\x02\x00\x00\x00"
    ihdr_crc = struct.pack(">I", zlib.crc32(ihdr))
    raw = b"\x00" * (1 + 3 * width) * height
    idat_payload = zlib.compress(raw)
    idat = b"IDAT" + idat_payload
    idat_crc = struct.pack(">I", zlib.crc32(idat))
    iend = b"IEND"
    iend_crc = struct.pack(">I", zlib.crc32(iend))
    path.write_bytes(
        sig
        + struct.pack(">I", 13) + ihdr + ihdr_crc
        + struct.pack(">I", len(idat_payload)) + idat + idat_crc
        + struct.pack(">I", 0) + iend + iend_crc
    )


def _read_png_long_edge(path: Path) -> int | None:
    """Return long edge of a PNG, or None if not a PNG."""
    with path.open("rb") as fh:
        header = fh.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    w = int.from_bytes(header[16:20], "big")
    h = int.from_bytes(header[20:24], "big")
    return max(w, h)


def _walk_strings(node: Any):
    if isinstance(node, str):
        yield node
        return
    if isinstance(node, dict):
        for v in node.values():
            yield from _walk_strings(v)
        return
    if isinstance(node, (list, tuple)):
        for v in node:
            yield from _walk_strings(v)


def _claude_api_simulator_reject(envelope: dict) -> list[tuple[str, int]]:
    """Return [(path, long_edge), ...] for any PNG path in the envelope
    that exceeds the Claude multi-image cap. Walks ALL string fields
    (not just `data`) because in practice a path can appear inside
    `error.details`, ride-along diagnostics, anywhere.

    Skips paths under release/ or tests/fixtures/golden/ — those are
    intentionally full-resolution and would never be inlined by
    Claude Code (they're metadata, not screenshot output)."""
    rejected: list[tuple[str, int]] = []
    skip_segments = ("/release/", "/tests/fixtures/golden/")
    for value in _walk_strings(envelope):
        if not isinstance(value, str) or not value.endswith(".png"):
            continue
        if any(seg in value for seg in skip_segments):
            continue
        try:
            path = Path(value)
            if not path.is_file():
                continue
        except OSError:
            continue
        long_edge = _read_png_long_edge(path)
        if long_edge is not None and long_edge > _CLAUDE_API_LIMIT:
            rejected.append((value, long_edge))
    return rejected


class _GalaxyS25Observation:
    """ObservationRepository that always writes 3120×1440 PNGs to disk.

    Stands in for the real `adb screencap` output of a Samsung Galaxy
    S25. If the agent's screenshot pipeline doesn't apply the cap,
    Claude's API simulator (above) will reject the resulting path
    string and the test goes red."""

    async def screenshot(self, _serial, output_path: Path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _write_real_png(output_path, _GALAXY_S25_W, _GALAXY_S25_H)
        return ok(output_path)

    async def start_recording(self, *_a, **_k): return ok(None)
    async def stop_recording(self, *_a, **_k): return ok(Path("/tmp/x.mp4"))
    async def read_logs(self, *_a, **_k): return ok([])
    async def tail_logs_until(self, *_a, **_k): return ok([])


def _build_dispatcher_with_galaxy_observation(tmp_path: Path):
    """Build the real dispatcher but with the Galaxy-S25 observation
    repo wired in. Reuses _build_fake_dispatcher's plumbing and just
    swaps the observation."""
    from tests.integration.test_tool_dispatcher import _build_fake_dispatcher

    dispatcher = _build_fake_dispatcher(tmp_path)
    # Swap the observation in every use case that has one. We do this
    # by reaching into the dispatcher's descriptors — each binds to a
    # use case via _bind. The use cases hold their repo refs. Rather
    # than rebuild the dispatcher manually, we monkeypatch the call
    # path: replace every reference to the observation_repo with our
    # Galaxy observation.
    galaxy = _GalaxyS25Observation()
    # Walk through every use case and re-wire its observation.
    # FakeObservation is referenced from use cases via _observation
    # attribute by convention.
    for descriptor in dispatcher.descriptors:
        # Some descriptors close over the use case via invoke;
        # extract the use case from the bound _bind closure.
        invoke = descriptor.invoke
        # __closure__ exposes the captured cell vars; the first is
        # the use case in our _bind helper.
        if invoke.__closure__:
            for cell in invoke.__closure__:
                try:
                    obj = cell.cell_contents
                except ValueError:
                    continue
                if hasattr(obj, "_observation"):
                    obj._observation = galaxy
    return dispatcher


@pytest.mark.asyncio
async def test_e2e_take_screenshot_path_passes_claude_api_check(tmp_path: Path):
    """The headline scenario: agent calls take_screenshot, then Claude
    Code Reads the resulting PNG. Path must be within cap."""
    dispatcher = _build_dispatcher_with_galaxy_observation(tmp_path)
    await dispatcher.dispatch("select_device", {"serial": "EMU01"})
    res = await dispatcher.dispatch("take_screenshot", {"label": "e2e"})
    rejected = _claude_api_simulator_reject(res)
    assert not rejected, f"take_screenshot leaked an over-cap PNG: {rejected}"


@pytest.mark.asyncio
async def test_e2e_prepare_for_test_evidence_screenshot_is_capped(tmp_path: Path):
    """The original live failure: prepare_for_test wrote evidence at
    3120×1440 and returned the path. Claude embedded it inline.
    Conversation broke."""
    dispatcher = _build_dispatcher_with_galaxy_observation(tmp_path)
    await dispatcher.dispatch("select_device", {"serial": "EMU01"})
    res = await dispatcher.dispatch(
        "prepare_for_test",
        {"package_id": "com.example", "project_path": str(tmp_path)},
    )
    rejected = _claude_api_simulator_reject(res)
    assert not rejected, (
        f"prepare_for_test leaked an over-cap PNG (the original live bug): "
        f"{rejected}"
    )


@pytest.mark.asyncio
async def test_e2e_full_walk_through_no_leak(tmp_path: Path):
    """Run a realistic sequence: device → prep → app launch → screenshot →
    summary. No envelope along the way may leak an over-cap PNG."""
    dispatcher = _build_dispatcher_with_galaxy_observation(tmp_path)
    sequence = [
        ("select_device", {"serial": "EMU01"}),
        ("new_session", {"label": "e2e"}),
        ("prepare_for_test", {
            "package_id": "com.example",
            "project_path": str(tmp_path),
        }),
        ("launch_app", {"package_id": "com.example"}),
        ("take_screenshot", {"label": "first"}),
        ("take_screenshot", {"label": "second"}),
        ("take_screenshot", {"label": "third"}),
        ("session_summary", {}),
        ("release_device", {}),
    ]
    leaks: list[tuple[str, list[tuple[str, int]]]] = []
    for name, args in sequence:
        res = await dispatcher.dispatch(name, args)
        rejected = _claude_api_simulator_reject(res)
        if rejected:
            leaks.append((name, rejected))
    assert not leaks, (
        f"end-to-end walk leaked over-cap PNGs from these tools:\n"
        + "\n".join(f"  {name}: {paths}" for name, paths in leaks)
    )


@pytest.mark.asyncio
async def test_e2e_pre_existing_oversized_file_seatbelt_catches(tmp_path: Path):
    """Edge case: the file already exists on disk over-cap before any
    tool runs (e.g. left over from a previous session before the cap
    landed). The dispatcher's seatbelt must still catch it the moment
    a tool returns the path."""
    dispatcher = _build_dispatcher_with_galaxy_observation(tmp_path)

    # Pre-create an oversized file at a path a tool would later return.
    artifacts = tmp_path / "sessions"
    artifacts.mkdir(parents=True, exist_ok=True)
    preexisting = artifacts / "leftover.png"
    _write_real_png(preexisting, _GALAXY_S25_W, _GALAXY_S25_H)
    assert _read_png_long_edge(preexisting) == _GALAXY_S25_W

    # Build a synthetic envelope as if a tool returned this path.
    from mcp_phone_controll.presentation.image_safety_net import cap_pngs_in_envelope

    envelope = {"ok": True, "data": str(preexisting)}
    out = cap_pngs_in_envelope(envelope)

    # Either the cap succeeded (Mac with sips/cv2/PIL) OR the seatbelt
    # refused. Both are acceptable; what's NOT acceptable is returning
    # an oversized path.
    if "<removed" not in str(out):
        # Cap succeeded — verify the file is now under-cap.
        long_edge = _read_png_long_edge(preexisting)
        assert long_edge is not None and long_edge <= _CLAUDE_API_LIMIT, (
            f"seatbelt let an over-cap file through: long_edge={long_edge}"
        )
    else:
        # Refused — must come with structured diagnosis.
        assert out["ok"] is False
        assert out["error"]["code"] == "ImageCapFailure"


@pytest.mark.asyncio
async def test_e2e_no_tool_returns_path_over_2000_under_any_legal_sequence(
    tmp_path: Path,
):
    """Property-style test: across a representative cross-section of
    screenshot-producing flows, no envelope can return a PNG path
    over 2000px on the long edge. This is the contract Claude's
    multi-image API enforces — we enforce it on our side."""
    dispatcher = _build_dispatcher_with_galaxy_observation(tmp_path)
    await dispatcher.dispatch("select_device", {"serial": "EMU01"})
    await dispatcher.dispatch("new_session", {"label": "props"})

    # Each of these is a real tool that has produced a PNG in the past
    # and returned its path in the response.
    candidates = [
        ("take_screenshot", {"label": "a"}),
        ("take_screenshot", {"label": "b"}),
        ("prepare_for_test", {
            "package_id": "com.example",
            "project_path": str(tmp_path),
        }),
    ]
    for name, args in candidates:
        res = await dispatcher.dispatch(name, args)
        rejected = _claude_api_simulator_reject(res)
        assert not rejected, (
            f"contract violation: {name} returned PNG over {_CLAUDE_API_LIMIT}px "
            f"on the long edge: {rejected}"
        )

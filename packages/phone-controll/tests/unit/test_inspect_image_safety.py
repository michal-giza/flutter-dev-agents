"""Tests for the `inspect_image_safety` agent-facing checker.

Closes the loop on the May 19 2026 raw-adb-screencap crash: agents now
have a cheap probe to call before `Read`-ing any image, so a 2400px PNG
from `adb exec-out screencap` gets `next_action: "compress_png"` instead
of silently poisoning the conversation context.

The probe must:
  - Handle every plausible bad input (missing path, non-PNG file,
    corrupt PNG header) with a structured error envelope, not an
    exception.
  - Classify dimensions consistently against the documented thresholds:
    >= 2000 → API will reject; > 1900 → recommend compress; else safe.
  - Detect MCP-produced images via the `.orig.png` sibling marker that
    the cap pipeline preserves.
  - Recommend `regenerate_via_take_screenshot` when the file is
    unsafe AND not MCP-produced (no `.orig.png` sibling). That's the
    cleanest path for raw-adb output where compress_png could in
    principle fail (no image backend available on the host).
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest

from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.inspect_image_safety import (
    InspectImageSafety,
    InspectImageSafetyParams,
)

# ---- helpers -----------------------------------------------------------


def _write_minimal_png(path: Path, width: int, height: int) -> None:
    """Write a tiny well-formed PNG with the requested dimensions.

    Bit depth is fixed at 8; color type is greyscale (0) so the IDAT
    block stays small. Enough for `_read_png_dimensions` (which only
    needs the IHDR header) without pulling in PIL.
    """
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_payload = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    ihdr = (
        struct.pack(">I", len(ihdr_payload))
        + b"IHDR"
        + ihdr_payload
        + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_payload))
    )
    # IDAT — single zlib-compressed row of zero pixels per scanline
    raw = b"".join(b"\x00" + b"\x00" * width for _ in range(height))
    idat_payload = zlib.compress(raw)
    idat = (
        struct.pack(">I", len(idat_payload))
        + b"IDAT"
        + idat_payload
        + struct.pack(">I", zlib.crc32(b"IDAT" + idat_payload))
    )
    iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", zlib.crc32(b"IEND"))
    path.write_bytes(sig + ihdr + idat + iend)


# ---- happy path: small PNG -----------------------------------------------


@pytest.mark.asyncio
async def test_small_png_is_safe_to_read(tmp_path: Path):
    p = tmp_path / "shot.png"
    _write_minimal_png(p, width=800, height=600)
    res = await InspectImageSafety()(InspectImageSafetyParams(path=p))
    assert isinstance(res, Ok)
    v = res.value
    assert v.safe_to_read is True
    assert v.next_action == "read_safely"
    assert v.long_edge_px == 800
    assert v.exceeds_api_dim_limit is False
    assert v.exceeds_safe_threshold is False
    assert v.mcp_produced is False  # no sibling


@pytest.mark.asyncio
async def test_png_with_orig_sibling_is_marked_mcp_produced(tmp_path: Path):
    p = tmp_path / "shot.png"
    _write_minimal_png(p, width=1024, height=768)
    # Simulate the cap pipeline's `.orig.png` companion
    _write_minimal_png(p.with_suffix(".orig.png"), width=2400, height=1080)
    res = await InspectImageSafety()(InspectImageSafetyParams(path=p))
    assert isinstance(res, Ok)
    assert res.value.mcp_produced is True
    assert res.value.safe_to_read is True


# ---- danger zone: exceeds API limit --------------------------------------


@pytest.mark.asyncio
async def test_2400px_png_without_mcp_marker_recommends_regenerate(
    tmp_path: Path,
):
    """Exactly the raw-adb-screencap scenario: a 2400px PNG with no
    .orig.png sibling. Recommend regenerate_via_take_screenshot, not
    compress_png — because if we got here it means the agent went
    around the MCP, and compress_png could in principle fail on a
    host missing all image backends."""
    p = tmp_path / "raw_adb_shot.png"
    _write_minimal_png(p, width=1080, height=2400)
    res = await InspectImageSafety()(InspectImageSafetyParams(path=p))
    assert isinstance(res, Ok)
    v = res.value
    assert v.safe_to_read is False
    assert v.exceeds_api_dim_limit is True
    assert v.long_edge_px == 2400
    assert v.next_action == "regenerate_via_take_screenshot"
    assert "take_screenshot" in v.advice


@pytest.mark.asyncio
async def test_2400px_png_with_mcp_marker_recommends_compress(tmp_path: Path):
    """A pathological case: an MCP-produced PNG that somehow ended up
    over the cap (stale subprocess running pre-1600 defaults, e.g.).
    `compress_png` is the right path since we know the file is in an
    allowed location and we trust the surrounding tooling."""
    p = tmp_path / "shot.png"
    _write_minimal_png(p, width=1080, height=2400)
    _write_minimal_png(p.with_suffix(".orig.png"), width=1080, height=2400)
    res = await InspectImageSafety()(InspectImageSafetyParams(path=p))
    assert isinstance(res, Ok)
    v = res.value
    assert v.next_action == "compress_png"
    assert "compress_png" in v.advice


@pytest.mark.asyncio
async def test_1950px_png_is_in_grey_zone_recommends_compress(tmp_path: Path):
    """Between 1900 and 2000 — below the hard ceiling but inside the
    safety margin. Recommend compress_png; safe_to_read=False."""
    p = tmp_path / "grey.png"
    _write_minimal_png(p, width=1950, height=1080)
    res = await InspectImageSafety()(InspectImageSafetyParams(path=p))
    assert isinstance(res, Ok)
    v = res.value
    assert v.safe_to_read is False
    assert v.exceeds_api_dim_limit is False
    assert v.exceeds_safe_threshold is True
    assert v.next_action == "compress_png"


@pytest.mark.asyncio
async def test_exactly_2000px_treated_as_exceeding_api_limit(tmp_path: Path):
    """The API limit is exclusive in our model — 2000 itself is the
    rejection threshold, not a safe maximum."""
    p = tmp_path / "edge.png"
    _write_minimal_png(p, width=2000, height=1080)
    res = await InspectImageSafety()(InspectImageSafetyParams(path=p))
    assert isinstance(res, Ok)
    assert res.value.exceeds_api_dim_limit is True


# ---- error paths --------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_path_returns_structured_error(tmp_path: Path):
    res = await InspectImageSafety()(
        InspectImageSafetyParams(path=tmp_path / "does_not_exist.png")
    )
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_non_png_file_returns_convert_action(tmp_path: Path):
    """Some agents will pass a .jpg by mistake. We don't decode it —
    just refuse with a clear next_action so they know what to do."""
    p = tmp_path / "shot.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0not-really-a-jpg")
    res = await InspectImageSafety()(InspectImageSafetyParams(path=p))
    assert isinstance(res, Err)
    # Either rejected as "not parseable PNG" or because of a malformed
    # header — both surface a sensible next_action.
    assert res.failure.next_action in ("convert_to_png", "check_path")


@pytest.mark.asyncio
async def test_corrupt_png_header_returns_structured_error(tmp_path: Path):
    """A file with a .png extension whose IHDR can't be parsed must
    not crash the probe — return an Err with details."""
    p = tmp_path / "corrupt.png"
    # Right magic, garbage where IHDR should be
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    res = await InspectImageSafety()(InspectImageSafetyParams(path=p))
    assert isinstance(res, Err)
    assert "PNG" in res.failure.message

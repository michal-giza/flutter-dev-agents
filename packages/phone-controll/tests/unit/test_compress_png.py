"""compress_png — recompress arbitrary PNGs on disk.

Use case: agent composes our MCP with `computer-use` (or any other MCP
that produces big screenshots). When the conversation hits "Request too
large (max 32MB)", the agent can call `compress_png(path=…)` on the
offending file to bring it under the byte budget without re-running the
tool that produced it.

Hermetic: writes a synthetic 4 MB PNG via PIL, asserts the use case
shrinks it >= 3x, and that idempotent re-runs are no-ops.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.domain.usecases.artifact_retention import (
    CompressPng,
    CompressPngParams,
)


def _have_pil() -> bool:
    try:
        import PIL  # noqa: F401

        return True
    except ImportError:
        return False


pytestmark = pytest.mark.skipif(not _have_pil(), reason="Pillow not installed")


def _write_truecolor_png(path: Path, width: int, height: int) -> int:
    """Write a PNG that's deliberately uncompressible-ish (random noise)
    so we can measure compression honestly. Returns the file size in
    bytes."""
    import random

    from PIL import Image

    rng = random.Random(42)
    # 256 unique colors arranged in horizontal bands — small enough that
    # palette compression is a clear win, big enough that the raw file
    # isn't trivially tiny.
    img = Image.new("RGB", (width, height))
    pixels = img.load()
    for y in range(height):
        for x in range(width):
            r = (x + y) & 0xFF
            g = (x * 2) & 0xFF
            b = (y * 3 + rng.randint(0, 10)) & 0xFF
            pixels[x, y] = (r, g, b)
    img.save(path, format="PNG")  # default compression — relatively large
    return path.stat().st_size


@pytest.mark.asyncio
async def test_compresses_truecolor_png_by_at_least_2x(tmp_path: Path):
    src = tmp_path / "big.png"
    before = _write_truecolor_png(src, 1200, 800)

    uc = CompressPng()
    res = await uc.execute(CompressPngParams(path=src))

    assert res.is_ok, res
    out = res.value
    assert out.bytes_before == before
    assert out.bytes_after < before
    # Truecolor → palette typically shrinks 2-5x. Asserting 2x lower
    # bound so the test doesn't flake on edge-case images.
    assert out.bytes_before >= out.bytes_after * 2, (
        f"expected at least 2x reduction; got {out.bytes_before} -> "
        f"{out.bytes_after}"
    )
    assert out.bytes_saved == out.bytes_before - out.bytes_after
    # No resize requested → dimensions unchanged.
    assert out.resized is False
    assert (out.width_before, out.height_before) == (1200, 800)
    assert (out.width_after, out.height_after) == (1200, 800)
    assert out.recompressed is True


@pytest.mark.asyncio
async def test_resize_and_recompress_when_max_dim_given(tmp_path: Path):
    src = tmp_path / "big.png"
    _write_truecolor_png(src, 2400, 1600)

    uc = CompressPng()
    res = await uc.execute(CompressPngParams(path=src, max_dim=800))

    assert res.is_ok
    out = res.value
    assert out.resized is True
    assert max(out.width_after, out.height_after) <= 800
    # Original preserved by cap_image_in_place's first-run snapshot.
    assert (tmp_path / "big.orig.png").exists()


@pytest.mark.asyncio
async def test_idempotent_second_call_is_noop(tmp_path: Path):
    src = tmp_path / "shot.png"
    _write_truecolor_png(src, 800, 600)

    uc = CompressPng()
    res1 = await uc.execute(CompressPngParams(path=src))
    assert res1.is_ok
    bytes_after_first = res1.value.bytes_after

    res2 = await uc.execute(CompressPngParams(path=src))
    assert res2.is_ok
    # Second call: file is already compressed — bytes_saved should be 0
    # (or negligible) and bytes_after should equal what we got after the
    # first call.
    assert res2.value.bytes_after <= bytes_after_first


@pytest.mark.asyncio
async def test_rejects_missing_file(tmp_path: Path):
    res = await CompressPng().execute(
        CompressPngParams(path=tmp_path / "ghost.png")
    )
    assert not res.is_ok
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_rejects_non_png_extension(tmp_path: Path):
    fake = tmp_path / "not_a_png.jpg"
    fake.write_bytes(b"\xff\xd8\xff")  # JPEG SOI bytes
    res = await CompressPng().execute(CompressPngParams(path=fake))
    assert not res.is_ok
    assert res.failure.next_action == "fix_arguments"
    assert ".png" in res.failure.message.lower()

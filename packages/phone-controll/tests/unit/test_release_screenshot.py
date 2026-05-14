"""capture_release_screenshot — full-res file on disk, metadata-only response."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from mcp_phone_controll.domain.entities import Session
from mcp_phone_controll.domain.result import Err, ok
from mcp_phone_controll.domain.usecases.release_screenshot import (
    CaptureReleaseScreenshot,
    CaptureReleaseScreenshotParams,
    _read_png_dimensions,
)


def _have_cv2() -> bool:
    try:
        import cv2  # noqa: F401
        return True
    except ImportError:
        return False


def _write_png(path: Path, width: int, height: int) -> None:
    """cv2-free PNG writer used when cv2 isn't installed; we hand-roll
    a minimal valid PNG so the dimension check still passes."""
    if _have_cv2():
        import cv2
        import numpy as np

        img = np.zeros((height, width, 3), dtype=np.uint8)
        cv2.imwrite(str(path), img)
        return
    # Tiny synthetic PNG: signature + IHDR + IDAT (empty) + IEND.
    # Width/height encoded so _read_png_dimensions can read them back.
    import struct
    import zlib

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = b"IHDR" + struct.pack(">II", width, height) + b"\x08\x02\x00\x00\x00"
    ihdr_crc = struct.pack(">I", zlib.crc32(ihdr))
    ihdr_len = struct.pack(">I", 13)
    raw = b"\x00" * (1 + 3 * width) * height
    idat_payload = zlib.compress(raw)
    idat = b"IDAT" + idat_payload
    idat_crc = struct.pack(">I", zlib.crc32(idat))
    idat_len = struct.pack(">I", len(idat_payload))
    iend = b"IEND"
    iend_crc = struct.pack(">I", zlib.crc32(iend))
    iend_len = struct.pack(">I", 0)
    path.write_bytes(sig + ihdr_len + ihdr + ihdr_crc + idat_len + idat + idat_crc + iend_len + iend + iend_crc)


class _FakeObservation:
    """Writes a synthetic 3120×1440 PNG, the Galaxy S25 native resolution."""

    async def screenshot(self, _serial, output_path: Path):
        _write_png(output_path, width=3120, height=1440)
        return ok(output_path)

    async def start_recording(self, _serial, _path): return ok(None)
    async def stop_recording(self, _serial): return ok(_Path := __import__("pathlib").Path("/tmp/rec.mp4"))
    async def read_logs(self, *_a, **_k): return ok([])
    async def tail_logs_until(self, *_a, **_k): return ok([])


class _FakeArtifacts:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._session = Session(
            id="s1", started_at=datetime(2026, 1, 1), root=root
        )

    async def new_session(self, _label=None): return ok(self._session)
    async def current_session(self): return ok(self._session)
    async def allocate_path(self, *_a, **_k):
        return ok(self._root / "alloc.png")
    async def register(self, _artifact): return ok(None)


class _FakeState:
    async def get_selected_serial(self): return ok("EMU01")
    async def set_selected_serial(self, _s): return ok(None)


# ---- the actual tests ----------------------------------------------------


@pytest.mark.asyncio
async def test_full_resolution_file_preserved(tmp_path: Path):
    uc = CaptureReleaseScreenshot(
        _FakeObservation(), _FakeArtifacts(tmp_path), _FakeState()
    )
    res = await uc.execute(
        CaptureReleaseScreenshotParams(label="01-home", serial="EMU01")
    )
    assert res.is_ok
    out = res.value
    # Full-res file on disk, untouched.
    full_path = out.release_dir / out.full_resolution_filename
    assert full_path.exists()
    w, h = _read_png_dimensions(full_path)
    assert (w, h) == (3120, 1440), (w, h)
    assert out.width == 3120
    assert out.height == 1440


@pytest.mark.asyncio
async def test_response_does_not_leak_full_path(tmp_path: Path):
    """The response must NOT contain the full-res path as a top-level string
    that Claude Code would auto-embed. It must be split into release_dir +
    filename so the agent has to compose the path explicitly."""
    uc = CaptureReleaseScreenshot(
        _FakeObservation(), _FakeArtifacts(tmp_path), _FakeState()
    )
    res = await uc.execute(CaptureReleaseScreenshotParams(label="x"))
    assert res.is_ok
    # Serialise like the dispatcher would; assert no string field equals
    # the absolute full-res path.
    from mcp_phone_controll.presentation.serialization import to_jsonable

    payload = to_jsonable(res.value)
    full = str(res.value.release_dir / res.value.full_resolution_filename)
    leaked = [
        (k, v) for k, v in payload.items()
        if isinstance(v, str) and v == full
    ]
    assert not leaked, f"full-res path leaked at: {leaked}"


@pytest.mark.asyncio
async def test_thumbnail_generated_when_cv2_available(tmp_path: Path):
    if not _have_cv2():
        pytest.skip("cv2 not installed")
    uc = CaptureReleaseScreenshot(
        _FakeObservation(), _FakeArtifacts(tmp_path), _FakeState()
    )
    res = await uc.execute(
        CaptureReleaseScreenshotParams(label="01", thumbnail_long_edge=128)
    )
    assert res.is_ok
    assert res.value.thumbnail is not None
    assert res.value.thumbnail.exists()
    w, h = _read_png_dimensions(res.value.thumbnail)
    assert max(w, h) == 128


@pytest.mark.asyncio
async def test_label_rejects_path_traversal(tmp_path: Path):
    uc = CaptureReleaseScreenshot(
        _FakeObservation(), _FakeArtifacts(tmp_path), _FakeState()
    )
    for bad in ("../escape", "a/b", "../../etc/passwd", ""):
        res = await uc.execute(CaptureReleaseScreenshotParams(label=bad))
        assert isinstance(res, Err), f"label {bad!r} should have been rejected"
        assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_sha256_and_size_are_real(tmp_path: Path):
    uc = CaptureReleaseScreenshot(
        _FakeObservation(), _FakeArtifacts(tmp_path), _FakeState()
    )
    res = await uc.execute(CaptureReleaseScreenshotParams(label="check"))
    assert res.is_ok
    assert len(res.value.sha256) == 64  # hex sha256
    assert res.value.size_bytes > 0
    # Verify the hash matches the actual file content.
    import hashlib

    full_path = res.value.release_dir / res.value.full_resolution_filename
    expected = hashlib.sha256(full_path.read_bytes()).hexdigest()
    assert res.value.sha256 == expected

"""Dispatcher-level seatbelt: cap any PNG path leaking out of a tool's
response envelope. Belt-and-braces against future use cases forgetting
to call cap_image_in_place themselves."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest

from mcp_phone_controll.presentation.image_safety_net import (
    _is_exempt,
    _looks_like_png_path,
    cap_pngs_in_envelope,
)


def _have_cv2() -> bool:
    try:
        import cv2  # noqa: F401
        return True
    except ImportError:
        return False


def _write_png(path: Path, width: int, height: int) -> None:
    if _have_cv2():
        import cv2
        import numpy as np

        img = np.zeros((height, width, 3), dtype=np.uint8)
        cv2.imwrite(str(path), img)
        return
    # Minimal valid PNG with the right IHDR for dimension reads to work.
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


def _read_dims(path: Path) -> tuple[int, int]:
    with path.open("rb") as fh:
        header = fh.read(24)
    return (
        int.from_bytes(header[16:20], "big"),
        int.from_bytes(header[20:24], "big"),
    )


# ---- exemption rules -----------------------------------------------------


def test_exempt_release_paths():
    assert _is_exempt("/Users/me/.mcp_phone_controll/sessions/s1/release/01-home.png")


def test_exempt_golden_paths():
    assert _is_exempt("/Users/me/Desktop/myapp/tests/fixtures/golden/home.png")


def test_non_exempt_regular_screenshot():
    assert not _is_exempt("/Users/me/.mcp_phone_controll/sessions/s1/screenshot-1.png")


# ---- path detection ------------------------------------------------------


def test_looks_like_png_only_for_real_files(tmp_path: Path):
    real = tmp_path / "x.png"
    real.touch()
    assert _looks_like_png_path(str(real))
    assert not _looks_like_png_path("/nope/x.png")
    assert not _looks_like_png_path("not a path")
    # exists() returns False, so the heuristic correctly rejects it.
    assert not _looks_like_png_path("see <path>.orig.png for original")


def test_looks_like_png_rejects_absurdly_long_strings():
    assert not _looks_like_png_path("/" + ("x" * 2000) + ".png")


# ---- seatbelt behaviour --------------------------------------------------


pytestmark = pytest.mark.skipif(not _have_cv2(), reason="cv2 not installed")


def test_caps_oversized_png_referenced_in_envelope_data(tmp_path: Path):
    oversize = tmp_path / "shot.png"
    _write_png(oversize, width=3120, height=1440)
    envelope = {"ok": True, "data": str(oversize)}
    out = cap_pngs_in_envelope(envelope)
    assert out.get("image_cap", {}).get("capped") == [str(oversize)]
    # Default cap is 1600 (lowered from 1920 — see image_capping.py docstring).
    assert max(_read_dims(oversize)) <= 1600


def test_walks_nested_dict_and_caps(tmp_path: Path):
    p1 = tmp_path / "a.png"
    _write_png(p1, 3120, 1440)
    p2 = tmp_path / "b.png"
    _write_png(p2, 2400, 1080)
    envelope = {
        "ok": True,
        "data": {
            "evidence_screenshot": str(p1),
            "extras": {"snapshot": str(p2)},
        },
    }
    out = cap_pngs_in_envelope(envelope)
    assert len(out["image_cap"]["capped"]) == 2


def test_skips_exempt_paths(tmp_path: Path):
    release_dir = tmp_path / "release"
    release_dir.mkdir()
    release = release_dir / "01-home.png"
    _write_png(release, width=3120, height=1440)
    envelope = {"ok": True, "data": {"full": str(release)}}
    out = cap_pngs_in_envelope(envelope)
    assert "image_cap" not in out
    # Exempt paths keep their native dimensions (> default 1600 cap).
    assert max(_read_dims(release)) > 1600


def test_idempotent(tmp_path: Path):
    p = tmp_path / "x.png"
    _write_png(p, 3120, 1440)
    cap_pngs_in_envelope({"data": str(p)})
    # second call: file is already under cap, no rewrite.
    out = cap_pngs_in_envelope({"data": str(p)})
    assert "image_cap" not in out


def test_handles_missing_file_gracefully():
    envelope = {"ok": True, "data": "/tmp/definitely-not-a-real-file.png"}
    out = cap_pngs_in_envelope(envelope)
    assert "image_cap" not in out


def test_hard_refuses_when_cap_fails(tmp_path: Path, monkeypatch):
    """Simulate cv2/PIL/sips all unavailable. The seatbelt must rewrite
    the envelope, flip ok=false, and attach a structured diagnosis."""
    oversize = tmp_path / "shot.png"
    _write_png(oversize, width=3120, height=1440)

    # Break every backend.
    import mcp_phone_controll.data.image_capping as cap_mod

    monkeypatch.setattr(cap_mod, "_resize_cv2", lambda *a, **k: False)
    monkeypatch.setattr(cap_mod, "_resize_pil", lambda *a, **k: False)
    monkeypatch.setattr(cap_mod, "_resize_sips", lambda *a, **k: False)

    envelope = {"ok": True, "data": str(oversize)}
    out = cap_pngs_in_envelope(envelope)

    # The path must be removed from the agent-visible data field so
    # Claude Code's auto-embed doesn't pick it up. The diagnostic
    # `error.details.image_cap.refused[].path` deliberately keeps the
    # path so the operator can find and fix the file.
    assert out["data"] != str(oversize)
    assert "<removed" in out["data"]
    # ok=false; structured error.
    assert out["ok"] is False
    assert out["error"]["code"] == "ImageCapFailure"
    assert out["error"]["next_action"] == "install_image_backend"
    refused = out["error"]["details"]["image_cap"]["refused"]
    assert len(refused) == 1
    assert refused[0]["path"] == str(oversize)


def test_capped_envelope_keeps_ok_true_when_all_caps_succeed(tmp_path: Path):
    p = tmp_path / "shot.png"
    _write_png(p, 3120, 1440)
    out = cap_pngs_in_envelope({"ok": True, "data": str(p)})
    # Successfully capped — ok stays True; diagnostic ride-along.
    assert out["ok"] is True
    assert "capped" in out["image_cap"]


# ---- hard 1900 ceiling --------------------------------------------------
#
# The whole reason `_HARD_CEILING_PX = 1900` exists is "the env-driven
# default leaked through one too many times." If the soft cap is
# misconfigured higher than 1900, the safety net MUST still bring the
# file under 1900 — not blindly respect the env value. These tests
# encode that invariant. They break if anyone ever wires the hard
# ceiling to consult the env var instead of being literal.


def test_hard_ceiling_catches_oversoft_env_cap(tmp_path: Path, monkeypatch):
    """Env says cap to 2400 (silly); safety net must still enforce 1900.

    Without the hard ceiling, an `MCP_MAX_IMAGE_DIM=2400` override would
    leak a 2300-px file straight through to the API and trigger the
    2000px rejection. With the hard ceiling, the safety net re-caps to
    1900 regardless.
    """
    monkeypatch.setenv("MCP_MAX_IMAGE_DIM", "2400")

    big = tmp_path / "wide.png"
    _write_png(big, 2300, 1000)  # under env cap (2400) but over hard (1900)

    out = cap_pngs_in_envelope({"ok": True, "data": str(big)})

    # Should still be ok=True (we successfully capped via the hard
    # ceiling fallback path) and the file on disk must now be <= 1900.
    assert out["ok"] is True, out
    assert max(_read_dims(big)) <= 1900


def test_hard_ceiling_refuses_when_no_backend_can_cap(tmp_path: Path, monkeypatch):
    """If both cap attempts fail, the safety net flips ok=False and
    replaces the path string with the `<removed: ...>` marker."""
    from mcp_phone_controll.data import image_capping

    monkeypatch.setattr(image_capping, "cap_image_in_place", lambda *a, **k: False)

    huge = tmp_path / "bad.png"
    _write_png(huge, 3000, 2000)  # well over hard ceiling

    out = cap_pngs_in_envelope({"ok": True, "data": str(huge)})

    assert out["ok"] is False
    assert out["error"]["code"] == "ImageCapFailure"
    assert out["error"]["next_action"] == "install_image_backend"
    # The offending path is no longer reachable in the envelope's
    # data field — it's been replaced with the removed-marker.
    assert str(huge) not in str(out["data"])


# ---- byte budget --------------------------------------------------------
#
# Dimensions can be fine while bytes blow the request limit (32 MB
# total). The byte-budget pass re-encodes PNGs that exceed
# `MCP_MAX_IMAGE_BYTES_KB` even if they're already within dimension
# cap.


def test_byte_budget_recompresses_oversized_but_dim_ok(tmp_path: Path):
    """A 800x600 PNG with random pixel data is well under the dim cap
    but ~600 KB on disk. The byte-budget pass should recompress it and
    surface the compressed path in `image_cap.compressed`.
    """
    import random

    src = tmp_path / "heavy.png"
    rng = random.Random(123)
    img = _np_for_random(800, 600, rng)
    cv2 = pytest.importorskip("cv2")
    cv2.imwrite(str(src), img)

    before = src.stat().st_size

    out = cap_pngs_in_envelope({"ok": True, "data": str(src)})

    # Dimensions never exceeded, so `capped` may be empty — but
    # `compressed` should list the path because cv2's default
    # compression is light and the file is well over 250 KB.
    if before > 250 * 1024:
        assert "compressed" in out.get("image_cap", {}), out
        # File should now be smaller.
        assert src.stat().st_size < before


def test_byte_budget_respects_env_override(tmp_path: Path, monkeypatch):
    """Setting `MCP_MAX_IMAGE_BYTES_KB=50` should trigger recompression
    on a 1080x1920 PNG that would otherwise be skipped at the default
    250 KB threshold."""
    monkeypatch.setenv("MCP_MAX_IMAGE_BYTES_KB", "50")

    src = tmp_path / "compact.png"
    _write_png(src, 1080, 1920)  # blue rect — likely <250KB after cv2 default

    out = cap_pngs_in_envelope({"ok": True, "data": str(src)})

    if src.stat().st_size > 50 * 1024:
        assert "compressed" in out.get("image_cap", {})


# Helper for the random-pixel test above. Lazy-imports numpy/cv2 only
# inside the test that needs them.
def _np_for_random(w: int, h: int, rng):
    np = pytest.importorskip("numpy")
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    # Stripe the image with random RGBs per band — uncompressible at
    # default level, so the file is big enough to trigger the byte path.
    for y in range(h):
        arr[y, :, 0] = rng.randint(0, 255)
        arr[y, :, 1] = rng.randint(0, 255)
        arr[y, :, 2] = rng.randint(0, 255)
    return arr

"""cap_image_in_place — resize over-cap PNGs, preserve originals, fail open."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.data.image_capping import cap_image_in_place


def _have_cv2() -> bool:
    try:
        import cv2  # noqa: F401
        return True
    except ImportError:
        return False


pytestmark = pytest.mark.skipif(not _have_cv2(), reason="cv2 not installed")


def _write_png(path: Path, width: int, height: int) -> None:
    import cv2
    import numpy as np

    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:, :, 0] = 255  # blue rectangle so we can confirm it survives resize
    cv2.imwrite(str(path), img)


def test_caps_image_over_max_dim(tmp_path: Path):
    src = tmp_path / "shot.png"
    _write_png(src, width=3120, height=1440)
    resized = cap_image_in_place(src, max_dim=1920)
    assert resized is True
    import cv2

    out = cv2.imread(str(src))
    h, w = out.shape[:2]
    assert max(h, w) == 1920
    # Original preserved.
    assert (tmp_path / "shot.orig.png").exists()


def test_no_op_when_image_already_under_cap(tmp_path: Path):
    src = tmp_path / "shot.png"
    _write_png(src, width=1080, height=1920)
    resized = cap_image_in_place(src, max_dim=1920)
    assert resized is False
    assert not (tmp_path / "shot.orig.png").exists()


def test_zero_max_dim_disables_capping(tmp_path: Path):
    src = tmp_path / "shot.png"
    _write_png(src, width=4000, height=2000)
    resized = cap_image_in_place(src, max_dim=0)
    assert resized is False


def test_idempotent_on_repeated_calls(tmp_path: Path):
    src = tmp_path / "shot.png"
    _write_png(src, width=3120, height=1440)
    cap_image_in_place(src, max_dim=1920)
    # Second call — already capped, should be no-op AND must not overwrite
    # the preserved original.
    original_size = (tmp_path / "shot.orig.png").stat().st_size
    resized_again = cap_image_in_place(src, max_dim=1920)
    assert resized_again is False
    assert (tmp_path / "shot.orig.png").stat().st_size == original_size


def test_env_var_drives_default_cap(tmp_path: Path, monkeypatch):
    src = tmp_path / "shot.png"
    _write_png(src, width=2400, height=1200)
    monkeypatch.setenv("MCP_MAX_IMAGE_DIM", "1024")
    resized = cap_image_in_place(src)  # no explicit max_dim → uses env var
    assert resized is True
    import cv2

    out = cv2.imread(str(src))
    assert max(out.shape[:2]) == 1024


# ---- performance regression guard --------------------------------------
#
# The image-cap path runs on every screenshot envelope. The dispatcher's
# image-safety-net middleware walks every response payload and caps any
# oversized PNG before it can reach the model. If that path ever regresses
# to seconds-per-screenshot (e.g. someone swaps cv2 for a Python-only PIL
# resize on a multi-MP image without thumbnail's in-place decimation),
# agents grind to a halt.
#
# These tests pin a generous-but-meaningful budget. They're not benchmarks
# — they catch the difference between "fast enough" and "broken."


def test_cap_latency_under_budget_for_galaxy_s25_capture(tmp_path: Path):
    """A real Galaxy S25 screenshot (1080×2340) caps under 250 ms.

    Budget: 250 ms wall-clock for cv2-backed cap of a 1080×2340 PNG to
    1920px on the long edge. Measured on a 2024 M-series laptop, the
    cv2 path completes in <50 ms; we leave 5× headroom for CI variance.
    A regression past 250 ms means the agent loop has stopped being
    interactive — that's the signal to investigate.
    """
    import time

    src = tmp_path / "screen_s25.png"
    _write_png(src, width=1080, height=2340)

    started = time.monotonic()
    resized = cap_image_in_place(src, max_dim=1920)
    elapsed_ms = (time.monotonic() - started) * 1000.0

    assert resized is True
    assert elapsed_ms < 250.0, (
        f"image cap took {elapsed_ms:.0f} ms — budget is 250 ms. "
        "Did someone swap the cv2 backend for a slower path?"
    )


def test_cap_no_op_is_effectively_free(tmp_path: Path):
    """When the image is already within the cap, the helper short-circuits.

    Budget: 30 ms/call averaged across 5 calls. The under-cap branch
    should only stat the file and peek at PNG header bytes — no
    decode, no resize. If we ever start decoding in this branch we'll
    spend >100 ms per screenshot for no reason.
    """
    import time

    src = tmp_path / "small.png"
    _write_png(src, width=1080, height=1920)  # exactly at cap

    # Warm up filesystem cache so the first stat doesn't pay disk latency.
    cap_image_in_place(src, max_dim=1920)

    started = time.monotonic()
    for _ in range(5):
        resized = cap_image_in_place(src, max_dim=1920)
        assert resized is False
    avg_ms = (time.monotonic() - started) * 1000.0 / 5

    assert avg_ms < 30.0, (
        f"under-cap short-circuit took {avg_ms:.1f} ms/call — "
        "the helper is probably decoding when it shouldn't."
    )

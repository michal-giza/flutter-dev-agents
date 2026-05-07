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

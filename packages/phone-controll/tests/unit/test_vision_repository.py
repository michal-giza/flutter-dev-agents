"""Vision tests using OpenCV. Skips cleanly if cv2 isn't installed."""

from __future__ import annotations

from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from mcp_phone_controll.data.repositories.opencv_vision_repository import (
    OpenCvVisionRepository,
)
from mcp_phone_controll.domain.result import Err, Ok


def _write_solid(path: Path, w: int, h: int, color: tuple[int, int, int]):
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, :] = color
    cv2.imwrite(str(path), img)


def _write_aruco(path: Path, marker_id: int, size: int = 200, dict_name: str = "DICT_4X4_50"):
    aruco = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dict_name))
    img = cv2.aruco.generateImageMarker(aruco, marker_id, size)
    # Pad with white border so the detector has clean margins
    pad = 50
    canvas = np.ones((size + 2 * pad, size + 2 * pad), dtype=np.uint8) * 255
    canvas[pad : pad + size, pad : pad + size] = img
    bgr = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)
    cv2.imwrite(str(path), bgr)


# -- compare ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_compare_identical_images(tmp_path: Path):
    actual = tmp_path / "actual.png"
    golden = tmp_path / "golden.png"
    _write_solid(actual, 100, 100, (50, 100, 200))
    _write_solid(golden, 100, 100, (50, 100, 200))

    repo = OpenCvVisionRepository()
    res = await repo.compare(actual, golden, tolerance=0.99)
    assert isinstance(res, Ok)
    assert res.value.passed is True
    assert res.value.similarity == pytest.approx(1.0)
    assert res.value.masked_pixels == 0


@pytest.mark.asyncio
async def test_compare_different_images_fails(tmp_path: Path):
    actual = tmp_path / "actual.png"
    golden = tmp_path / "golden.png"
    _write_solid(actual, 100, 100, (0, 0, 0))
    _write_solid(golden, 100, 100, (255, 255, 255))
    diff = tmp_path / "diff.png"

    repo = OpenCvVisionRepository()
    res = await repo.compare(actual, golden, tolerance=0.99, diff_output_path=diff)
    assert isinstance(res, Ok)
    assert res.value.passed is False
    assert res.value.similarity == pytest.approx(0.0)
    assert res.value.diff_image_path == diff
    assert diff.exists()


@pytest.mark.asyncio
async def test_compare_missing_file(tmp_path: Path):
    repo = OpenCvVisionRepository()
    res = await repo.compare(tmp_path / "nope.png", tmp_path / "also_nope.png")
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


# -- detect_markers --------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_markers_finds_planted_marker(tmp_path: Path):
    image = tmp_path / "marker.png"
    _write_aruco(image, marker_id=7)

    repo = OpenCvVisionRepository()
    res = await repo.detect_markers(image)
    assert isinstance(res, Ok)
    ids = {m.id for m in res.value}
    assert 7 in ids


@pytest.mark.asyncio
async def test_detect_markers_returns_empty_when_none(tmp_path: Path):
    image = tmp_path / "blank.png"
    _write_solid(image, 200, 200, (240, 240, 240))

    repo = OpenCvVisionRepository()
    res = await repo.detect_markers(image)
    assert isinstance(res, Ok)
    assert res.value == []


@pytest.mark.asyncio
async def test_detect_markers_unsupported_dict(tmp_path: Path):
    image = tmp_path / "marker.png"
    _write_aruco(image, marker_id=0)

    repo = OpenCvVisionRepository()
    res = await repo.detect_markers(image, dictionary="DICT_NOT_REAL")
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


# -- pose ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_infer_pose_returns_pose_for_known_marker(tmp_path: Path):
    image = tmp_path / "marker.png"
    _write_aruco(image, marker_id=3, size=300)

    repo = OpenCvVisionRepository()
    res = await repo.infer_pose(image, marker_id=3, marker_size_m=0.05)
    assert isinstance(res, Ok)
    assert res.value.marker_id == 3
    assert len(res.value.tvec) == 3

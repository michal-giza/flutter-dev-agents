"""zoom_screenshot — crop + upscale a screen region (v0.14.0 #7)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PIL")
from PIL import Image

from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.observation import (
    ZoomScreenshot,
    ZoomScreenshotParams,
)
from tests.fakes.fake_repositories import (
    FakeArtifactRepository,
    FakeObservationRepository,
    FakeSessionStateRepository,
)


def _png(tmp_path: Path, w=400, h=600) -> Path:
    p = tmp_path / "src.png"
    Image.new("RGB", (w, h), (10, 20, 30)).save(p)
    return p


def _uc(tmp_path):
    return ZoomScreenshot(
        FakeObservationRepository(),
        FakeArtifactRepository(root=tmp_path / "sessions"),
        FakeSessionStateRepository(serial="dev"),
    )


@pytest.mark.asyncio
async def test_crops_and_upscales_an_existing_screenshot(tmp_path):
    src = _png(tmp_path, 400, 600)
    uc = _uc(tmp_path)
    res = await uc(ZoomScreenshotParams(region=(100, 100, 200, 200), path=src, scale=3.0))
    assert isinstance(res, Ok), res
    out = Path(res.value)
    assert out.exists()
    with Image.open(out) as img:
        # 100x100 crop upscaled 3x = 300x300 (no cap needed; under the limit)
        assert img.size == (300, 300)


@pytest.mark.asyncio
async def test_region_clamped_to_image_bounds(tmp_path):
    src = _png(tmp_path, 400, 600)
    uc = _uc(tmp_path)
    # region runs off the right/bottom edge — must clamp, not error
    res = await uc(ZoomScreenshotParams(region=(350, 550, 999, 999), path=src, scale=1.0))
    assert isinstance(res, Ok), res
    with Image.open(Path(res.value)) as img:
        assert img.size == (50, 50)  # clamped to 400x600


@pytest.mark.asyncio
async def test_invalid_region_errors(tmp_path):
    uc = _uc(tmp_path)
    res = await uc(ZoomScreenshotParams(region=(200, 200, 100, 100), path=_png(tmp_path)))
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_missing_source_path_errors(tmp_path):
    uc = _uc(tmp_path)
    res = await uc(
        ZoomScreenshotParams(region=(0, 0, 10, 10), path=tmp_path / "nope.png")
    )
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"

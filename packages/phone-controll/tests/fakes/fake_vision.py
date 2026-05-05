"""Fake VisionRepository for tests that don't need real OpenCV."""

from __future__ import annotations

from pathlib import Path

from mcp_phone_controll.domain.entities import ImageDiff, MarkerDetection, Pose
from mcp_phone_controll.domain.result import ok


class FakeVisionRepository:
    def __init__(
        self,
        markers: list[MarkerDetection] | None = None,
        diff: ImageDiff | None = None,
        pose: Pose | None = None,
    ) -> None:
        self.markers = markers or []
        self.diff = diff or ImageDiff(similarity=1.0, threshold=0.98, passed=True)
        self.pose = pose or Pose(rvec=(0.0, 0.0, 0.0), tvec=(0.0, 0.0, 0.5), marker_id=0)

    async def compare(self, actual_path, golden_path, tolerance=0.98, diff_output_path=None):
        return ok(self.diff)

    async def detect_markers(self, image_path, dictionary="DICT_4X4_50"):
        return ok(list(self.markers))

    async def infer_pose(self, image_path, marker_id, marker_size_m, camera_matrix=None):
        return ok(self.pose)

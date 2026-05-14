"""Advanced AR/Vision use cases for the 4-of-6 apps that ship AR features.

These complement the v1 vision tools (compare_screenshot, detect_markers,
infer_camera_pose, wait_for_marker) with:
  - calibrate_camera : produces real intrinsics from chessboard images
  - assert_pose_stable : filters single-frame outliers
  - wait_for_ar_session_ready : gates on ARKit/ARCore tracking-state log
  - save_golden_image : captures + writes to a project's golden dir
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from pathlib import Path

from ..entities import (
    CameraIntrinsics,
    GoldenImage,
    Pose,
    PoseStabilityReport,
)
from ..failures import TimeoutFailure, VisionFailure
from ..repositories import (
    ArtifactRepository,
    ObservationRepository,
    SessionStateRepository,
    VisionRepository,
)
from ..result import Err, Result, err, ok
from .base import BaseUseCase
from ._helpers import resolve_serial


# --- calibrate_camera ----------------------------------------------------


@dataclass(frozen=True, slots=True)
class CalibrateCameraParams:
    image_paths: list[Path]
    board_cols: int = 9             # inner corner cols
    board_rows: int = 6             # inner corner rows
    square_size_m: float = 0.025    # 25mm default


class CalibrateCamera(BaseUseCase[CalibrateCameraParams, CameraIntrinsics]):
    """Run cv2.calibrateCamera over a set of chessboard images.

    Requires opencv (the [ar] extra). Returns reusable intrinsics so
    infer_camera_pose can produce world-coordinate poses, not just relative ones.
    """

    def __init__(self, vision: VisionRepository | None = None) -> None:
        # vision repo not used directly today — kept for parity / future moves.
        self._vision = vision

    async def execute(
        self, params: CalibrateCameraParams
    ) -> Result[CameraIntrinsics]:
        if not params.image_paths:
            return err(
                VisionFailure(
                    message="calibrate_camera needs at least one chessboard image",
                    next_action="fix_arguments",
                )
            )
        return await asyncio.to_thread(
            self._calibrate_sync,
            params.image_paths,
            params.board_cols,
            params.board_rows,
            params.square_size_m,
        )

    def _calibrate_sync(
        self,
        image_paths: list[Path],
        cols: int,
        rows: int,
        square_size_m: float,
    ) -> Result[CameraIntrinsics]:
        try:
            import cv2
            import numpy as np
        except ImportError as e:
            return err(
                VisionFailure(
                    message=f"OpenCV not installed: {e}",
                    next_action="install_ar_extras",
                    details={"hint": "uv pip install -e \".[ar]\""},
                )
            )

        objp = np.zeros((cols * rows, 3), np.float32)
        objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2) * square_size_m
        obj_points: list = []
        img_points: list = []
        image_size: tuple[int, int] | None = None

        for path in image_paths:
            if not path.exists():
                return err(
                    VisionFailure(
                        message=f"image not found: {path}",
                        next_action="fix_arguments",
                    )
                )
            img = cv2.imread(str(path))
            if img is None:
                continue
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            image_size = gray.shape[::-1]
            found, corners = cv2.findChessboardCorners(gray, (cols, rows), None)
            if not found:
                continue
            corners_refined = cv2.cornerSubPix(
                gray, corners, (11, 11), (-1, -1),
                criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001),
            )
            obj_points.append(objp)
            img_points.append(corners_refined)

        if len(obj_points) < 3:
            return err(
                VisionFailure(
                    message=(
                        "calibration needs at least 3 images with a detected "
                        f"chessboard ({cols}x{rows} inner corners). "
                        f"Got {len(obj_points)} usable images out of {len(image_paths)}."
                    ),
                    next_action="more_calibration_images",
                )
            )
        assert image_size is not None
        rms, mtx, dist, _, _ = cv2.calibrateCamera(
            obj_points, img_points, image_size, None, None
        )
        return ok(
            CameraIntrinsics(
                fx=float(mtx[0, 0]),
                fy=float(mtx[1, 1]),
                cx=float(mtx[0, 2]),
                cy=float(mtx[1, 2]),
                distortion=tuple(float(v) for v in dist.flatten()),
                reprojection_error=float(rms),
                sample_count=len(obj_points),
            )
        )


# --- assert_pose_stable -------------------------------------------------


@dataclass(frozen=True, slots=True)
class AssertPoseStableParams:
    marker_id: int
    samples: int = 10
    sample_interval_s: float = 0.2
    max_translation_m: float = 0.005    # 5mm
    max_rotation_deg: float = 2.0
    marker_size_m: float = 0.05
    serial: str | None = None


class AssertPoseStable(
    BaseUseCase[AssertPoseStableParams, PoseStabilityReport]
):
    """Capture N pose samples of a marker and assert frame-to-frame stability.

    Filters out single-frame outliers that compare_screenshot and detect_markers
    don't catch. Useful as a gate before asserting AR overlay placement.
    """

    def __init__(
        self,
        vision: VisionRepository,
        observation: ObservationRepository,
        artifacts: ArtifactRepository,
        state: SessionStateRepository,
    ) -> None:
        self._vision = vision
        self._observation = observation
        self._artifacts = artifacts
        self._state = state

    async def execute(
        self, params: AssertPoseStableParams
    ) -> Result[PoseStabilityReport]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        serial = serial_res.value

        poses: list[Pose] = []
        for i in range(params.samples):
            path_res = await self._artifacts.allocate_path(
                "screenshot", ".png", f"pose-{i}"
            )
            if isinstance(path_res, Err):
                return path_res
            shot_res = await self._observation.screenshot(serial, path_res.value)
            if isinstance(shot_res, Err):
                return shot_res
            # Cap each pose-sample frame so Claude doesn't choke on a
            # long-running pose check that emits 20+ uncapped PNGs.
            # Pose math runs over the original via prefer_original.
            from ...data.image_capping import cap_image_in_place, prefer_original

            cap_image_in_place(shot_res.value)
            pose_res = await self._vision.infer_pose(
                prefer_original(shot_res.value),
                params.marker_id,
                params.marker_size_m,
            )
            if isinstance(pose_res, Err):
                # Skip frames where the marker isn't seen rather than failing
                continue
            poses.append(pose_res.value)
            await asyncio.sleep(params.sample_interval_s)

        if len(poses) < max(2, params.samples // 2):
            return err(
                VisionFailure(
                    message=(
                        f"only {len(poses)} of {params.samples} frames had a "
                        f"detectable marker {params.marker_id}"
                    ),
                    next_action="check_lighting",
                )
            )

        # Compute spread of translations and rotations.
        max_t = 0.0
        max_r = 0.0
        for i, a in enumerate(poses):
            for b in poses[i + 1 :]:
                dt = math.sqrt(
                    sum((a.tvec[k] - b.tvec[k]) ** 2 for k in range(3))
                )
                dr_rad = math.sqrt(
                    sum((a.rvec[k] - b.rvec[k]) ** 2 for k in range(3))
                )
                max_t = max(max_t, dt)
                max_r = max(max_r, math.degrees(dr_rad))

        passed = (
            max_t <= params.max_translation_m
            and max_r <= params.max_rotation_deg
        )
        return ok(
            PoseStabilityReport(
                marker_id=params.marker_id,
                samples=len(poses),
                translation_max_delta_m=max_t,
                rotation_max_delta_deg=max_r,
                passed=passed,
            )
        )


# --- wait_for_ar_session_ready -----------------------------------------


@dataclass(frozen=True, slots=True)
class WaitForArSessionReadyParams:
    timeout_s: float = 30.0
    serial: str | None = None
    # Custom log patterns can override the defaults — useful for non-standard
    # AR engines or custom telemetry tags.
    android_pattern: str = r"ARCore.*tracking.*NORMAL|TRACKING_STATE_TRACKING"
    ios_pattern: str = r"ARSession.*trackingState.*normal|ARTrackingStateNormal"


class WaitForArSessionReady(
    BaseUseCase[WaitForArSessionReadyParams, str]
):
    """Tail device logs until an AR session reports normal tracking.

    Returns the matched log line so the caller has a citation for the report.
    """

    def __init__(
        self,
        observation: ObservationRepository,
        state: SessionStateRepository,
    ) -> None:
        self._observation = observation
        self._state = state

    async def execute(
        self, params: WaitForArSessionReadyParams
    ) -> Result[str]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        # We don't know the platform here; tail with the most permissive pattern
        # so either ARCore or ARKit logs match.
        combined = f"({params.android_pattern})|({params.ios_pattern})"
        res = await self._observation.tail_logs_until(
            serial=serial_res.value,
            until_pattern=combined,
            timeout_s=params.timeout_s,
        )
        if isinstance(res, Err):
            return res
        if not res.value:
            return err(
                TimeoutFailure(
                    message="AR session never reported normal tracking",
                    next_action="check_lighting",
                )
            )
        last = res.value[-1]
        return ok(last.message)


# --- save_golden_image -----------------------------------------------


@dataclass(frozen=True, slots=True)
class SaveGoldenImageParams:
    label: str
    project_path: Path | None = None    # If None, saves under artifacts dir
    serial: str | None = None


class SaveGoldenImage(BaseUseCase[SaveGoldenImageParams, GoldenImage]):
    """Capture a screenshot and write it to a project's golden directory.

    Default location: <project>/tests/fixtures/golden/<label>.png. Falls back
    to the artifacts dir if no project_path is given. Used to bootstrap golden
    images for compare_screenshot regression tests.
    """

    def __init__(
        self,
        observation: ObservationRepository,
        artifacts: ArtifactRepository,
        state: SessionStateRepository,
    ) -> None:
        self._observation = observation
        self._artifacts = artifacts
        self._state = state

    async def execute(self, params: SaveGoldenImageParams) -> Result[GoldenImage]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res

        if params.project_path is not None:
            target_dir = (
                params.project_path / "tests" / "fixtures" / "golden"
            )
        else:
            session_res = await self._artifacts.current_session()
            if isinstance(session_res, Err):
                return session_res
            target_dir = session_res.value.root / "golden"
        target_dir.mkdir(parents=True, exist_ok=True)
        out = target_dir / f"{params.label}.png"
        # Goldens are intentionally NOT dimension-capped — visual-diff math
        # wants the full sensor. The cap in TakeScreenshot only applies to
        # the agent-facing path; ObservationRepository.screenshot here
        # writes the raw frame.
        shot_res = await self._observation.screenshot(serial_res.value, out)
        if isinstance(shot_res, Err):
            return shot_res
        size = out.stat().st_size if out.exists() else 0
        return ok(GoldenImage(label=params.label, path=out, image_size_bytes=size))

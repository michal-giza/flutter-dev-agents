"""VisionRepository implementation backed by OpenCV.

OpenCV is imported lazily so the core MCP runs without the [ar] extra installed.
Every call surfaces typed VisionFailure with `next_action` hints when it can.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from ...domain.entities import ImageDiff, MarkerDetection, Pose
from ...domain.failures import VisionFailure
from ...domain.repositories import VisionRepository
from ...domain.result import Result, err, ok


def _require_cv2():
    try:
        import cv2  # noqa: F401
        import numpy as np  # noqa: F401
    except ImportError as e:
        return err(
            VisionFailure(
                message=f"OpenCV / numpy not installed: {e}",
                next_action="install_ar_extras",
                details={"hint": "uv pip install -e \".[ar]\""},
            )
        )
    return None


_DICT_NAMES = {
    "DICT_4X4_50": "DICT_4X4_50",
    "DICT_5X5_50": "DICT_5X5_50",
    "DICT_6X6_250": "DICT_6X6_250",
    "DICT_ARUCO_ORIGINAL": "DICT_ARUCO_ORIGINAL",
}


class OpenCvVisionRepository(VisionRepository):
    async def compare(
        self,
        actual_path: Path,
        golden_path: Path,
        tolerance: float = 0.98,
        diff_output_path: Path | None = None,
    ) -> Result[ImageDiff]:
        miss = _require_cv2()
        if miss is not None:
            return miss

        return await asyncio.to_thread(
            self._compare_sync, actual_path, golden_path, tolerance, diff_output_path
        )

    def _compare_sync(
        self,
        actual_path: Path,
        golden_path: Path,
        tolerance: float,
        diff_output_path: Path | None,
    ) -> Result[ImageDiff]:
        import cv2
        import numpy as np

        if not actual_path.exists():
            return err(
                VisionFailure(
                    message=f"actual image not found: {actual_path}",
                    next_action="fix_arguments",
                )
            )
        if not golden_path.exists():
            return err(
                VisionFailure(
                    message=f"golden image not found: {golden_path}",
                    next_action="fix_arguments",
                )
            )

        actual = cv2.imread(str(actual_path))
        golden = cv2.imread(str(golden_path))
        if actual is None or golden is None:
            return err(
                VisionFailure(
                    message="could not decode one of the images as a valid format",
                    next_action="review_diff",
                )
            )
        if actual.shape != golden.shape:
            actual = cv2.resize(actual, (golden.shape[1], golden.shape[0]))

        actual_gray = cv2.cvtColor(actual, cv2.COLOR_BGR2GRAY)
        golden_gray = cv2.cvtColor(golden, cv2.COLOR_BGR2GRAY)

        diff = cv2.absdiff(actual_gray, golden_gray)
        threshold = 30
        _, mask = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)
        masked_pixels = int(np.count_nonzero(mask))

        # Similarity: 1 - (fraction of pixels that differ above threshold)
        total = float(mask.size)
        similarity = 1.0 - (masked_pixels / total)
        passed = similarity >= tolerance

        if diff_output_path is not None:
            diff_output_path.parent.mkdir(parents=True, exist_ok=True)
            highlight = actual.copy()
            highlight[mask > 0] = (0, 0, 255)
            cv2.imwrite(str(diff_output_path), highlight)
            # Diff image is returned to the agent as a path → Claude Code
            # auto-embeds. Cap to keep it under the 2000px multi-image
            # limit. Original highlighted diff preserved at `.orig.png`.
            from ..image_capping import cap_image_in_place

            cap_image_in_place(diff_output_path)

        return ok(
            ImageDiff(
                similarity=float(similarity),
                threshold=tolerance,
                passed=bool(passed),
                diff_image_path=diff_output_path,
                masked_pixels=masked_pixels,
            )
        )

    async def detect_markers(
        self, image_path: Path, dictionary: str = "DICT_4X4_50"
    ) -> Result[list[MarkerDetection]]:
        miss = _require_cv2()
        if miss is not None:
            return miss
        return await asyncio.to_thread(self._detect_sync, image_path, dictionary)

    def _detect_sync(
        self, image_path: Path, dictionary: str
    ) -> Result[list[MarkerDetection]]:
        import cv2

        if not image_path.exists():
            return err(
                VisionFailure(
                    message=f"image not found: {image_path}",
                    next_action="fix_arguments",
                )
            )
        if dictionary not in _DICT_NAMES:
            return err(
                VisionFailure(
                    message=f"unsupported dictionary {dictionary!r}",
                    next_action="fix_arguments",
                    details={"supported": list(_DICT_NAMES)},
                )
            )

        img = cv2.imread(str(image_path))
        if img is None:
            return err(
                VisionFailure(
                    message="could not decode image",
                    next_action="review_diff",
                )
            )

        try:
            aruco_dict = cv2.aruco.getPredefinedDictionary(
                getattr(cv2.aruco, dictionary)
            )
            params = cv2.aruco.DetectorParameters()
            detector = cv2.aruco.ArucoDetector(aruco_dict, params)
            corners, ids, _ = detector.detectMarkers(img)
        except AttributeError:
            return err(
                VisionFailure(
                    message="cv2.aruco not available — install opencv-contrib-python",
                    next_action="install_ar_extras",
                )
            )

        if ids is None or len(ids) == 0:
            return ok([])

        results: list[MarkerDetection] = []
        for marker_id, corner_set in zip(ids.flatten().tolist(), corners, strict=False):
            pts = corner_set.reshape(4, 2).astype(int).tolist()
            cx = int(sum(p[0] for p in pts) / 4)
            cy = int(sum(p[1] for p in pts) / 4)
            results.append(
                MarkerDetection(
                    id=int(marker_id),
                    corners=tuple((int(p[0]), int(p[1])) for p in pts),
                    center=(cx, cy),
                )
            )
        return ok(results)

    async def infer_pose(
        self,
        image_path: Path,
        marker_id: int,
        marker_size_m: float,
        camera_matrix=None,
    ) -> Result[Pose]:
        miss = _require_cv2()
        if miss is not None:
            return miss
        return await asyncio.to_thread(
            self._pose_sync, image_path, marker_id, marker_size_m, camera_matrix
        )

    def _pose_sync(
        self,
        image_path: Path,
        marker_id: int,
        marker_size_m: float,
        camera_matrix,
    ) -> Result[Pose]:
        import cv2
        import numpy as np

        detect = self._detect_sync(image_path, "DICT_4X4_50")
        if detect.is_err:
            return detect  # type: ignore[return-value]
        markers = detect.value  # type: ignore[union-attr]
        target = next((m for m in markers if m.id == marker_id), None)
        if target is None:
            return err(
                VisionFailure(
                    message=f"marker {marker_id} not present in image",
                    next_action="check_lighting",
                )
            )

        if camera_matrix is None:
            img = cv2.imread(str(image_path))
            h, w = img.shape[:2]
            fx = fy = float(w)  # rough default; user should supply real intrinsics
            cx, cy = w / 2.0, h / 2.0
            cam = np.array(
                [[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype=np.float64
            )
        else:
            cam = np.array(camera_matrix, dtype=np.float64)

        dist = np.zeros(5, dtype=np.float64)
        s = float(marker_size_m) / 2.0
        obj_pts = np.array(
            [[-s, s, 0], [s, s, 0], [s, -s, 0], [-s, -s, 0]], dtype=np.float64
        )
        img_pts = np.array(target.corners, dtype=np.float64)
        ok_flag, rvec, tvec = cv2.solvePnP(
            obj_pts, img_pts, cam, dist, flags=cv2.SOLVEPNP_IPPE_SQUARE
        )
        if not ok_flag:
            return err(VisionFailure(message="solvePnP failed", next_action="calibrate_stand"))
        return ok(
            Pose(
                rvec=tuple(float(v) for v in rvec.flatten()),
                tvec=tuple(float(v) for v in tvec.flatten()),
                marker_id=marker_id,
            )
        )

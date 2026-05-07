"""Cap PNG dimensions to stay under provider per-image limits.

Claude rejects multi-image conversations where any image exceeds 2000px
on the long edge. Local vision models (LLaVA, Qwen-VL) work best at
≤1024px. Default cap of 1920 is safe across all current providers.

Originals stay on disk under `<screenshot>.orig.png` so visual-diff
flows (compare_screenshot, golden image checks) can still resolve full
resolution via fetch_artifact when needed.

Optional cv2 dep via the `[ar]` extra. Fails open with a logged
warning if cv2 isn't importable — better to return an over-cap image
than to break the screenshot pipeline.
"""

from __future__ import annotations

import os
import shutil
from importlib.util import find_spec
from pathlib import Path

DEFAULT_MAX_DIM = 1920


def _max_dim() -> int:
    raw = os.environ.get("MCP_MAX_IMAGE_DIM", "")
    if not raw:
        return DEFAULT_MAX_DIM
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_DIM
    return value  # 0 disables capping


def prefer_original(path: Path) -> Path:
    """Return `<path>.orig.png` if it exists, else `path` unchanged.

    Visual-diff workflows (compare_screenshot, golden image checks)
    should always read from this so capping doesn't degrade their
    accuracy. Capping happens for vision-model context budget — diff
    math wants the full sensor.
    """
    original = path.with_suffix(".orig.png")
    return original if original.exists() else path


def cap_image_in_place(path: Path, max_dim: int | None = None) -> bool:
    """Resize `path` so its long edge ≤ max_dim. Returns True if resized.

    Idempotent on already-capped images (no-op when both dims are
    already within bounds). Preserves the original at `<path>.orig.png`
    on the first call so visual-diff workflows have full resolution.
    """
    cap = _max_dim() if max_dim is None else max_dim
    if cap <= 0:
        return False
    if find_spec("cv2") is None:
        # Fail open — over-cap image is better than broken pipeline.
        return False
    import cv2  # local import; only when actually capping

    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        return False
    h, w = img.shape[:2]
    longest = max(h, w)
    if longest <= cap:
        return False
    # Snapshot the original on first cap.
    original = path.with_suffix(".orig.png")
    if not original.exists():
        try:
            shutil.copy2(path, original)
        except OSError:
            pass  # not fatal; capping still proceeds
    scale = cap / longest
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(path), resized)
    return True

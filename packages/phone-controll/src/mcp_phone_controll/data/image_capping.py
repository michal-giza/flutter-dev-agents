"""Cap PNG dimensions to stay under provider per-image limits.

Claude rejects multi-image conversations where any image exceeds 2000px
on the long edge. Local vision models (LLaVA, Qwen-VL) work best at
≤1024px. Default cap of 1920 is safe across all current providers.

Three backends, tried in order — first one that works wins:

  1. **cv2** (OpenCV) — best quality, but requires the `[ar]` extra
     (~80 MB install). Available when the project is set up for
     AR/Vision work.
  2. **PIL** (Pillow) — lighter, often already pulled in by other
     deps. Quality slightly worse than cv2 on photo content; fine
     for UI screenshots.
  3. **sips** — macOS-native, zero Python deps. Always available on
     a developer Mac. The defaulting layer for the common case.

If all three fail (Linux box without cv2/PIL), `cap_image_in_place`
returns False AND logs a clear stderr warning so the user knows the
cap is non-functional. Together with the dispatcher's hard guard
(see `presentation/image_safety_net.py`), this guarantees the
2000px limit is never silently violated.

Originals stay on disk at `<path>.orig.png` so visual-diff workflows
have full resolution.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
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


# ---- dimension probing (no deps) ----------------------------------------


def _read_png_dimensions(path: Path) -> tuple[int, int] | None:
    """Read PNG IHDR width/height without any image library. Returns None
    if the file isn't a valid PNG header."""
    try:
        with path.open("rb") as fh:
            header = fh.read(24)
    except OSError:
        return None
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    width = int.from_bytes(header[16:20], "big")
    height = int.from_bytes(header[20:24], "big")
    return (width, height)


# ---- per-backend resize implementations ---------------------------------


def _resize_cv2(path: Path, new_w: int, new_h: int) -> bool:
    if find_spec("cv2") is None:
        return False
    try:
        import cv2

        img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if img is None:
            return False
        resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        return bool(cv2.imwrite(str(path), resized))
    except Exception as exc:
        print(f"[image_capping] cv2 resize failed: {exc}", file=sys.stderr)
        return False


def _resize_pil(path: Path, new_w: int, new_h: int) -> bool:
    if find_spec("PIL") is None:
        return False
    try:
        from PIL import Image

        with Image.open(path) as img:
            resized = img.resize((new_w, new_h), Image.LANCZOS)
            resized.save(path, format="PNG")
        return True
    except Exception as exc:
        print(f"[image_capping] PIL resize failed: {exc}", file=sys.stderr)
        return False


def _resize_sips(path: Path, cap: int) -> bool:
    """macOS `sips -Z` resizes the longest dimension to `cap` in place.

    Doesn't need explicit new_w/new_h — sips does the math itself. Only
    available on macOS; returns False on other platforms.
    """
    if not shutil.which("sips"):
        return False
    try:
        result = subprocess.run(
            ["sips", "-Z", str(cap), str(path)],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"[image_capping] sips resize failed: {exc}", file=sys.stderr)
        return False


# ---- the public entry point ---------------------------------------------


def cap_image_in_place(path: Path, max_dim: int | None = None) -> bool:
    """Resize `path` so its long edge ≤ max_dim. Returns True if resized.

    Idempotent on already-capped images (no-op when both dims are
    already within bounds). Preserves the original at `<path>.orig.png`
    on the first call.

    Tries cv2 → PIL → sips. If all three fail (and the image is over
    cap), logs to stderr — the dispatcher's hard guard will refuse to
    return the path in that case.
    """
    cap = _max_dim() if max_dim is None else max_dim
    if cap <= 0:
        return False
    dims = _read_png_dimensions(path)
    if dims is None:
        return False
    w, h = dims
    longest = max(w, h)
    if longest <= cap:
        return False

    # Snapshot the original on first cap.
    original = path.with_suffix(".orig.png")
    if not original.exists():
        try:
            shutil.copy2(path, original)
        except OSError as exc:
            print(
                f"[image_capping] failed to preserve original {path}: {exc}",
                file=sys.stderr,
            )
            # Continue anyway — losing the original is worse than failing
            # to cap, but capping is what protects the conversation.

    scale = cap / longest
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))

    # Try backends in order. First successful one wins.
    for backend in (
        lambda: _resize_cv2(path, new_w, new_h),
        lambda: _resize_pil(path, new_w, new_h),
        lambda: _resize_sips(path, cap),
    ):
        if backend():
            return True

    # All three failed.
    print(
        f"[image_capping] CAP FAILED for {path} ({w}x{h} → wanted ≤{cap}px). "
        "Install one of: cv2 (`uv pip install -e '.[ar]'`), "
        "Pillow (`uv pip install pillow`), or run on macOS where `sips` is "
        "available by default. The dispatcher will refuse to return this "
        "path until the cap succeeds.",
        file=sys.stderr,
    )
    return False


def is_within_cap(path: Path, max_dim: int | None = None) -> bool:
    """Verification helper: True if `path` is a PNG whose long edge ≤ cap.

    Used by the dispatcher seatbelt to verify cap success before
    returning a path to the agent. Returns True for non-PNG files
    (they don't trigger the multi-image limit).
    """
    cap = _max_dim() if max_dim is None else max_dim
    if cap <= 0:
        return True
    dims = _read_png_dimensions(path)
    if dims is None:
        # Not a PNG or unreadable — let it pass; multi-image limit only
        # affects images Claude can decode.
        return True
    return max(dims) <= cap

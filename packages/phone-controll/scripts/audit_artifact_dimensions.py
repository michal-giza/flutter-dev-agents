"""List every PNG in the artifacts dir whose long edge exceeds the cap.

When Claude refuses a conversation because of the 2000px multi-image
limit, the offending images are usually leftovers from a previous
session captured before the cap fix landed. Run this script to find
and (optionally) cap them:

    python -m scripts.audit_artifact_dimensions             # list only
    python -m scripts.audit_artifact_dimensions --cap       # cap them
    python -m scripts.audit_artifact_dimensions --cap --root ~/other/sessions

Skips files under `release/` (intentionally full-res for store
listings) and `tests/fixtures/golden/` (intentionally full-res for
visual diff). Skips `.orig.png` companions (those should stay full-res).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_DEFAULT_ROOT = Path.home() / ".mcp_phone_controll" / "sessions"


def _read_png_dims(path: Path) -> tuple[int, int]:
    try:
        with path.open("rb") as fh:
            header = fh.read(24)
    except OSError:
        return (0, 0)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return (0, 0)
    return (
        int.from_bytes(header[16:20], "big"),
        int.from_bytes(header[20:24], "big"),
    )


def _should_skip(path: Path) -> bool:
    parts = set(path.parts)
    if "release" in parts:
        return True
    if "golden" in parts:
        return True
    if path.name.endswith(".orig.png"):
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=_DEFAULT_ROOT)
    ap.add_argument("--cap", action="store_true", help="Cap oversized PNGs in place.")
    ap.add_argument("--max-dim", type=int, default=1600)
    ap.add_argument(
        "--max-bytes-kb",
        type=int,
        default=250,
        help=(
            "Recompress (palette + max zlib) any PNG larger than this in KB. "
            "Requires --cap. The upstream API enforces a 32 MB total request "
            "size; agents accumulating ~30+ screenshots per session hit that "
            "even with dimensions capped."
        ),
    )
    args = ap.parse_args()

    if not args.root.is_dir():
        print(f"artifacts root not found: {args.root}", file=sys.stderr)
        return 2

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

    oversized: list[tuple[Path, int, int]] = []
    heavy: list[tuple[Path, int]] = []  # (path, size_kb) — within dims, over bytes
    total = 0
    for png in args.root.rglob("*.png"):
        if _should_skip(png):
            continue
        total += 1
        w, h = _read_png_dims(png)
        if max(w, h) > args.max_dim:
            oversized.append((png, w, h))
            continue
        try:
            size_kb = png.stat().st_size // 1024
        except OSError:
            continue
        if size_kb > args.max_bytes_kb:
            heavy.append((png, size_kb))

    print(f"scanned {total} PNG(s) under {args.root}")
    print(f"oversized (long edge > {args.max_dim}): {len(oversized)}")
    for path, w, h in oversized:
        rel = path.relative_to(args.root)
        print(f"  {w}x{h}  {rel}")
    print(f"heavy (size > {args.max_bytes_kb} KB): {len(heavy)}")
    for path, size_kb in heavy[:20]:
        rel = path.relative_to(args.root)
        print(f"  {size_kb} KB  {rel}")
    if len(heavy) > 20:
        print(f"  ... and {len(heavy) - 20} more")

    if args.cap:
        from importlib.util import find_spec

        from mcp_phone_controll.data.image_capping import (
            cap_image_in_place,
            compress_png_in_place,
        )

        if oversized and find_spec("cv2") is None and find_spec("PIL") is None:
            print(
                "\n--cap requested but no image backend installed. "
                "Install Pillow: uv pip install pillow",
                file=sys.stderr,
            )
            return 1

        capped = 0
        for path, _w, _h in oversized:
            if cap_image_in_place(path, max_dim=args.max_dim):
                capped += 1
        if oversized:
            print(f"\ncapped {capped} of {len(oversized)} files.")
            print("originals preserved at <path>.orig.png.")

        recompressed = 0
        saved_kb = 0
        for path, size_kb in heavy:
            if compress_png_in_place(path):
                try:
                    new_kb = path.stat().st_size // 1024
                    saved_kb += max(0, size_kb - new_kb)
                    recompressed += 1
                except OSError:
                    pass
        if heavy:
            print(
                f"recompressed {recompressed} of {len(heavy)} heavy files "
                f"(saved ~{saved_kb} KB total)."
            )

    if (oversized or heavy) and not args.cap:
        print("\nrun with --cap to resize/recompress them in place.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""ocr_screenshot — extract text from a PNG without burning a vision call.

Modern visual-UI agents (CogAgent, ShowUI, etc.) operate over a
combination of OCR + a structured UI graph. For a text-only LLM
driving phone-controll, this tool is the cheapest way to "see" the
contents of a screen without a multimodal model.

Three backends, tried in order:

  1. **macOS Vision** via the `shortcuts` command or `vision-cli` if
     installed. Best quality, free, on-device, no extra dep on a Mac.
  2. **pytesseract** (Tesseract CLI wrapper) — cross-platform; needs
     `brew install tesseract`. Solid for printed text.
  3. **easyocr** — Python deep-learning OCR. Heavier install but works
     anywhere.

If none is available, returns an `OcrUnavailableFailure` with
`next_action="install_ocr_backend"` so the agent knows what to do.

The cap interaction: OCR reads from `prefer_original(path)` — full
resolution gives better recognition. The capped version is what
Claude embeds, but our diff/OCR math always uses the original.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path

from ..failures import VisionFailure
from ..result import Result, err, ok
from .base import BaseUseCase


@dataclass(frozen=True, slots=True)
class OcrScreenshotParams:
    path: Path
    languages: tuple[str, ...] = ("eng",)
    min_confidence: float = 0.0   # easyocr emits per-line conf; tesseract doesn't


@dataclass(frozen=True, slots=True)
class OcrTextSpan:
    text: str
    confidence: float | None    # None when backend doesn't report it
    bbox: tuple[int, int, int, int] | None


@dataclass(frozen=True, slots=True)
class OcrResult:
    backend: str
    text: str                   # joined newline-separated
    spans: tuple[OcrTextSpan, ...]
    word_count: int


class OcrScreenshot(BaseUseCase[OcrScreenshotParams, OcrResult]):
    """Run OCR on a PNG; return joined text + per-span breakdown."""

    async def execute(self, params: OcrScreenshotParams) -> Result[OcrResult]:
        from ...data.image_capping import prefer_original

        path = prefer_original(Path(params.path).expanduser())
        if not path.is_file():
            return err(
                VisionFailure(
                    message=f"image not found: {path}",
                    next_action="check_path",
                )
            )

        for backend in (_macos_vision, _pytesseract, _easyocr):
            res = backend(path, params)
            if res is not None:
                return ok(res)

        return err(
            VisionFailure(
                message=(
                    "no OCR backend available. Install one of: macOS "
                    "shortcuts ('Get text from image'), Tesseract "
                    "(`brew install tesseract && pip install pytesseract`), "
                    "or easyocr (`pip install easyocr`)."
                ),
                next_action="install_ocr_backend",
            )
        )


# ---- backends -----------------------------------------------------------


def _macos_vision(path: Path, params: OcrScreenshotParams) -> OcrResult | None:
    """Use a small Swift one-liner via `osascript` to drive
    VNRecognizeTextRequest. Cheap and good on text-heavy screens.

    Requires macOS. Returns None on any failure so the next backend
    can try.
    """
    if not shutil.which("osascript"):
        return None
    # Sneak the path through a here-doc; AppleScript shells out to
    # `vision-cli` if installed (most reliable), else we skip.
    if not shutil.which("vision-cli"):
        # No Swift compiler available without pyobjc; defer to other
        # backends. Returning None lets _pytesseract try next.
        return None
    try:
        result = subprocess.run(
            ["vision-cli", "text", str(path)],
            capture_output=True,
            timeout=15,
            text=True,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    text = result.stdout.strip()
    if not text:
        return None
    spans = tuple(OcrTextSpan(text=line, confidence=None, bbox=None)
                  for line in text.splitlines() if line.strip())
    return OcrResult(
        backend="macos-vision",
        text=text,
        spans=spans,
        word_count=sum(len(s.text.split()) for s in spans),
    )


def _pytesseract(path: Path, params: OcrScreenshotParams) -> OcrResult | None:
    if find_spec("pytesseract") is None or not shutil.which("tesseract"):
        return None
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return None
    lang = "+".join(params.languages)
    try:
        with Image.open(path) as img:
            text = pytesseract.image_to_string(img, lang=lang).strip()
    except Exception:
        return None
    if not text:
        return None
    spans = tuple(OcrTextSpan(text=line, confidence=None, bbox=None)
                  for line in text.splitlines() if line.strip())
    return OcrResult(
        backend="pytesseract",
        text=text,
        spans=spans,
        word_count=sum(len(s.text.split()) for s in spans),
    )


def _easyocr(path: Path, params: OcrScreenshotParams) -> OcrResult | None:
    if find_spec("easyocr") is None:
        return None
    try:
        import easyocr  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        reader = easyocr.Reader(list(params.languages), gpu=False, verbose=False)
        rows = reader.readtext(str(path))
    except Exception:
        return None
    spans: list[OcrTextSpan] = []
    for bbox_pts, span_text, conf in rows:
        if conf < params.min_confidence:
            continue
        # bbox_pts is 4 corners; reduce to (x1,y1,x2,y2).
        xs = [int(p[0]) for p in bbox_pts]
        ys = [int(p[1]) for p in bbox_pts]
        spans.append(
            OcrTextSpan(
                text=str(span_text),
                confidence=float(conf),
                bbox=(min(xs), min(ys), max(xs), max(ys)),
            )
        )
    if not spans:
        return None
    joined = "\n".join(s.text for s in spans)
    return OcrResult(
        backend="easyocr",
        text=joined,
        spans=tuple(spans),
        word_count=sum(len(s.text.split()) for s in spans),
    )

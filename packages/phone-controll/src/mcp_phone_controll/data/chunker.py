"""Language-aware chunker. Pure Python, zero deps.

Inspired by the Dart-aware chunker in `rag-search/codebase-rag/ai_project_root`,
but simplified for the in-tree indexing path:

  - .md   → split on H1/H2 headings (preserve heading as anchor)
  - .dart → split on `class `, `void main(`, top-level functions
  - .py   → split on top-level `def `/`class `
  - else  → fixed-size 600-char windows with 100-char overlap

Each chunk is metadata-tagged so `recall(scope=...)` can filter cleanly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Chunk:
    text: str
    language: str
    char_start: int
    char_end: int


_DEFAULT_CHUNK_CHARS = 600
_DEFAULT_OVERLAP = 100
_MIN_CHUNK_CHARS = 80      # discard sub-paragraph fragments


_LANG_BY_SUFFIX = {
    ".md": "markdown",
    ".dart": "dart",
    ".py": "python",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
}


def language_for(path: Path) -> str:
    return _LANG_BY_SUFFIX.get(path.suffix.lower(), "text")


class LanguageAwareChunker:
    """Split text into Chunks based on file language.

    The chunker is deliberately conservative: it never produces chunks
    smaller than `_MIN_CHUNK_CHARS`, never larger than ~2× the target.
    """

    def __init__(
        self,
        chunk_chars: int = _DEFAULT_CHUNK_CHARS,
        overlap: int = _DEFAULT_OVERLAP,
    ) -> None:
        self._chunk_chars = chunk_chars
        self._overlap = overlap

    def chunk(self, text: str, path: Path) -> list[Chunk]:
        lang = language_for(path)
        if lang == "markdown":
            return self._chunk_markdown(text)
        if lang == "dart":
            return self._chunk_dart(text)
        if lang == "python":
            return self._chunk_python(text)
        return self._chunk_fixed(text, lang)

    # ---- per-language strategies ---------------------------------------

    def _chunk_markdown(self, text: str) -> list[Chunk]:
        # Split on H1/H2 boundaries; preserve the heading line at the top
        # of each chunk so retrieval surfaces "Section: …".
        parts = re.split(r"(?m)^(#{1,2} .+)$", text)
        chunks: list[Chunk] = []
        cursor = 0
        # `parts` alternates [pre, heading, body, heading, body, ...]
        if parts and not parts[0].strip():
            parts = parts[1:]
        i = 0
        while i < len(parts):
            piece = parts[i]
            if i + 1 < len(parts):
                piece = piece + "\n" + parts[i + 1]
                i += 2
            else:
                i += 1
            piece = piece.strip()
            if len(piece) < _MIN_CHUNK_CHARS:
                continue
            chunks.append(
                Chunk(
                    text=piece,
                    language="markdown",
                    char_start=cursor,
                    char_end=cursor + len(piece),
                )
            )
            cursor += len(piece)
        if not chunks:
            return self._chunk_fixed(text, "markdown")
        return chunks

    _DART_BOUNDARIES = re.compile(
        r"(?m)^(?:class\s+\w|abstract\s+class\s+\w|void\s+main\b|"
        r"[A-Za-z_][A-Za-z0-9_]*\s+[A-Za-z_][A-Za-z0-9_]*\s*\()"
    )

    def _chunk_dart(self, text: str) -> list[Chunk]:
        return self._chunk_by_regex(text, self._DART_BOUNDARIES, "dart")

    _PY_BOUNDARIES = re.compile(r"(?m)^(?:def\s+\w|async\s+def\s+\w|class\s+\w)")

    def _chunk_python(self, text: str) -> list[Chunk]:
        return self._chunk_by_regex(text, self._PY_BOUNDARIES, "python")

    def _chunk_by_regex(
        self, text: str, boundary: re.Pattern, language: str
    ) -> list[Chunk]:
        starts = [m.start() for m in boundary.finditer(text)]
        if not starts:
            return self._chunk_fixed(text, language)
        starts.append(len(text))
        chunks: list[Chunk] = []
        for s, e in zip(starts, starts[1:]):
            piece = text[s:e].strip()
            if len(piece) < _MIN_CHUNK_CHARS:
                continue
            # Keep chunks bounded — split very large class/function bodies
            # into fixed-size windows so we don't exceed embed-token limits.
            if len(piece) > 2 * self._chunk_chars:
                for sub in self._split_fixed(piece, language, base_offset=s):
                    chunks.append(sub)
            else:
                chunks.append(
                    Chunk(
                        text=piece,
                        language=language,
                        char_start=s,
                        char_end=s + len(piece),
                    )
                )
        if not chunks:
            return self._chunk_fixed(text, language)
        return chunks

    def _chunk_fixed(self, text: str, language: str) -> list[Chunk]:
        return list(self._split_fixed(text, language, base_offset=0))

    def _split_fixed(self, text: str, language: str, base_offset: int):
        if not text.strip():
            return
        step = max(1, self._chunk_chars - self._overlap)
        for start in range(0, len(text), step):
            end = min(start + self._chunk_chars, len(text))
            piece = text[start:end].strip()
            if len(piece) < _MIN_CHUNK_CHARS:
                continue
            yield Chunk(
                text=piece,
                language=language,
                char_start=base_offset + start,
                char_end=base_offset + end,
            )
            if end == len(text):
                break

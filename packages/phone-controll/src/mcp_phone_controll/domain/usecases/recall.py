"""recall + index_project — retrieval-augmented agent context.

Why this exists: the SKILL.md file an autonomous agent loads is ~8 KB.
For 4B-class local models, that's a 30%+ context-budget hit before any
tool runs. Loading is also blunt: most steps need 2-3 paragraphs of the
SKILL, not the whole thing.

`recall(query, k, scope)` lets the agent fetch only the chunks that
match its current question. `index_project(project_path)` populates the
RAG backend from project source + docs + the SKILL itself.

Grounding:
- Lewis et al., 2020, arXiv 2005.11401 (RAG): retrieve-then-generate
  beats parametric-only models on knowledge-intensive tasks.
- Liu et al., 2023, arXiv 2307.03172 ("Lost in the Middle"): long
  contexts surface mid-document content unreliably; short retrieved
  chunks are recovered far better than long monolithic prompts.
- Gao et al., 2023, arXiv 2312.10997: a survey establishing chunked
  retrieval over agent tool descriptions as a load-bearing pattern.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..entities import IndexStats, RecallChunk
from ..failures import RagIndexingFailure, RagUnavailableFailure
from ..repositories import RagRepository
from ..result import Err, Result, err, ok
from .base import BaseUseCase


_VALID_SCOPES = frozenset({"skill", "docs", "trace", "code", "all"})


@dataclass(frozen=True, slots=True)
class RecallParams:
    query: str
    k: int = 3
    scope: str = "all"


class Recall(BaseUseCase[RecallParams, list[RecallChunk]]):
    """Retrieve top-k chunks matching the query within an optional scope."""

    def __init__(self, rag: RagRepository) -> None:
        self._rag = rag

    async def execute(self, params: RecallParams) -> Result[list[RecallChunk]]:
        if not params.query.strip():
            return err(
                RagIndexingFailure(
                    message="recall requires a non-empty query",
                    next_action="fix_arguments",
                )
            )
        if params.scope not in _VALID_SCOPES:
            return err(
                RagIndexingFailure(
                    message=f"invalid scope {params.scope!r}",
                    next_action="fix_arguments",
                    details={
                        "valid_scopes": sorted(_VALID_SCOPES),
                        "corrected_example": {
                            "query": params.query,
                            "scope": "all",
                        },
                    },
                )
            )
        if params.k < 1 or params.k > 20:
            return err(
                RagIndexingFailure(
                    message="k must be between 1 and 20",
                    next_action="fix_arguments",
                )
            )
        return await self._rag.recall(params.query, params.k, params.scope)


@dataclass(frozen=True, slots=True)
class IndexProjectParams:
    project_path: Path
    collection: str = "phone-controll-default"
    include_globs: tuple[str, ...] = ("**/*.md", "**/*.dart", "**/*.py")
    exclude_globs: tuple[str, ...] = (
        "**/.git/**",
        "**/build/**",
        "**/.dart_tool/**",
        "**/node_modules/**",
        "**/.venv/**",
    )


class IndexProject(BaseUseCase[IndexProjectParams, IndexStats]):
    """Walk a project, chunk discovered files, push them into the RAG repo.

    Idempotent on (collection, source-path) — re-indexing a file replaces
    its chunks. Designed to run once per session, or on a watcher.
    """

    def __init__(self, rag: RagRepository, chunker) -> None:
        self._rag = rag
        self._chunker = chunker

    async def execute(self, params: IndexProjectParams) -> Result[IndexStats]:
        project = Path(params.project_path).expanduser()
        if not project.is_dir():
            return err(
                RagIndexingFailure(
                    message=f"not a directory: {project}",
                    next_action="check_path",
                )
            )
        avail = await self._rag.is_available()
        if isinstance(avail, Err):
            return avail
        items: list[tuple[str, str, dict]] = []
        skipped: list[str] = []
        for path in _walk(project, params.include_globs, params.exclude_globs):
            try:
                text = path.read_text(errors="replace")
            except OSError:
                skipped.append(str(path.relative_to(project)))
                continue
            for chunk in self._chunker.chunk(text, path):
                items.append(
                    (
                        chunk.text,
                        str(path.relative_to(project)),
                        {
                            "language": chunk.language,
                            "char_start": chunk.char_start,
                            "char_end": chunk.char_end,
                            "scope": _scope_for_path(path),
                        },
                    )
                )
        if not items:
            return err(
                RagIndexingFailure(
                    message="no indexable content found",
                    next_action="check_globs",
                    details={
                        "include_globs": list(params.include_globs),
                        "skipped": skipped[:20],
                    },
                )
            )
        upsert_res = await self._rag.index_collection(params.collection, items)
        if isinstance(upsert_res, Err):
            return upsert_res
        stats = upsert_res.value
        return ok(
            IndexStats(
                collection=stats.collection,
                files_indexed=stats.files_indexed,
                chunks_indexed=stats.chunks_indexed,
                skipped=tuple(skipped),
                duration_ms=stats.duration_ms,
            )
        )


# --- helpers --------------------------------------------------------------


def _walk(
    project: Path,
    include_globs: tuple[str, ...],
    exclude_globs: tuple[str, ...],
):
    """Yield paths under `project` matching include and not exclude."""
    seen: set[Path] = set()
    for pattern in include_globs:
        for path in project.glob(pattern):
            if not path.is_file() or path in seen:
                continue
            rel = path.relative_to(project).as_posix()
            if any(_match_glob(rel, ex) for ex in exclude_globs):
                continue
            seen.add(path)
            yield path


def _match_glob(rel_path: str, pattern: str) -> bool:
    # Strip leading `**/` since we test against project-relative paths.
    if pattern.startswith("**/"):
        pattern = pattern[3:]
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return rel_path.startswith(prefix + "/") or rel_path == prefix
    from fnmatch import fnmatch

    return fnmatch(rel_path, pattern)


def _scope_for_path(path: Path) -> str:
    name = path.name.lower()
    parts = {p.lower() for p in path.parts}
    if name == "skill.md" or name == "skill-basic.md":
        return "skill"
    if "docs" in parts or path.suffix == ".md":
        return "docs"
    return "code"

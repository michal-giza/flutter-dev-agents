"""Artifact retention — pruning stale `.orig.png` companions + disk usage.

Every capped screenshot preserves an `<path>.orig.png` companion so
visual-diff workflows keep full resolution. Across a busy week these
add up — the user's tree showed 165 of them by the time we ran the
audit.

Two surfaces:

  - `disk_usage()` — total bytes + per-bucket breakdown (screenshots,
    .orig.png companions, logs, recordings, goldens, release).
  - `prune_originals(older_than_days, dry_run)` — delete `.orig.png`
    files whose mtime is older than the threshold. Defaults to 14
    days; configurable via `MCP_ORIG_RETENTION_DAYS`.

Conservative by design: only `.orig.png` files are eligible for
pruning, never the capped screenshot, never goldens, never
release-mode files. The agent gets clear `next_action` hints
("review_prune_target") so it never silently nukes data.

Inspired by the same "fix once, every consumer benefits" pattern we
used for the image cap. Run on `release_device` for automatic
hygiene, or invoke explicitly.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from ..failures import FilesystemFailure
from ..repositories import ArtifactRepository
from ..result import Err, Result, err, ok
from .base import BaseUseCase

# Default retention window. Conservative — long enough to recover a
# previous session's full-res image; short enough that a busy month
# doesn't accumulate gigabytes.
_DEFAULT_RETENTION_DAYS = 14


def _retention_days() -> int:
    raw = os.environ.get("MCP_ORIG_RETENTION_DAYS", "")
    if not raw:
        return _DEFAULT_RETENTION_DAYS
    try:
        return max(0, int(raw))
    except ValueError:
        return _DEFAULT_RETENTION_DAYS


# ---------------- disk_usage ---------------------------------------------


@dataclass(frozen=True, slots=True)
class DiskUsageBucket:
    name: str
    bytes: int
    file_count: int


@dataclass(frozen=True, slots=True)
class DiskUsageReport:
    root: Path
    total_bytes: int
    total_files: int
    buckets: tuple[DiskUsageBucket, ...]


class DiskUsage(BaseUseCase):
    """Walk the artifacts root and report bytes used per bucket.

    Buckets:
      - screenshots          *.png excluding .orig.png/golden/release
      - originals            *.orig.png
      - goldens              under tests/fixtures/golden/ anywhere
      - release              under release/ subdirs
      - logs                 *.log / *.txt
      - recordings           *.mp4 / *.mov / *.webm
      - other                everything else
    """

    def __init__(self, artifacts: ArtifactRepository) -> None:
        self._artifacts = artifacts

    async def execute(self, _params) -> Result[DiskUsageReport]:
        session_res = await self._artifacts.current_session()
        if isinstance(session_res, Err):
            return session_res
        root = session_res.value.root.parent  # sessions/ root, not this run
        if not root.is_dir():
            return err(
                FilesystemFailure(
                    message=f"artifacts root not found: {root}",
                    next_action="check_path",
                )
            )
        buckets: dict[str, list[int]] = {
            "screenshots": [], "originals": [], "goldens": [],
            "release": [], "logs": [], "recordings": [], "other": [],
        }
        total_files = 0
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            total_files += 1
            buckets[_bucket_for(path)].append(path.stat().st_size)
        total_bytes = sum(sum(sizes) for sizes in buckets.values())
        return ok(
            DiskUsageReport(
                root=root,
                total_bytes=total_bytes,
                total_files=total_files,
                buckets=tuple(
                    DiskUsageBucket(name=name, bytes=sum(sizes), file_count=len(sizes))
                    for name, sizes in buckets.items()
                    if sizes
                ),
            )
        )


def _bucket_for(path: Path) -> str:
    name = path.name.lower()
    parts = set(p.lower() for p in path.parts)
    if name.endswith(".orig.png"):
        return "originals"
    if "golden" in parts:
        return "goldens"
    if "release" in parts:
        return "release"
    if name.endswith(".png"):
        return "screenshots"
    if name.endswith((".log", ".txt")):
        return "logs"
    if name.endswith((".mp4", ".mov", ".webm")):
        return "recordings"
    return "other"


# ---------------- prune_originals ----------------------------------------


@dataclass(frozen=True, slots=True)
class PruneOriginalsParams:
    older_than_days: int | None = None  # None → MCP_ORIG_RETENTION_DAYS env or 14
    dry_run: bool = False


@dataclass(frozen=True, slots=True)
class PruneOriginalsResult:
    candidates_found: int
    deleted: int
    bytes_freed: int
    dry_run: bool
    sample_paths: tuple[str, ...]   # up to 10 examples


class PruneOriginals(BaseUseCase[PruneOriginalsParams, PruneOriginalsResult]):
    """Delete `.orig.png` companions older than the retention threshold.

    Conservative: only removes files matching `*.orig.png` whose mtime
    is older than `older_than_days`. Never touches the capped
    screenshot next to them, never touches goldens, never touches
    release-mode files.

    `dry_run=true` lists candidates without deleting — recommended for
    a one-shot manual run before wiring this into automation.
    """

    def __init__(self, artifacts: ArtifactRepository) -> None:
        self._artifacts = artifacts

    async def execute(
        self, params: PruneOriginalsParams
    ) -> Result[PruneOriginalsResult]:
        session_res = await self._artifacts.current_session()
        if isinstance(session_res, Err):
            return session_res
        root = session_res.value.root.parent
        if not root.is_dir():
            return err(
                FilesystemFailure(
                    message=f"artifacts root not found: {root}",
                    next_action="check_path",
                )
            )
        days = params.older_than_days if params.older_than_days is not None else _retention_days()
        if days < 0:
            return err(
                FilesystemFailure(
                    message="older_than_days must be ≥ 0",
                    next_action="fix_arguments",
                )
            )
        cutoff = time.time() - days * 86400
        candidates: list[Path] = []
        for path in root.rglob("*.orig.png"):
            try:
                if path.stat().st_mtime < cutoff:
                    candidates.append(path)
            except OSError:
                continue
        sample = tuple(str(p.relative_to(root)) for p in candidates[:10])
        bytes_freed = 0
        deleted = 0
        if not params.dry_run:
            for path in candidates:
                try:
                    size = path.stat().st_size
                    path.unlink()
                    bytes_freed += size
                    deleted += 1
                except OSError:
                    continue
        else:
            bytes_freed = sum(p.stat().st_size for p in candidates)
        return ok(
            PruneOriginalsResult(
                candidates_found=len(candidates),
                deleted=deleted,
                bytes_freed=bytes_freed,
                dry_run=params.dry_run,
                sample_paths=sample,
            )
        )

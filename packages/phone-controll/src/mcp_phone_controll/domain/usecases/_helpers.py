"""Shared use-case helpers — kept tiny, only the things genuinely repeated."""

from __future__ import annotations

from pathlib import Path

from ..failures import NoDeviceSelectedFailure
from ..repositories import SessionStateRepository
from ..result import Err, Result, err, ok

# Directories every static-audit tool should skip. These are
# generated/cache/vendored locations that flood the scanners
# with duplicates + false positives (build/ contains generated
# manifests; .claude/worktrees/ contains agent worktree copies;
# .dart_tool/ has the pub cache; etc.).
#
# Surfaced by the v0.3.0 field test on mytaskboardapp +
# bike_news_room — see docs/v030-field-test.md.
AUDIT_EXCLUDED_DIRS: frozenset[str] = frozenset({
    "build",          # Flutter / Gradle build output
    ".claude",        # Agent worktrees + state
    ".dart_tool",     # Dart tool cache
    "Pods",           # CocoaPods (under ios/)
    ".gradle",        # Gradle cache (under android/)
    ".git",
    ".svn",
    ".hg",
    "node_modules",
    "DerivedData",    # Xcode-derived data
    ".idea",
    ".vscode",
    "__pycache__",
})


def is_path_excluded(path: Path, project_root: Path) -> bool:
    """Returns True if any path segment between `project_root`
    and `path` is in `AUDIT_EXCLUDED_DIRS`.

    Use in `for f in root.rglob("*")` loops to skip files under
    generated / agent-worktree / vendor directories.
    """
    try:
        rel = path.relative_to(project_root)
    except ValueError:
        # Not under project root — be conservative and exclude.
        return True
    return any(part in AUDIT_EXCLUDED_DIRS for part in rel.parts)


async def resolve_serial(
    explicit: str | None, state: SessionStateRepository
) -> Result[str]:
    if explicit is not None:
        return ok(explicit)
    selected = await state.get_selected_serial()
    if isinstance(selected, Err):
        return selected
    if selected.value is None:
        return err(
            NoDeviceSelectedFailure(
                message="No device selected. Call select_device or pass serial explicitly."
            )
        )
    return ok(selected.value)

"""Shared path-traversal guard for tools that accept arbitrary disk paths.

The first MCP-level audit (May 2026) caught that `compress_png` accepted
any path on disk — an agent or prompt-injected upstream could pass
`~/.ssh/id_rsa.png` and clobber it. We added a per-tool guard there.

This module lifts the guard into a reusable helper so every tool that
takes a `path` argument can consistently enforce the same allowlist.

Default allowlist (always available):
  - `~/.mcp_phone_controll/sessions/`
  - `/tmp/`, `/var/folders/`, `/private/tmp/`, `/private/var/folders/`

Per-call extensions:
  - `extra_roots=` lets the caller add specific dirs (e.g. the active
    project root for `fetch_artifact` operations on build outputs).
  - `MCP_<TOOL_NAME>_ALLOWED_ROOTS` env var (colon-separated) for
    operator-level extensions, e.g. `MCP_FETCH_ARTIFACT_ALLOWED_ROOTS`.

Returns a structured (ok, reason, allowed_roots) tuple so each caller
can build its own failure envelope with the right next_action and
details. Doesn't raise — pure value-returning function.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_ROOTS = [
    Path.home() / ".mcp_phone_controll" / "sessions",
    Path("/tmp"),
    Path("/var/folders"),
    Path("/private/tmp"),
    Path("/private/var/folders"),
]


@dataclass(frozen=True, slots=True)
class PathGuardResult:
    ok: bool
    resolved_path: Path
    allowed_roots: list[Path]
    reason: str | None = None  # populated when ok=False


def is_within(child: Path, parent: Path) -> bool:
    """True iff `child` is `parent` or a descendant. Symlink-aware via
    `resolve()` — call resolve() on both sides BEFORE this helper if
    you want symlink expansion."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def check_path_allowed(
    path: Path,
    *,
    tool_name: str,
    extra_roots: list[Path] | None = None,
    env_var_override: str | None = None,
) -> PathGuardResult:
    """Check that `path` is under an allowed root for `tool_name`.

    `env_var_override` defaults to `MCP_<TOOL_NAME_UPPER>_ALLOWED_ROOTS`
    (colon-separated path list). Pass an explicit value if the tool
    wants a custom env name.

    Resolves symlinks on both `path` and every allowed root so a
    symlinked-out file is caught.
    """
    resolved = path.expanduser().resolve()

    allowed: list[Path] = [r.resolve() for r in _DEFAULT_ROOTS]
    if extra_roots:
        allowed.extend(r.expanduser().resolve() for r in extra_roots)

    env_name = env_var_override or f"MCP_{tool_name.upper()}_ALLOWED_ROOTS"
    extra_env = os.environ.get(env_name, "")
    if extra_env:
        for raw in extra_env.split(":"):
            if raw.strip():
                allowed.append(Path(raw).expanduser().resolve())

    if any(is_within(resolved, root) for root in allowed):
        return PathGuardResult(
            ok=True, resolved_path=resolved, allowed_roots=allowed
        )
    return PathGuardResult(
        ok=False,
        resolved_path=resolved,
        allowed_roots=allowed,
        reason=(
            f"{resolved} is not under an allowed root for {tool_name}. "
            f"Set {env_name} (colon-separated paths) to extend the allowlist."
        ),
    )

"""Version + git-SHA capture so a running MCP subprocess can answer the
question 'are you the code that's on disk?'.

Captured at module import time. If the on-disk code is newer than what's
loaded in memory, the SHA here lags — which is exactly the signal we
want when diagnosing stale-subprocess issues (the recurring pain that
caused the image-cap fix to apparently fail four times).

Fields:
  - package_version  — semver-ish, read from pyproject.toml
  - git_sha          — short SHA of HEAD at startup; "unknown" if not a git tree
  - git_branch       — branch name; "unknown" otherwise
  - git_dirty        — True if there are uncommitted changes at startup
  - started_at       — ISO timestamp captured at import time
  - python_version   — runtime Python (3.11.x etc.)
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

_started_at = datetime.now()
_started_monotonic = time.monotonic()


def _package_version() -> str:
    try:
        from importlib.metadata import version

        return version("mcp_phone_controll")
    except Exception:  # noqa: BLE001
        return "unknown"


def _git_dir() -> Path | None:
    """Walk up from this file looking for a .git dir."""
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        candidate = parent.parent / ".git" if parent.is_file() else parent / ".git"
        if candidate.exists():
            return candidate.parent
    return None


def _git(args: list[str], cwd: Path) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            timeout=3,
            text=True,
        )
        if result.returncode != 0:
            return "unknown"
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return "unknown"


def _git_info() -> dict[str, Any]:
    cwd = _git_dir()
    if cwd is None:
        return {"git_sha": "unknown", "git_branch": "unknown", "git_dirty": False}
    sha = _git(["rev-parse", "--short", "HEAD"], cwd)
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    status = _git(["status", "--porcelain"], cwd)
    return {
        "git_sha": sha,
        "git_branch": branch,
        "git_dirty": bool(status and status != "unknown"),
    }


_VERSION_CACHE: dict[str, Any] = {
    "package_version": _package_version(),
    **_git_info(),
    "started_at": _started_at.isoformat(),
    "python_version": ".".join(str(v) for v in sys.version_info[:3]),
    "pid": os.getpid(),
}


def version_info() -> dict[str, Any]:
    """Return the cached version snapshot + live uptime."""
    return {
        **_VERSION_CACHE,
        "uptime_s": round(time.monotonic() - _started_monotonic, 1),
    }


def boot_self_check_log() -> str:
    """One-line stderr-friendly status line for the boot log."""
    from importlib.util import find_spec
    import shutil

    cv2 = find_spec("cv2") is not None
    pil = find_spec("PIL") is not None
    sips = bool(shutil.which("sips"))
    info = version_info()
    backends = []
    if cv2:
        backends.append("cv2")
    if pil:
        backends.append("PIL")
    if sips:
        backends.append("sips")
    return (
        f"[phone-controll] startup: version={info['package_version']} "
        f"sha={info['git_sha']}{'*' if info['git_dirty'] else ''} "
        f"branch={info['git_branch']} python={info['python_version']} "
        f"image_backends={','.join(backends) or 'NONE'} pid={info['pid']}"
    )

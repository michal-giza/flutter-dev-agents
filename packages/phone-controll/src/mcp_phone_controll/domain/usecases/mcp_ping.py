"""mcp_ping — answers 'is this the code I think it is?'.

Closes the recurring stale-subprocess class of bugs. When the agent
suspects something is off (a tool argument missing, a new feature
absent), it calls `mcp_ping` to learn what version of the MCP is
actually running. Compare against the on-disk SHA via `git rev-parse`
in the project, mismatch → restart Claude Code.

Returns:
  - package_version    semver from pyproject.toml
  - git_sha            short SHA of HEAD at startup
  - git_branch         branch at startup
  - git_dirty          True if working tree had uncommitted changes
  - started_at         ISO timestamp at MCP-subprocess boot
  - uptime_s           seconds since boot
  - python_version     runtime Python
  - pid                process id
  - image_backends     which cap backends are available (cv2/PIL/sips)
  - n_tools            number of registered tools
"""

from __future__ import annotations

from dataclasses import dataclass

from ..result import Result, ok
from .base import BaseUseCase, NoParams


@dataclass(frozen=True, slots=True)
class McpPingResult:
    package_version: str
    git_sha: str
    git_branch: str
    git_dirty: bool
    started_at: str
    uptime_s: float
    python_version: str
    pid: int
    image_backends: tuple[str, ...]
    n_tools: int


class McpPing(BaseUseCase[NoParams, McpPingResult]):
    """Identify the running MCP subprocess.

    Takes a callable returning the descriptor count so we don't import
    the registry from the domain layer.
    """

    def __init__(self, n_tools_provider) -> None:
        self._n_tools_provider = n_tools_provider

    async def execute(self, _params: NoParams) -> Result[McpPingResult]:
        from importlib.util import find_spec
        import shutil

        from ...version_info import version_info

        info = version_info()
        backends: list[str] = []
        if find_spec("cv2") is not None:
            backends.append("cv2")
        if find_spec("PIL") is not None:
            backends.append("PIL")
        if shutil.which("sips"):
            backends.append("sips")
        n_tools = 0
        try:
            n_tools = int(self._n_tools_provider())
        except Exception:  # noqa: BLE001
            n_tools = 0
        return ok(
            McpPingResult(
                package_version=info["package_version"],
                git_sha=info["git_sha"],
                git_branch=info["git_branch"],
                git_dirty=bool(info["git_dirty"]),
                started_at=info["started_at"],
                uptime_s=float(info["uptime_s"]),
                python_version=info["python_version"],
                pid=int(info["pid"]),
                image_backends=tuple(backends),
                n_tools=n_tools,
            )
        )

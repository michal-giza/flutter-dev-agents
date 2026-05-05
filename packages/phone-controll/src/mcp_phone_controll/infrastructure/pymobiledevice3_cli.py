"""Async wrapper around the `pymobiledevice3` CLI.

Lockdown-tier commands (usbmux list, apps install/uninstall) use --udid.
Developer-tier commands (screenshot, dvt launch/kill, syslog live on iOS 17+)
route through tunneld via --tunnel <udid>, which requires:
  - `sudo pymobiledevice3 remote tunneld` running in another terminal
  - DDI mounted (`pymobiledevice3 mounter auto-mount`)
  - Developer Mode ON in iOS Settings
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from .process_runner import ProcessResult, ProcessRunner


def _default_pymobiledevice3_path() -> str:
    """Prefer the venv-installed binary so MCP host PATH doesn't matter.

    pymobiledevice3 ships as a Python entry point in the same venv as our own
    process, so `<sys.executable>/../pymobiledevice3` is the most reliable path.
    Falls back to whatever `shutil.which` finds, then to the bare name.
    """
    venv_candidate = Path(sys.executable).parent / "pymobiledevice3"
    if venv_candidate.exists():
        return str(venv_candidate)
    found = shutil.which("pymobiledevice3")
    return found or "pymobiledevice3"


class PyMobileDevice3Cli:
    def __init__(self, runner: ProcessRunner, binary: str | None = None) -> None:
        self._runner = runner
        self._bin = binary or _default_pymobiledevice3_path()

    # --- lockdown-tier (no tunnel needed) ----------------------------------

    async def usbmux_list(self, timeout_s: float = 10.0) -> ProcessResult:
        return await self._runner.run(
            [self._bin, "usbmux", "list"], timeout_s=timeout_s
        )

    async def install(
        self, udid: str, bundle_path: Path, timeout_s: float = 300.0
    ) -> ProcessResult:
        return await self._runner.run(
            [self._bin, "apps", "install", str(bundle_path), "--udid", udid],
            timeout_s=timeout_s,
        )

    async def uninstall(
        self, udid: str, bundle_id: str, timeout_s: float = 60.0
    ) -> ProcessResult:
        return await self._runner.run(
            [self._bin, "apps", "uninstall", bundle_id, "--udid", udid],
            timeout_s=timeout_s,
        )

    # --- developer-tier (route through tunneld via --tunnel) ---------------

    async def launch(
        self, udid: str, bundle_id: str, timeout_s: float = 30.0
    ) -> ProcessResult:
        return await self._runner.run(
            [self._bin, "developer", "dvt", "launch", bundle_id, "--tunnel", udid],
            timeout_s=timeout_s,
        )

    async def kill(
        self, udid: str, bundle_id: str, timeout_s: float = 15.0
    ) -> ProcessResult:
        return await self._runner.run(
            [self._bin, "developer", "dvt", "kill", bundle_id, "--tunnel", udid],
            timeout_s=timeout_s,
        )

    async def screenshot(
        self, udid: str, output_path: Path, timeout_s: float = 30.0
    ) -> ProcessResult:
        return await self._runner.run(
            [
                self._bin,
                "developer",
                "screenshot",
                str(output_path),
                "--tunnel",
                udid,
            ],
            timeout_s=timeout_s,
        )

    async def syslog_live_stream(self, udid: str):
        """Start a streaming `pymobiledevice3 syslog live` subprocess.

        On iOS 17+, syslog runs over the developer tunnel.
        """
        return await self._runner.stream(
            [self._bin, "syslog", "live", "--tunnel", udid]
        )

    # --- one-shot setup helpers --------------------------------------------

    async def amfi_enable_developer_mode(
        self, udid: str, timeout_s: float = 60.0
    ) -> ProcessResult:
        return await self._runner.run(
            [self._bin, "amfi", "enable-developer-mode", "--udid", udid],
            timeout_s=timeout_s,
        )

    async def mounter_auto_mount(
        self, udid: str, timeout_s: float = 120.0
    ) -> ProcessResult:
        return await self._runner.run(
            [self._bin, "mounter", "auto-mount", "--udid", udid],
            timeout_s=timeout_s,
        )

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
from .tunneld_probe import resolve_rsd


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

    # --- developer-tier (route through tunneld) ----------------------------
    #
    # On iOS 17+, every developer-tier subcommand needs explicit RSD
    # coordinates (`--rsd HOST PORT`). The older `--tunnel UDID` shortcut
    # still works for SOME subcommands in newer pymobiledevice3 builds but
    # not all of them — `developer dvt screenshot` in particular fails with
    # "Failed to start service" unless --rsd is provided. We resolve the
    # RSD endpoint via tunneld's HTTP API first, then fall back to the
    # --tunnel shortcut so older iOS 16 setups still work.

    async def _device_route(self, udid: str) -> list[str]:
        rsd = await resolve_rsd(udid)
        if rsd is not None:
            return ["--rsd", rsd.host, str(rsd.port)]
        return ["--tunnel", udid]

    async def launch(
        self, udid: str, bundle_id: str, timeout_s: float = 30.0
    ) -> ProcessResult:
        route = await self._device_route(udid)
        return await self._runner.run(
            [self._bin, "developer", "dvt", "launch", bundle_id, *route],
            timeout_s=timeout_s,
        )

    async def kill(
        self, udid: str, bundle_id: str, timeout_s: float = 15.0
    ) -> ProcessResult:
        route = await self._device_route(udid)
        return await self._runner.run(
            [self._bin, "developer", "dvt", "kill", bundle_id, *route],
            timeout_s=timeout_s,
        )

    async def screenshot(
        self, udid: str, output_path: Path, timeout_s: float = 30.0
    ) -> ProcessResult:
        """Capture a screenshot via the DVT screenshot service.

        Uses `developer dvt screenshot` (NOT `developer screenshot` — the
        latter is the deprecated lockdown API Apple removed on iOS 17+ and
        returns "service unavailable" even with --rsd). DVT route requires
        tunneld + DDI mounted + Developer Mode ON.
        """
        route = await self._device_route(udid)
        return await self._runner.run(
            [
                self._bin,
                "developer",
                "dvt",
                "screenshot",
                str(output_path),
                *route,
            ],
            timeout_s=timeout_s,
        )

    async def syslog_live_stream(self, udid: str):
        """Start a streaming `pymobiledevice3 syslog live` subprocess.

        On iOS 17+, syslog runs over the developer tunnel.
        """
        route = await self._device_route(udid)
        return await self._runner.stream(
            [self._bin, "syslog", "live", *route]
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

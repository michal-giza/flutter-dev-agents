"""Async wrapper around `xcrun simctl` for iOS Simulator control.

Simulators are managed entirely by Xcode's command-line tools — they never
appear in pymobiledevice3 because they don't speak usbmuxd. Every method
here defers to `xcrun simctl` and returns a structured `ProcessResult`.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .process_runner import ProcessResult, ProcessRunner


def _default_simctl_path() -> str:
    found = shutil.which("xcrun")
    return found or "xcrun"


class SimctlClient:
    def __init__(self, runner: ProcessRunner, xcrun_path: str | None = None) -> None:
        self._runner = runner
        self._xcrun = xcrun_path or _default_simctl_path()

    @property
    def binary(self) -> str:
        return self._xcrun

    # ----- discovery -----------------------------------------------------

    async def list_devices_json(self, timeout_s: float = 10.0) -> ProcessResult:
        return await self._runner.run(
            [self._xcrun, "simctl", "list", "devices", "--json"], timeout_s=timeout_s
        )

    # ----- lifecycle -----------------------------------------------------

    async def boot(self, udid: str, timeout_s: float = 60.0) -> ProcessResult:
        return await self._runner.run(
            [self._xcrun, "simctl", "boot", udid], timeout_s=timeout_s
        )

    async def shutdown(self, udid: str, timeout_s: float = 30.0) -> ProcessResult:
        return await self._runner.run(
            [self._xcrun, "simctl", "shutdown", udid], timeout_s=timeout_s
        )

    async def install(
        self, udid: str, app_path: Path, timeout_s: float = 120.0
    ) -> ProcessResult:
        return await self._runner.run(
            [self._xcrun, "simctl", "install", udid, str(app_path)],
            timeout_s=timeout_s,
        )

    async def uninstall(
        self, udid: str, bundle_id: str, timeout_s: float = 30.0
    ) -> ProcessResult:
        return await self._runner.run(
            [self._xcrun, "simctl", "uninstall", udid, bundle_id], timeout_s=timeout_s
        )

    async def launch(
        self, udid: str, bundle_id: str, timeout_s: float = 30.0
    ) -> ProcessResult:
        return await self._runner.run(
            [self._xcrun, "simctl", "launch", udid, bundle_id], timeout_s=timeout_s
        )

    async def terminate(
        self, udid: str, bundle_id: str, timeout_s: float = 15.0
    ) -> ProcessResult:
        return await self._runner.run(
            [self._xcrun, "simctl", "terminate", udid, bundle_id], timeout_s=timeout_s
        )

    async def privacy_grant(
        self, udid: str, service: str, bundle_id: str, timeout_s: float = 15.0
    ) -> ProcessResult:
        """Grant a TCC permission. service ∈ {camera, microphone, location, photos, contacts, ...}."""
        return await self._runner.run(
            [self._xcrun, "simctl", "privacy", udid, "grant", service, bundle_id],
            timeout_s=timeout_s,
        )

    # ----- observation ---------------------------------------------------

    async def screenshot_to(
        self, udid: str, output_path: Path, timeout_s: float = 15.0
    ) -> ProcessResult:
        return await self._runner.run(
            [self._xcrun, "simctl", "io", udid, "screenshot", str(output_path)],
            timeout_s=timeout_s,
        )

    async def log_stream(self, udid: str):
        return await self._runner.stream(
            [self._xcrun, "simctl", "spawn", udid, "log", "stream"]
        )

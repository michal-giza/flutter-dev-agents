"""Thin async wrapper around the `adb` binary."""

from __future__ import annotations

import shutil
from pathlib import Path

from .process_runner import ProcessResult, ProcessRunner

_ADB_FALLBACKS = (
    "/opt/homebrew/bin/adb",
    "/usr/local/bin/adb",
    "/opt/homebrew/share/android-platform-tools/adb",
)


def _default_adb_path() -> str:
    found = shutil.which("adb")
    if found:
        return found
    for candidate in _ADB_FALLBACKS:
        if Path(candidate).exists():
            return candidate
    return "adb"


class AdbClient:
    def __init__(self, runner: ProcessRunner, adb_path: str | None = None) -> None:
        self._runner = runner
        self._adb = adb_path or _default_adb_path()

    async def devices_l(self, timeout_s: float = 10.0) -> ProcessResult:
        return await self._runner.run([self._adb, "devices", "-l"], timeout_s=timeout_s)

    async def shell(
        self, serial: str, *args: str, timeout_s: float = 30.0
    ) -> ProcessResult:
        argv = [self._adb, "-s", serial, "shell", *args]
        return await self._runner.run(argv, timeout_s=timeout_s)

    async def install(
        self, serial: str, apk_path: Path, replace: bool = True, timeout_s: float = 180.0
    ) -> ProcessResult:
        argv = [self._adb, "-s", serial, "install"]
        if replace:
            argv.append("-r")
        argv.append(str(apk_path))
        return await self._runner.run(argv, timeout_s=timeout_s)

    async def uninstall(
        self, serial: str, package_id: str, timeout_s: float = 30.0
    ) -> ProcessResult:
        return await self._runner.run(
            [self._adb, "-s", serial, "uninstall", package_id], timeout_s=timeout_s
        )

    async def get_prop(self, serial: str, prop: str) -> ProcessResult:
        return await self.shell(serial, "getprop", prop, timeout_s=5.0)

    async def pull(
        self, serial: str, remote: str, local: Path, timeout_s: float = 60.0
    ) -> ProcessResult:
        return await self._runner.run(
            [self._adb, "-s", serial, "pull", remote, str(local)], timeout_s=timeout_s
        )

    async def exec_out(
        self, serial: str, *args: str, timeout_s: float = 30.0
    ) -> ProcessResult:
        return await self._runner.run(
            [self._adb, "-s", serial, "exec-out", *args], timeout_s=timeout_s
        )

    async def screencap_to(
        self, serial: str, output_path: Path, timeout_s: float = 15.0
    ) -> ProcessResult:
        """Capture a PNG screenshot directly to `output_path` (binary-safe)."""
        return await self._runner.run_to_file(
            [self._adb, "-s", serial, "exec-out", "screencap", "-p"],
            output_path=output_path,
            timeout_s=timeout_s,
        )

    async def logcat_dump(
        self, serial: str, since_s: int, timeout_s: float = 15.0
    ) -> ProcessResult:
        return await self._runner.run(
            [
                self._adb,
                "-s",
                serial,
                "logcat",
                "-d",
                "-v",
                "threadtime",
                "-T",
                f"{since_s}",
            ],
            timeout_s=timeout_s,
        )

    async def logcat_stream(self, serial: str):
        return await self._runner.stream(
            [self._adb, "-s", serial, "logcat", "-v", "threadtime"]
        )

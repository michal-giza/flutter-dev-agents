"""Async wrapper around the Android `emulator` binary for AVD management."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from .process_runner import ProcessResult, ProcessRunner


def _default_emulator_path() -> str:
    found = shutil.which("emulator")
    if found:
        return found
    candidates = [
        os.environ.get("ANDROID_HOME"),
        os.environ.get("ANDROID_SDK_ROOT"),
        str(Path.home() / "Library/Android/sdk"),
        str(Path.home() / "Android/Sdk"),
    ]
    for sdk in (c for c in candidates if c):
        path = Path(sdk) / "emulator" / "emulator"
        if path.exists():
            return str(path)
    return "emulator"


class AndroidEmulatorCli:
    def __init__(self, runner: ProcessRunner, emulator_path: str | None = None) -> None:
        self._runner = runner
        self._bin = emulator_path or _default_emulator_path()

    @property
    def binary(self) -> str:
        return self._bin

    async def list_avds(self, timeout_s: float = 10.0) -> ProcessResult:
        return await self._runner.run([self._bin, "-list-avds"], timeout_s=timeout_s)

    async def start(
        self,
        avd_name: str,
        headless: bool = False,
        wipe_data: bool = False,
        no_snapshot: bool = True,
    ):
        argv = [self._bin, "-avd", avd_name]
        if headless:
            argv += ["-no-window"]
        if wipe_data:
            argv += ["-wipe-data"]
        if no_snapshot:
            argv += ["-no-snapshot-load"]
        return await self._runner.stream(argv)

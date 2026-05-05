"""Async wrapper around the `patrol` CLI (https://patrol.leancode.co)."""

from __future__ import annotations

import shutil
from pathlib import Path

from .process_runner import ProcessResult, ProcessRunner


_PATROL_FALLBACKS = (
    "/opt/homebrew/bin/patrol",
    "/usr/local/bin/patrol",
    str(Path.home() / ".pub-cache/bin/patrol"),
    str(Path.home() / "fvm/default/bin/cache/dart-sdk/bin/pub-global/bin/patrol"),
)


def _default_patrol_path() -> str:
    found = shutil.which("patrol")
    if found:
        return found
    for candidate in _PATROL_FALLBACKS:
        if Path(candidate).exists():
            return candidate
    return "patrol"


class PatrolCli:
    def __init__(self, runner: ProcessRunner, binary: str | None = None) -> None:
        self._runner = runner
        self._bin = binary or _default_patrol_path()

    @property
    def binary(self) -> str:
        return self._bin

    async def doctor(self, timeout_s: float = 30.0) -> ProcessResult:
        return await self._runner.run([self._bin, "doctor"], timeout_s=timeout_s)

    async def test(
        self,
        project_path: Path,
        target: Path | None = None,
        device_serial: str | None = None,
        flavor: str | None = None,
        build_mode: str = "debug",
        extra_flags: list[str] | None = None,
        timeout_s: float = 1800.0,
    ) -> ProcessResult:
        argv: list[str] = [self._bin, "test"]
        if target is not None:
            argv += ["--target", str(target)]
        if device_serial:
            argv += ["--device", device_serial]
        if flavor:
            argv += ["--flavor", flavor]
        if build_mode in ("release", "profile"):
            argv += [f"--{build_mode}"]
        if extra_flags:
            argv += list(extra_flags)
        return await self._runner.run(argv, cwd=project_path, timeout_s=timeout_s)

    async def develop(
        self,
        project_path: Path,
        target: Path,
        device_serial: str | None = None,
        timeout_s: float = 3600.0,
    ) -> ProcessResult:
        argv = [self._bin, "develop", "--target", str(target)]
        if device_serial:
            argv += ["--device", device_serial]
        return await self._runner.run(argv, cwd=project_path, timeout_s=timeout_s)

"""Async wrapper around the `flutter` CLI."""

from __future__ import annotations

import shutil
from pathlib import Path

from .process_runner import ProcessResult, ProcessRunner

_FLUTTER_FALLBACKS = (
    "/opt/homebrew/bin/flutter",
    "/usr/local/bin/flutter",
    str(Path.home() / "fvm/default/bin/flutter"),
    str(Path.home() / "flutter/bin/flutter"),
    str(Path.home() / "development/flutter/bin/flutter"),
)


def _default_flutter_path() -> str:
    found = shutil.which("flutter")
    if found:
        return found
    for candidate in _FLUTTER_FALLBACKS:
        if Path(candidate).exists():
            return candidate
    return "flutter"


class FlutterCli:
    def __init__(self, runner: ProcessRunner, flutter_path: str | None = None) -> None:
        self._runner = runner
        self._flutter = flutter_path or _default_flutter_path()

    async def build_apk(
        self,
        project_path: Path,
        mode: str = "debug",
        flavor: str | None = None,
        # Bumped 600 → 1500: first-run Gradle on a clean machine downloads
        # the Android Gradle Plugin, AAPT2, KGP, and the build cache — easily
        # 10+ minutes on a slow link. Subsequent builds complete in 30-90 s
        # so the bump only matters for cold starts. Reported in the field
        # May 2026.
        timeout_s: float = 1500.0,
    ) -> ProcessResult:
        argv = [self._flutter, "build", "apk", f"--{mode}"]
        if flavor:
            argv += ["--flavor", flavor]
        return await self._runner.run(argv, cwd=project_path, timeout_s=timeout_s)

    async def build_ipa(
        self,
        project_path: Path,
        mode: str = "debug",
        flavor: str | None = None,
        timeout_s: float = 1200.0,
    ) -> ProcessResult:
        argv = [self._flutter, "build", "ipa", f"--{mode}"]
        if flavor:
            argv += ["--flavor", flavor]
        return await self._runner.run(argv, cwd=project_path, timeout_s=timeout_s)

    async def test_unit(
        self, project_path: Path, timeout_s: float = 600.0
    ) -> ProcessResult:
        return await self._runner.run(
            [self._flutter, "test", "--reporter=json"],
            cwd=project_path,
            timeout_s=timeout_s,
        )

    async def test_integration(
        self,
        project_path: Path,
        device_serial: str,
        test_path: str = "integration_test/",
        timeout_s: float = 1800.0,
    ) -> ProcessResult:
        return await self._runner.run(
            [
                self._flutter,
                "test",
                test_path,
                "-d",
                device_serial,
                "--reporter=json",
            ],
            cwd=project_path,
            timeout_s=timeout_s,
        )

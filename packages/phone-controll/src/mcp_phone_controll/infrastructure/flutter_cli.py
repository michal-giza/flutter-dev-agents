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

    async def build_with_size_analysis(
        self,
        project_path: Path,
        platform: str = "apk",       # "apk" or "ios"
        mode: str = "release",       # size analysis only meaningful on release
        flavor: str | None = None,
        timeout_s: float = 1800.0,
    ) -> ProcessResult:
        """Build with --analyze-size — emits a per-package size report.

        Flutter writes the report to
        `build/<platform>/<mode>/<flavor>/<arch>-code-size-analysis_<timestamp>.json`
        AND prints a path-to-JSON line to stdout we can scrape. The
        report is a tree of (path, type, size, children) — used by
        the AnalyzeAppSize use case to surface "what's making your
        app big."

        Only meaningful in release mode. Debug builds skip tree
        shaking + obfuscation, so the numbers are misleading. The
        use case layer defaults mode="release" and warns on
        non-release values.
        """
        argv = [self._flutter, "build", platform, f"--{mode}", "--analyze-size"]
        if flavor:
            argv += ["--flavor", flavor]
        return await self._runner.run(argv, cwd=project_path, timeout_s=timeout_s)

    async def test_unit(
        self,
        project_path: Path,
        platform: str | None = None,
        timeout_s: float = 600.0,
    ) -> ProcessResult:
        # `platform` maps to `flutter test --platform <X>` (e.g. "chrome"
        # for Flutter web apps whose code imports dart:html, "vm" for the
        # default). None → omit the flag (Flutter's own default = VM).
        argv = [self._flutter, "test", "--reporter=json"]
        if platform:
            argv += ["--platform", platform]
        return await self._runner.run(argv, cwd=project_path, timeout_s=timeout_s)

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

    async def test_widget(
        self,
        project_path: Path,
        test_path: str | None = None,
        name_pattern: str | None = None,
        tags: str | None = None,
        plain_name: bool = False,
        coverage: bool = False,
        update_goldens: bool = False,
        platform: str | None = None,
        timeout_s: float = 600.0,
    ) -> ProcessResult:
        """`flutter test` with the targeting flags widget testing needs.

        Use cases this covers that the existing `test_unit()` doesn't:

        - `test_path` — point at one file (`test/widgets/foo_test.dart`)
          or a subdirectory (`test/features/auth/`). Lets agents
          re-run only the widget tests they just touched, not the
          whole suite.
        - `name_pattern` — `--name` regex over the testWidgets()
          description string. Combined with `plain_name=True`, this
          becomes `--plain-name` (literal substring, not regex).
        - `tags` — `--tags` filter for tests grouped with
          `tags: ['golden']` or similar conventions. Useful when
          a portfolio of apps tags golden-image tests separately
          so they're easy to opt in/out.
        - `coverage` — adds `--coverage` so the lcov.info file is
          generated; the use case layer then parses it.
        - `update_goldens` — adds `--update-goldens` so golden
          mismatches REGENERATE the saved images instead of
          failing. Use deliberately — running this against a
          regressed UI silently wipes the regression detection.
        - `platform` — maps to `--platform` (e.g. "chrome"). Flutter
          web apps whose widgets pull in `dart:html` won't compile on
          the default VM platform; "chrome" runs them in a headless
          browser. None omits the flag (VM default).

        All flags compose. `--reporter=json` stays on so the
        existing parser still works.
        """
        argv = [self._flutter, "test", "--reporter=json"]
        if platform:
            argv += ["--platform", platform]
        if coverage:
            argv.append("--coverage")
        if update_goldens:
            argv.append("--update-goldens")
        if name_pattern:
            argv.append("--plain-name" if plain_name else "--name")
            argv.append(name_pattern)
        if tags:
            argv += ["--tags", tags]
        if test_path:
            argv.append(test_path)
        return await self._runner.run(argv, cwd=project_path, timeout_s=timeout_s)

"""Async wrapper around the `patrol` CLI (https://patrol.leancode.co)."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .process_runner import ProcessResult, ProcessRunner

# `patrol --version` prints an update banner BEFORE the real line, e.g.
#     Update available! 3.11.0 → 4.5.1
#     patrol_cli v3.11.0
# so a naive "first version-looking token" parse reads the LATEST version
# instead of the installed one. Anchor on the package name.
_VERSION_RE = re.compile(r"patrol_cli\s+v(\d+)\.(\d+)\.(\d+)")

# Flutter web integration testing landed in patrol_cli 4.0.0 (with patrol
# 4.0.0, released together 2025-12-08) and is driven by Playwright.
MIN_WEB_CLI_VERSION = (4, 0, 0)

# The `-d` value Patrol documents for web. Chromium only — the docs list
# no Firefox/WebKit target and there is no documented flag to pick one.
WEB_DEVICE = "chrome"

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


_UNSET = object()


class PatrolCli:
    def __init__(self, runner: ProcessRunner, binary: str | None = None) -> None:
        self._runner = runner
        self._bin = binary or _default_patrol_path()
        self._version_cache: tuple[int, int, int] | None | object = _UNSET

    @property
    def binary(self) -> str:
        return self._bin

    async def doctor(self, timeout_s: float = 30.0) -> ProcessResult:
        return await self._runner.run([self._bin, "doctor"], timeout_s=timeout_s)

    async def version(self, timeout_s: float = 20.0) -> tuple[int, int, int] | None:
        """Installed patrol_cli version, or None if unparsable.

        Cached per instance — the subprocess costs ~1s and the binary
        doesn't change mid-session.
        """
        if self._version_cache is not _UNSET:
            return self._version_cache
        parsed: tuple[int, int, int] | None = None
        try:
            result = await self._runner.run(
                [self._bin, "--version"], timeout_s=timeout_s
            )
            match = _VERSION_RE.search(f"{result.stdout or ''}\n{result.stderr or ''}")
            if match:
                parsed = (
                    int(match.group(1)), int(match.group(2)), int(match.group(3))
                )
        except Exception:
            parsed = None
        self._version_cache = parsed
        return parsed

    async def test(
        self,
        project_path: Path,
        target: Path | None = None,
        device_serial: str | None = None,
        flavor: str | None = None,
        build_mode: str = "debug",
        extra_flags: list[str] | None = None,
        timeout_s: float = 1800.0,
        web: bool = False,
        web_headless: bool = True,
        web_port: int | None = None,
        # Machine-readable web results (Playwright JSON report).
        web_results_dir: Path | None = None,
        web_retries: int | None = None,
        web_global_timeout_ms: int | None = None,
        web_browser_args: list[str] | None = None,
        web_video: str | None = None,
        # Patrol 4 native-only hermeticity knobs.
        clear_permissions: bool = False,
        full_isolation: bool = False,
        # Shared filtering / config.
        tags: str | None = None,
        exclude_tags: str | None = None,
        dart_defines: list[str] | None = None,
        dart_define_from_file: Path | None = None,
    ) -> ProcessResult:
        """Run `patrol test`.

        `web=True` targets Flutter web (Patrol >= 4.0.0, Playwright-driven,
        Chromium only). The web path deliberately differs:
          - `--device chrome` (the only documented web target);
          - `--flavor` is SUPPRESSED — patrol_cli rejects it for web;
          - build mode is forced to debug (release/profile on the web path
            are unverified upstream, so we don't emit them);
          - `--web-headless` takes a literal `true`/`false`, not a bare flag,
            and we default to headless because MCP runs are unattended.
        We intentionally do NOT emit `--web-reporter` yet: its accepted
        encoding (a JSON array) through subprocess argv is unverified.
        """
        argv: list[str] = [self._bin, "test"]
        if target is not None:
            argv += ["--target", str(target)]
        if web:
            argv += ["--device", WEB_DEVICE]
            argv += ["--web-headless", "true" if web_headless else "false"]
            if web_port is not None:
                argv += ["--web-port", str(web_port)]
            # Machine-readable results. `--web-reporter` takes a JSON ARRAY
            # STRING (verified in patrol_cli 4.5.1 --help:
            #   --web-reporter=<'["html", "json", "list"]'>), so we json.dumps
            # it rather than passing a bare word.
            if web_results_dir is not None:
                argv += ["--web-reporter", json.dumps(["json"])]
                argv += ["--web-results-dir", str(web_results_dir)]
            if web_retries is not None:
                argv += ["--web-retries", str(web_retries)]
            if web_global_timeout_ms is not None:
                argv += ["--web-global-timeout", str(web_global_timeout_ms)]
            if web_browser_args:
                argv += ["--web-browser-args", json.dumps(list(web_browser_args))]
            if web_video:
                argv += ["--web-video", web_video]
        else:
            if device_serial:
                argv += ["--device", device_serial]
            if flavor:
                argv += ["--flavor", flavor]
            if build_mode in ("release", "profile"):
                argv += [f"--{build_mode}"]
            # Patrol 4 hermeticity knobs — they only exist on the native path.
            if clear_permissions:
                argv += ["--clear-permissions"]
            if full_isolation:
                argv += ["--full-isolation"]
        # Shared across platforms.
        if tags:
            argv += ["--tags", tags]
        if exclude_tags:
            argv += ["--exclude-tags", exclude_tags]
        for define in dart_defines or []:
            argv += ["--dart-define", define]
        if dart_define_from_file is not None:
            argv += ["--dart-define-from-file", str(dart_define_from_file)]
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

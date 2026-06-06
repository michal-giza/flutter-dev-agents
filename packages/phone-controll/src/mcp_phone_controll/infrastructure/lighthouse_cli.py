"""Thin wrapper over the Lighthouse CLI (Google's web-quality auditor).

We *run* Lighthouse headless and write its JSON report; the parsing /
grading half lives in the `ingest_lighthouse_report` use case (which
`run_lighthouse` then delegates to). Same orchestrate-the-toolchain
posture as `FlutterCli` / `PatrolCli` — we shell out to an external CLI
the user already has, we don't reimplement it.

Lighthouse is an npm tool. We resolve it as (in order):
  1. `lighthouse` on PATH
  2. `npx --yes lighthouse` (lets it run without a global install)

Both need a Chrome/Chromium that Lighthouse can drive headless.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .process_runner import ProcessResult, ProcessRunner


class LighthouseCli:
    def __init__(self, runner: ProcessRunner) -> None:
        self._runner = runner

    def resolve_argv_prefix(self) -> list[str] | None:
        """How to invoke Lighthouse, or None if it can't be found.
        `npx` is the fallback so users without a global install still work."""
        if shutil.which("lighthouse"):
            return ["lighthouse"]
        if shutil.which("npx"):
            return ["npx", "--yes", "lighthouse"]
        return None

    async def run(
        self,
        url: str,
        output_path: Path,
        categories: tuple[str, ...] | None = None,
        preset: str | None = None,
        chrome_flags: str = "--headless=new --no-sandbox",
        extra_args: tuple[str, ...] = (),
        timeout_s: float = 180.0,
    ) -> ProcessResult | None:
        """Run `lighthouse <url> --output=json --output-path=<file>`.

        Returns None if the Lighthouse CLI can't be resolved at all (so
        the use case can emit a clean install hint). Otherwise returns the
        ProcessResult (which may still be a non-zero exit — the use case
        decides)."""
        prefix = self.resolve_argv_prefix()
        if prefix is None:
            return None

        argv = [
            *prefix,
            url,
            "--output=json",
            f"--output-path={output_path}",
            "--quiet",
            f"--chrome-flags={chrome_flags}",
        ]
        if categories:
            argv.append("--only-categories=" + ",".join(categories))
        if preset:
            argv.append(f"--preset={preset}")
        argv.extend(extra_args)

        return await self._runner.run(argv, timeout_s=timeout_s)

"""Run Lighthouse against a URL, then parse the report (web vitals).

This is the *runner* half the field report asked for: `ingest_lighthouse_report`
parses a Lighthouse JSON file, but until now you had to run `lighthouse`
yourself. `run_lighthouse` shells out to the Lighthouse CLI (headless
Chrome), writes the JSON, and delegates to `IngestLighthouseReport` for
the scores / Core Web Vitals / grade — so one call gives you hard web
metrics against a running build (e.g. `http://localhost:8080`).

Composition, not reinvention:
  • We run the official Lighthouse CLI (like we run flutter / adb / patrol);
    we do NOT reimplement an auditor.
  • Parsing + CanvasKit-aware grading is 100% reused from
    `ingest_lighthouse_report` (same result shape).
  • For interactive browser driving (click/scroll/login before measuring),
    compose with the official Chrome MCP — we don't ship a browser driver.

The saved report path is returned so you can re-ingest or diff later.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..failures import LighthouseFailure
from ..result import Err, Result, err, ok
from .base import BaseUseCase
from .ingest_lighthouse_report import (
    IngestLighthouseReport,
    IngestLighthouseReportParams,
    IngestLighthouseReportResult,
)


@dataclass(frozen=True, slots=True)
class RunLighthouseParams:
    url: str
    # Where to save the JSON report. None → a temp file (returned in the
    # result so you can re-ingest / diff later).
    output_path: Path | None = None
    # Restrict to specific Lighthouse categories, e.g.
    # ("performance", "accessibility"). None → all.
    categories: tuple[str, ...] | None = None
    # Lighthouse preset: "desktop" or "mobile" (Lighthouse's default is
    # mobile/throttled). For a desktop Flutter web build use "desktop".
    preset: str | None = None
    # CanvasKit-aware perf threshold passed straight to the ingest grader
    # (a perf score of 70 is healthy for CanvasKit).
    perf_good_threshold: float = 70.0
    chrome_flags: str = "--headless=new --no-sandbox"
    timeout_s: float = 180.0


@dataclass(frozen=True, slots=True)
class RunLighthouseResult:
    url: str
    report_path: str                        # saved JSON — re-ingestable
    grade: str                              # convenience mirror of report.grade
    report: IngestLighthouseReportResult    # full parsed result (reused shape)


class RunLighthouse(BaseUseCase[RunLighthouseParams, RunLighthouseResult]):
    """Run the Lighthouse CLI headless, then parse the report.

    Needs the `lighthouse` CLI (or `npx`) + a Chrome/Chromium on the host.
    Surfaces a clean install hint when it's missing — same posture as
    check_environment for adb/flutter.
    """

    def __init__(self, lighthouse_cli, ingest: IngestLighthouseReport) -> None:
        self._cli = lighthouse_cli
        self._ingest = ingest

    async def execute(self, params: RunLighthouseParams) -> Result[RunLighthouseResult]:
        if not params.url or not params.url.strip():
            return err(LighthouseFailure(
                message="url is required (e.g. http://localhost:8080)",
                next_action="fix_arguments",
            ))

        out_path = (
            params.output_path.expanduser()
            if params.output_path is not None
            else Path(tempfile.gettempdir()) / "phone_controll_lighthouse.json"
        )

        proc = await self._cli.run(
            url=params.url,
            output_path=out_path,
            categories=params.categories,
            preset=params.preset,
            chrome_flags=params.chrome_flags,
            timeout_s=params.timeout_s,
        )

        if proc is None:
            return err(LighthouseFailure(
                message=(
                    "Lighthouse CLI not found. Install it with "
                    "`npm install -g lighthouse` (needs Node + Chrome), or "
                    "ensure `npx` is on PATH."
                ),
                next_action="install_lighthouse",
            ))

        # Lighthouse can exit non-zero yet still write a usable report
        # (warnings), so check the file first; only treat a missing file
        # as a hard failure.
        if not out_path.is_file():
            return err(LighthouseFailure(
                message=(
                    f"Lighthouse produced no report at {out_path} "
                    f"(exit {proc.returncode})."
                ),
                details={
                    "url": params.url,
                    "returncode": proc.returncode,
                    "stderr_tail": (proc.stderr or "")[-2000:],
                },
                next_action="check_environment",
            ))

        ingested = await self._ingest.execute(IngestLighthouseReportParams(
            report_path=out_path,
            perf_good_threshold=params.perf_good_threshold,
        ))
        if isinstance(ingested, Err):
            return ingested

        report = ingested.value
        return ok(RunLighthouseResult(
            url=params.url,
            report_path=str(out_path),
            grade=report.grade,
            report=report,
        ))

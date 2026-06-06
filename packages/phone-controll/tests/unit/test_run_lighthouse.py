"""run_lighthouse — the Lighthouse *runner* (v0.6.0).

Field report asked for it: `ingest_lighthouse_report` parses a JSON
report, but the MCP couldn't RUN Lighthouse. `run_lighthouse` shells out
to the Lighthouse CLI (headless Chrome), writes the JSON, and reuses the
existing ingest parsing/grading in one call.

Hermetic: a fake LighthouseCli writes a scripted report (or doesn't);
the real IngestLighthouseReport does the parsing. No real lighthouse /
Chrome needed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_phone_controll.domain.failures import LighthouseFailure
from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.ingest_lighthouse_report import (
    IngestLighthouseReport,
)
from mcp_phone_controll.domain.usecases.run_lighthouse import (
    RunLighthouse,
    RunLighthouseParams,
)
from mcp_phone_controll.infrastructure.lighthouse_cli import LighthouseCli
from mcp_phone_controll.infrastructure.process_runner import ProcessResult

_MINIMAL_REPORT = {
    "finalUrl": "http://localhost:8080/",
    "categories": {
        "performance": {"score": 0.72},
        "accessibility": {"score": 0.95},
        "seo": {"score": 0.9},
    },
    "audits": {
        "largest-contentful-paint": {
            "numericValue": 2300, "score": 0.9, "displayValue": "2.3 s",
        },
        "cumulative-layout-shift": {
            "numericValue": 0.05, "score": 1.0, "displayValue": "0.05",
        },
        "total-blocking-time": {
            "numericValue": 150, "score": 0.95, "displayValue": "150 ms",
        },
    },
}


class _FakeLighthouseCli:
    """Scriptable stand-in. `prefix=None` simulates 'lighthouse not found';
    `write_report` controls whether a JSON file is produced."""

    def __init__(self, *, prefix=("lighthouse",), write_report=True, returncode=0):
        self._prefix = list(prefix) if prefix is not None else None
        self._write = write_report
        self._rc = returncode
        self.calls: list[dict] = []

    def resolve_argv_prefix(self):
        return self._prefix

    async def run(self, *, url, output_path, **kwargs):
        self.calls.append({"url": url, "output_path": output_path, **kwargs})
        if self._prefix is None:
            return None
        if self._write:
            Path(output_path).write_text(json.dumps(_MINIMAL_REPORT), encoding="utf-8")
        return ProcessResult(returncode=self._rc, stdout="", stderr="lh log")


def _uc(cli):
    return RunLighthouse(cli, IngestLighthouseReport())


# ---- happy path ---------------------------------------------------------


@pytest.mark.asyncio
async def test_runs_and_parses(tmp_path: Path):
    out = tmp_path / "lh.json"
    cli = _FakeLighthouseCli()
    res = await _uc(cli)(RunLighthouseParams(url="http://localhost:8080", output_path=out))

    assert isinstance(res, Ok)
    assert res.value.url == "http://localhost:8080"
    assert res.value.report_path == str(out)
    # Reused ingest grading: perf 72 + good CWV → "good" (CanvasKit-aware).
    assert res.value.grade == "good"
    assert res.value.report.lcp_s == 2.3
    # The CLI got the url + output path.
    assert cli.calls[0]["url"] == "http://localhost:8080"


@pytest.mark.asyncio
async def test_passes_through_options(tmp_path: Path):
    out = tmp_path / "lh.json"
    cli = _FakeLighthouseCli()
    await _uc(cli)(RunLighthouseParams(
        url="http://localhost:8080",
        output_path=out,
        categories=("performance", "accessibility"),
        preset="desktop",
        perf_good_threshold=90.0,
    ))
    call = cli.calls[0]
    assert call["categories"] == ("performance", "accessibility")
    assert call["preset"] == "desktop"


# ---- failure modes ------------------------------------------------------


@pytest.mark.asyncio
async def test_cli_not_found(tmp_path: Path):
    cli = _FakeLighthouseCli(prefix=None)
    res = await _uc(cli)(RunLighthouseParams(url="http://x", output_path=tmp_path / "x.json"))
    assert isinstance(res, Err)
    assert isinstance(res.failure, LighthouseFailure)
    assert res.failure.next_action == "install_lighthouse"


@pytest.mark.asyncio
async def test_no_report_produced(tmp_path: Path):
    cli = _FakeLighthouseCli(write_report=False, returncode=1)
    res = await _uc(cli)(RunLighthouseParams(url="http://x", output_path=tmp_path / "missing.json"))
    assert isinstance(res, Err)
    assert isinstance(res.failure, LighthouseFailure)
    assert res.failure.next_action == "check_environment"
    assert "stderr_tail" in res.failure.details


@pytest.mark.asyncio
async def test_empty_url_rejected(tmp_path: Path):
    cli = _FakeLighthouseCli()
    res = await _uc(cli)(RunLighthouseParams(url="   ", output_path=tmp_path / "x.json"))
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


# ---- LighthouseCli argv + resolution ------------------------------------


class _RecordingRunner:
    def __init__(self):
        self.argv = None

    async def run(self, argv, cwd=None, timeout_s=None, env=None):
        self.argv = list(argv)
        return ProcessResult(returncode=0, stdout="", stderr="")


@pytest.mark.asyncio
async def test_cli_builds_argv(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "mcp_phone_controll.infrastructure.lighthouse_cli.shutil.which",
        lambda name: "/usr/bin/lighthouse" if name == "lighthouse" else None,
    )
    runner = _RecordingRunner()
    cli = LighthouseCli(runner)
    out = tmp_path / "r.json"
    await cli.run(
        url="http://localhost:8080", output_path=out,
        categories=("performance",), preset="desktop",
    )
    assert runner.argv[0] == "lighthouse"
    assert "http://localhost:8080" in runner.argv
    assert "--output=json" in runner.argv
    assert f"--output-path={out}" in runner.argv
    assert "--only-categories=performance" in runner.argv
    assert "--preset=desktop" in runner.argv


def test_cli_resolves_npx_fallback(monkeypatch):
    monkeypatch.setattr(
        "mcp_phone_controll.infrastructure.lighthouse_cli.shutil.which",
        lambda name: "/usr/bin/npx" if name == "npx" else None,
    )
    cli = LighthouseCli(_RecordingRunner())
    assert cli.resolve_argv_prefix() == ["npx", "--yes", "lighthouse"]


def test_cli_resolves_none_when_absent(monkeypatch):
    monkeypatch.setattr(
        "mcp_phone_controll.infrastructure.lighthouse_cli.shutil.which",
        lambda name: None,
    )
    cli = LighthouseCli(_RecordingRunner())
    assert cli.resolve_argv_prefix() is None

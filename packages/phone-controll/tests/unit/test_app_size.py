"""Tests for the v0.3.0 app-size analyzer.

Hermetic — fakes the FlutterCli so no real `flutter build` is needed
(that takes 10+ minutes on a cold cache). Tests cover:

- Happy path: build succeeds, JSON parses, top-N packages + assets
  surface, advice line forms correctly.
- JSON-path extraction regex handles both wording variants Flutter
  has shipped across versions.
- Delta vs baseline: a previous run JSON is compared and the
  growers + shrinkers surface.
- Failure modes: build fails → typed error; output present but no
  JSON path mentioned → fix-arguments envelope; unsupported
  platform string rejected upfront.
- _fmt_bytes formatter for the three magnitude bands (B / KB / MB).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.app_size import (
    AnalyzeAppSize,
    AnalyzeAppSizeParams,
    _extract_json_path_from_output,
    _fmt_bytes,
)
from mcp_phone_controll.infrastructure.process_runner import ProcessResult

# ---- fixtures ----------------------------------------------------------


class _FakeFlutterCli:
    """Stub FlutterCli — records the call args, returns scripted output."""

    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.calls: list[dict] = []

    async def build_with_size_analysis(self, **kwargs):
        self.calls.append(kwargs)
        return ProcessResult(
            stdout=self.stdout,
            stderr=self.stderr,
            returncode=self.returncode,
        )


def _make_size_report() -> dict:
    """Realistic shape of `flutter build --analyze-size` output."""
    return {
        "compressed_size_bytes": 4_200_000,
        "uncompressed_size_bytes": 10_500_000,
        "root": [
            # Code packages
            {
                "name": "package:flutter/material.dart",
                "type": "package",
                "size": 1_200_000,
            },
            {
                "name": "package:flutter/widgets.dart",
                "type": "package",
                "size": 800_000,
            },
            {
                "name": "package:flutter_bloc/src/bloc.dart",
                "type": "package",
                "size": 300_000,
            },
            {
                "name": "package:flutter_bloc/src/cubit.dart",
                "type": "package",
                "size": 200_000,
            },
            # Assets
            {"name": "assets/images/onboarding.mp4", "size": 8_000_000},
            {"name": "assets/images/hero.png", "size": 500_000},
            {"name": "assets/fonts/Inter-Regular.ttf", "size": 150_000},
            # Misc (filtered out — neither package nor asset)
            {"name": "isolate_snapshot_data", "size": 50_000},
        ],
    }


# ---- _extract_json_path_from_output regex ------------------------------


def test_extract_json_path_handles_flutter_wording_variant_1():
    stdout = """
Running Gradle task 'assembleRelease'…
✓ Built build/app/outputs/flutter-apk/app-release.apk (4.2MB).
A size analysis file has been written to: /tmp/flutter_size_2026_05_20_abc/apk-code-size-analysis_01.json
"""
    p = _extract_json_path_from_output(stdout)
    assert p is not None
    assert p.name == "apk-code-size-analysis_01.json"


def test_extract_json_path_handles_flutter_wording_variant_2():
    """Older Flutter shipped 'Size analysis written to <path>'."""
    stdout = "Size analysis written to /tmp/foo/code-size-analysis_07.json\n"
    p = _extract_json_path_from_output(stdout)
    assert p is not None
    assert p.name == "code-size-analysis_07.json"


def test_extract_json_path_returns_none_when_absent():
    assert _extract_json_path_from_output("just normal build output\n") is None


# ---- _fmt_bytes --------------------------------------------------------


def test_fmt_bytes_renders_three_magnitude_bands():
    assert _fmt_bytes(500) == "500 B"
    assert _fmt_bytes(1500) == "1.5 KB"
    assert _fmt_bytes(2_500_000) == "2.4 MB"


# ---- AnalyzeAppSize happy path -----------------------------------------


@pytest.mark.asyncio
async def test_analyze_app_size_happy(tmp_path: Path):
    # Write the size report to disk; Flutter would have done this.
    json_path = tmp_path / "apk-code-size-analysis_01.json"
    json_path.write_text(json.dumps(_make_size_report()))
    stdout = (
        f"Built build/app/outputs/flutter-apk/app-release.apk.\n"
        f"A size analysis file has been written to: {json_path}\n"
    )
    cli = _FakeFlutterCli(stdout=stdout)

    res = await AnalyzeAppSize(cli)(
        AnalyzeAppSizeParams(project_path=tmp_path, platform="apk")
    )
    assert isinstance(res, Ok)
    v = res.value
    assert v.platform == "apk"
    assert v.total_compressed_bytes == 4_200_000
    # Largest package: flutter/material + flutter/widgets roll up to
    # "package:flutter" → 2_000_000. flutter_bloc rolls to 500_000.
    assert v.top_packages[0].name == "package:flutter"
    assert v.top_packages[0].bytes == 2_000_000
    # Largest asset: the 8MB onboarding video
    assert v.top_assets[0].path == "assets/images/onboarding.mp4"
    assert v.top_assets[0].bytes == 8_000_000
    # Advice mentions the largest package + asset
    assert "package:flutter" in v.advice
    assert "onboarding" in v.advice


@pytest.mark.asyncio
async def test_analyze_app_size_warns_on_non_release_mode(tmp_path: Path):
    """Non-release builds skip tree shaking; the advice line must
    flag that so the agent doesn't quote misleading numbers."""
    json_path = tmp_path / "apk-code-size-analysis_01.json"
    json_path.write_text(json.dumps(_make_size_report()))
    cli = _FakeFlutterCli(
        stdout=f"A size analysis file has been written to: {json_path}\n"
    )

    res = await AnalyzeAppSize(cli)(
        AnalyzeAppSizeParams(project_path=tmp_path, mode="debug")
    )
    assert isinstance(res, Ok)
    assert "tree shaking" in res.value.advice.lower() or "misleading" in res.value.advice.lower()


# ---- delta vs baseline -------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_app_size_delta_surfaces_growers(tmp_path: Path):
    """Baseline has flutter_bloc at 200KB; current has it at 500KB.
    The delta report should flag a +300KB growth for the rolled-up
    package."""
    # Current run
    cur_json = tmp_path / "current.json"
    cur_json.write_text(json.dumps(_make_size_report()))

    # Baseline — flutter_bloc was smaller, and onboarding video didn't exist yet
    baseline = _make_size_report()
    # Remove the bloc entries from baseline
    baseline["root"] = [r for r in baseline["root"] if "flutter_bloc" not in r.get("name", "")]
    # Add smaller bloc
    baseline["root"].append({
        "name": "package:flutter_bloc/src/bloc.dart",
        "type": "package",
        "size": 200_000,  # was 500K rolled up; now 200K
    })
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline))

    cli = _FakeFlutterCli(
        stdout=f"A size analysis file has been written to: {cur_json}\n"
    )

    res = await AnalyzeAppSize(cli)(
        AnalyzeAppSizeParams(
            project_path=tmp_path,
            baseline_json_path=baseline_path,
        )
    )
    assert isinstance(res, Ok)
    deltas = res.value.deltas_vs_baseline
    bloc_delta = next((d for d in deltas if d.name == "package:flutter_bloc"), None)
    assert bloc_delta is not None
    assert bloc_delta.delta_bytes == 300_000


# ---- error paths -------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_app_size_unsupported_platform(tmp_path: Path):
    """'web' isn't supported — fail fast with a typed error."""
    res = await AnalyzeAppSize(_FakeFlutterCli())(
        AnalyzeAppSizeParams(project_path=tmp_path, platform="web")
    )
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_analyze_app_size_build_failure_surfaces_typed_error(tmp_path: Path):
    """flutter build returns non-zero → FlutterCliFailure with logs."""
    cli = _FakeFlutterCli(returncode=1, stderr="error: kotlin compile failed")
    res = await AnalyzeAppSize(cli)(AnalyzeAppSizeParams(project_path=tmp_path))
    assert isinstance(res, Err)
    assert res.failure.next_action == "check_build_log"
    assert "kotlin" in str(res.failure.details).lower()


@pytest.mark.asyncio
async def test_analyze_app_size_no_json_path_in_output(tmp_path: Path):
    """Build succeeded but didn't mention the analysis JSON path —
    surface a structured error so the agent knows to check
    flutter version."""
    cli = _FakeFlutterCli(stdout="Built app-release.apk\n", returncode=0)
    res = await AnalyzeAppSize(cli)(AnalyzeAppSizeParams(project_path=tmp_path))
    assert isinstance(res, Err)
    assert res.failure.next_action == "check_flutter_version"

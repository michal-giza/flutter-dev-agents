"""Opt-in integration tests — run only when MCP_REAL=1.

These exercise real CLI tools (flutter, dart, adb) against the
`tests/fixtures/sample_flutter_app/` fixture project. They are slow,
require a Flutter SDK, and cannot run in standard CI. Skip by default.

Run them with:

    MCP_REAL=1 pytest tests/integration_real

Add `MCP_REAL_DEVICE=1` to also exercise the device-attached paths
(install_app, take_screenshot, etc.). That requires a connected Android
device or running emulator.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def _opt_in_guard() -> None:
    if os.environ.get("MCP_REAL") != "1":
        pytest.skip(
            "integration_real tests skipped; set MCP_REAL=1 to enable",
            allow_module_level=True,
        )


@pytest.fixture(scope="session")
def sample_flutter_app() -> Path:
    here = Path(__file__).resolve().parent.parent
    fixture = here / "fixtures" / "sample_flutter_app"
    if not (fixture / "pubspec.yaml").exists():
        pytest.skip(f"fixture missing: {fixture}")
    return fixture


@pytest.fixture(scope="session")
def flutter_cli() -> str:
    path = shutil.which("flutter")
    if not path:
        pytest.skip("flutter SDK not on PATH")
    return path


@pytest.fixture(scope="session")
def adb_cli() -> str:
    path = shutil.which("adb") or "/opt/homebrew/bin/adb"
    if not Path(path).exists():
        pytest.skip("adb not on PATH and not at /opt/homebrew/bin/adb")
    return path


@pytest.fixture(scope="session")
def real_device_required() -> str:
    """Skip unless a real Android device or emulator is attached AND
    `MCP_REAL_DEVICE=1` is set. Returns the device serial."""
    import subprocess

    if os.environ.get("MCP_REAL_DEVICE") != "1":
        pytest.skip(
            "device-attached tests skipped; set MCP_REAL_DEVICE=1 + "
            "have an Android device or emulator booted",
            allow_module_level=False,
        )
    out = subprocess.run(
        ["adb", "devices"], capture_output=True, text=True, timeout=10
    )
    lines = [
        line.strip() for line in out.stdout.splitlines()
        if line.strip() and "\tdevice" in line and not line.startswith("List")
    ]
    if not lines:
        pytest.skip("MCP_REAL_DEVICE=1 set but no devices visible to adb")
    return lines[0].split("\t")[0]

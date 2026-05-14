"""Regression test for the Android screenshot binary-corruption bug.

Earlier impl decoded screencap stdout as utf-8 then re-encoded as latin-1, both
with errors='replace'. PNG bytes are 8-bit binary and full of non-ASCII; the
roundtrip silently corrupted the file. This test runs through a fake runner
that streams real PNG bytes, then asserts the file is byte-identical to the
source — catches any future regression that reintroduces a string roundtrip.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.data.repositories.adb_observation_repository import (
    AdbObservationRepository,
)
from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.infrastructure.adb_client import AdbClient
from mcp_phone_controll.infrastructure.process_runner import ProcessResult

# Minimal real PNG: 8-byte signature + IHDR + IDAT + IEND. 1x1 transparent.
_REAL_PNG = bytes.fromhex(
    "89504e470d0a1a0a"                          # signature
    "0000000d49484452000000010000000108060000001f15c489"  # IHDR
    "0000000d49444154789c6300010000000500010d0a2db40000000049454e44ae426082"
)


class _BinaryStreamingRunner:
    """ProcessRunner double that writes a known PNG byte-for-byte to output_path."""

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.calls: list[list[str]] = []

    async def run(self, argv, cwd=None, timeout_s=None, env=None):
        self.calls.append(list(argv))
        return ProcessResult(returncode=0, stdout="", stderr="")

    async def run_to_file(self, argv, output_path, cwd=None, timeout_s=None, env=None):
        self.calls.append(list(argv))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(self.payload)
        return ProcessResult(returncode=0, stdout="", stderr="")

    async def stream(self, argv, cwd=None, env=None):
        raise NotImplementedError


@pytest.mark.asyncio
async def test_screenshot_writes_binary_unmodified(tmp_path: Path):
    runner = _BinaryStreamingRunner(_REAL_PNG)
    adb = AdbClient(runner, adb_path="adb")
    repo = AdbObservationRepository(adb)

    out = tmp_path / "shot.png"
    res = await repo.screenshot("EMU01", out)

    assert isinstance(res, Ok), res
    assert out.exists()
    assert out.read_bytes() == _REAL_PNG, "PNG must be byte-identical to the source"


@pytest.mark.asyncio
async def test_screenshot_rejects_non_png_output(tmp_path: Path):
    """If screencap returns garbage, surface a clean error instead of letting agents
    try to read a corrupt file."""
    runner = _BinaryStreamingRunner(b"NOTAPNG_PAYLOAD")
    repo = AdbObservationRepository(AdbClient(runner, adb_path="adb"))

    res = await repo.screenshot("EMU01", tmp_path / "broken.png")
    assert isinstance(res, Err)
    assert "not a valid PNG" in res.failure.message


@pytest.mark.asyncio
async def test_screenshot_rejects_empty_output(tmp_path: Path):
    runner = _BinaryStreamingRunner(b"")
    repo = AdbObservationRepository(AdbClient(runner, adb_path="adb"))

    res = await repo.screenshot("EMU01", tmp_path / "empty.png")
    assert isinstance(res, Err)
    assert "no output" in res.failure.message


@pytest.mark.asyncio
async def test_screenshot_uses_exec_out_screencap_p(tmp_path: Path):
    runner = _BinaryStreamingRunner(_REAL_PNG)
    repo = AdbObservationRepository(AdbClient(runner, adb_path="adb"))

    await repo.screenshot("EMU01", tmp_path / "ok.png")
    assert runner.calls == [["adb", "-s", "EMU01", "exec-out", "screencap", "-p"]]

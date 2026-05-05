"""ObservationRepository implementation backed by adb."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from ...domain.entities import LogEntry, LogLevel
from ...domain.failures import AdbFailure, TimeoutFailure
from ...domain.repositories import ObservationRepository
from ...domain.result import Result, err, ok
from ...infrastructure.adb_client import AdbClient
from ..parsers.adb_devices_parser import parse_logcat_threadtime


_LEVEL_ORDER = {
    LogLevel.VERBOSE: 0,
    LogLevel.DEBUG: 1,
    LogLevel.INFO: 2,
    LogLevel.WARN: 3,
    LogLevel.ERROR: 4,
    LogLevel.FATAL: 5,
}


class AdbObservationRepository(ObservationRepository):
    def __init__(self, adb: AdbClient) -> None:
        self._adb = adb
        self._recordings: dict[str, tuple[asyncio.subprocess.Process, str, Path]] = {}

    async def screenshot(self, serial: str, output_path: Path) -> Result[Path]:
        # Write binary PNG straight to disk — never decode bytes through string.
        result = await self._adb.screencap_to(serial, output_path, timeout_s=15.0)
        if not result.ok:
            return err(
                AdbFailure(
                    message="screencap failed",
                    details={"stderr": result.stderr, "returncode": result.returncode},
                )
            )
        if not output_path.exists() or output_path.stat().st_size == 0:
            return err(
                AdbFailure(
                    message="screencap produced no output",
                    details={"path": str(output_path), "stderr": result.stderr},
                )
            )
        # Sanity-check the PNG signature so a partial write surfaces as a clean error
        # instead of a silently corrupt file Claude can't read.
        with output_path.open("rb") as fh:
            header = fh.read(8)
        if header[:8] != b"\x89PNG\r\n\x1a\n":
            return err(
                AdbFailure(
                    message="screencap output is not a valid PNG",
                    details={"path": str(output_path), "first_bytes_hex": header.hex()},
                )
            )
        return ok(output_path)

    async def start_recording(self, serial: str, output_path: Path) -> Result[None]:
        if serial in self._recordings:
            return err(AdbFailure(message=f"recording already in progress for {serial}"))
        remote = f"/sdcard/mcp_record_{abs(hash(output_path)) & 0xFFFFFFFF}.mp4"
        proc = await self._adb._runner.stream(  # noqa: SLF001 — single intentional escape hatch
            ["adb", "-s", serial, "shell", "screenrecord", remote]
        )
        self._recordings[serial] = (proc, remote, output_path)
        return ok(None)

    async def stop_recording(self, serial: str) -> Result[Path]:
        entry = self._recordings.pop(serial, None)
        if entry is None:
            return err(AdbFailure(message=f"no active recording for {serial}"))
        proc, remote, local = entry
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        # Pull the file. screenrecord finalizes on SIGTERM; give it a moment.
        await asyncio.sleep(0.5)
        local.parent.mkdir(parents=True, exist_ok=True)
        pull = await self._adb.pull(serial, remote, local)
        if not pull.ok:
            return err(AdbFailure(message="failed to pull recording", details={"stderr": pull.stderr}))
        await self._adb.shell(serial, "rm", "-f", remote, timeout_s=5.0)
        return ok(local)

    async def read_logs(
        self,
        serial: str,
        since_s: int = 30,
        tag: str | None = None,
        min_level: LogLevel = LogLevel.WARN,
        max_lines: int = 500,
    ) -> Result[list[LogEntry]]:
        result = await self._adb.logcat_dump(serial, since_s=since_s)
        if not result.ok:
            return err(AdbFailure(message="logcat failed", details={"stderr": result.stderr}))
        entries = parse_logcat_threadtime(result.stdout, max_lines=max_lines * 4)
        threshold = _LEVEL_ORDER[min_level]
        filtered = [
            e
            for e in entries
            if _LEVEL_ORDER[e.level] >= threshold and (tag is None or e.tag == tag)
        ]
        return ok(filtered[-max_lines:])

    async def tail_logs_until(
        self,
        serial: str,
        until_pattern: str,
        tag: str | None = None,
        timeout_s: float = 30.0,
    ) -> Result[list[LogEntry]]:
        pattern = re.compile(until_pattern)
        proc = await self._adb.logcat_stream(serial)
        collected: list[LogEntry] = []
        deadline = asyncio.get_event_loop().time() + timeout_s
        try:
            assert proc.stdout is not None
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    proc.terminate()
                    return err(
                        TimeoutFailure(
                            message="tail_logs_until timed out",
                            details={"pattern": until_pattern, "timeout_s": timeout_s},
                        )
                    )
                try:
                    raw = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
                except asyncio.TimeoutError:
                    proc.terminate()
                    return err(TimeoutFailure(message="tail_logs_until timed out"))
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").rstrip()
                parsed = parse_logcat_threadtime(line, max_lines=1)
                if not parsed:
                    continue
                entry = parsed[0]
                if tag is not None and entry.tag != tag:
                    continue
                collected.append(entry)
                if pattern.search(entry.message):
                    proc.terminate()
                    return ok(collected)
        finally:
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    proc.kill()
        return ok(collected)

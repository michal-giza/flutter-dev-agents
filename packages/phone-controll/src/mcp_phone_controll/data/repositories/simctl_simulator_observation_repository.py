"""ObservationRepository implementation for iOS Simulators."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from ...domain.entities import LogEntry, LogLevel
from ...domain.failures import FlutterCliFailure, TimeoutFailure
from ...domain.repositories import ObservationRepository
from ...domain.result import Result, err, ok
from ...infrastructure.simctl_client import SimctlClient


# Apple `log stream` levels → our LogLevel
_LOG_LEVEL = {
    "Debug": LogLevel.DEBUG,
    "Default": LogLevel.INFO,
    "Info": LogLevel.INFO,
    "Notice": LogLevel.INFO,
    "Error": LogLevel.ERROR,
    "Fault": LogLevel.FATAL,
}

_LEVEL_ORDER = {
    LogLevel.VERBOSE: 0,
    LogLevel.DEBUG: 1,
    LogLevel.INFO: 2,
    LogLevel.WARN: 3,
    LogLevel.ERROR: 4,
    LogLevel.FATAL: 5,
}


def _parse_log_stream_line(line: str) -> LogEntry | None:
    """Parse a single `log stream` line. Format varies; best-effort.

    Typical: `<timestamp> <pid:tid> <level> <subsystem>: <message>`
    """
    parts = line.strip().split(None, 4)
    if len(parts) < 5:
        return None
    timestamp_a, timestamp_b, pid_tid, level_token, rest = parts
    level = _LOG_LEVEL.get(level_token, LogLevel.INFO)
    if ":" in rest:
        tag, message = rest.split(":", 1)
        message = message.strip()
    else:
        tag, message = "ios-sim", rest
    pid: int | None
    try:
        pid = int(pid_tid.split(":", 1)[0])
    except ValueError:
        pid = None
    return LogEntry(
        timestamp=f"{timestamp_a} {timestamp_b}",
        level=level,
        tag=tag.strip(),
        pid=pid,
        message=message,
    )


async def _terminate(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=2.0)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()


class SimctlSimulatorObservationRepository(ObservationRepository):
    def __init__(self, client: SimctlClient) -> None:
        self._client = client

    async def screenshot(self, serial: str, output_path: Path) -> Result[Path]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result = await self._client.screenshot_to(serial, output_path)
        if not result.ok or not output_path.exists():
            return err(
                FlutterCliFailure(
                    message="simctl screenshot failed",
                    details={"stderr": result.stderr},
                    next_action="check_simulator_booted",
                )
            )
        # Quick PNG signature check — simctl writes PNG by default.
        with output_path.open("rb") as fh:
            header = fh.read(8)
        if header[:8] != b"\x89PNG\r\n\x1a\n":
            return err(
                FlutterCliFailure(
                    message="simctl screenshot did not produce a valid PNG",
                    details={"first_bytes_hex": header.hex()},
                )
            )
        return ok(output_path)

    async def start_recording(self, serial: str, output_path: Path) -> Result[None]:
        return err(
            FlutterCliFailure(
                message=(
                    "simulator screen recording uses `simctl io recordVideo` which is "
                    "long-running and not yet wired into this repo"
                ),
                next_action="use_xcode",
            )
        )

    async def stop_recording(self, serial: str) -> Result[Path]:
        return err(
            FlutterCliFailure(
                message="simulator screen recording is not yet wired",
            )
        )

    async def read_logs(
        self,
        serial: str,
        since_s: int = 30,
        tag: str | None = None,
        min_level: LogLevel = LogLevel.WARN,
        max_lines: int = 500,
    ) -> Result[list[LogEntry]]:
        try:
            proc = await self._client.log_stream(serial)
        except FileNotFoundError as e:
            return err(FlutterCliFailure(message=f"xcrun not on PATH: {e}"))

        threshold = _LEVEL_ORDER[min_level]
        entries: list[LogEntry] = []
        deadline = asyncio.get_event_loop().time() + since_s

        try:
            assert proc.stdout is not None
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    break
                try:
                    raw = await asyncio.wait_for(
                        proc.stdout.readline(), timeout=remaining
                    )
                except asyncio.TimeoutError:
                    break
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").rstrip()
                entry = _parse_log_stream_line(line)
                if entry is None:
                    continue
                if _LEVEL_ORDER[entry.level] < threshold:
                    continue
                if tag is not None and entry.tag != tag:
                    continue
                entries.append(entry)
                if len(entries) >= max_lines:
                    break
        finally:
            await _terminate(proc)

        return ok(entries[-max_lines:])

    async def tail_logs_until(
        self,
        serial: str,
        until_pattern: str,
        tag: str | None = None,
        timeout_s: float = 30.0,
    ) -> Result[list[LogEntry]]:
        try:
            proc = await self._client.log_stream(serial)
        except FileNotFoundError as e:
            return err(FlutterCliFailure(message=f"xcrun not on PATH: {e}"))

        pattern = re.compile(until_pattern)
        collected: list[LogEntry] = []
        deadline = asyncio.get_event_loop().time() + timeout_s

        try:
            assert proc.stdout is not None
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    return err(
                        TimeoutFailure(
                            message="tail_logs_until timed out",
                            details={"pattern": until_pattern, "timeout_s": timeout_s},
                        )
                    )
                try:
                    raw = await asyncio.wait_for(
                        proc.stdout.readline(), timeout=remaining
                    )
                except asyncio.TimeoutError:
                    return err(TimeoutFailure(message="tail_logs_until timed out"))
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").rstrip()
                entry = _parse_log_stream_line(line)
                if entry is None:
                    continue
                if tag is not None and entry.tag != tag:
                    continue
                collected.append(entry)
                if pattern.search(entry.message):
                    return ok(collected)
        finally:
            await _terminate(proc)

        return ok(collected)

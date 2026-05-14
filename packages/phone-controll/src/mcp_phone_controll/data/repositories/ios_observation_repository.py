"""ObservationRepository implementation for iOS.

- screenshot: pymobiledevice3 developer screenshot (requires tunneld + DDI)
- start/stop_recording: NOT SUPPORTED on iOS via pymobiledevice3 — returns Failure
- read_logs / tail_logs_until: stream `pymobiledevice3 syslog live` and tear down
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from ...domain.entities import LogEntry, LogLevel
from ...domain.failures import FlutterCliFailure, TimeoutFailure
from ...domain.repositories import ObservationRepository
from ...domain.result import Result, err, ok
from ...infrastructure.pymobiledevice3_cli import PyMobileDevice3Cli

# Apple oslog severities mapped to our LogLevel.
_OSLOG_LEVEL = {
    "default": LogLevel.INFO,
    "info": LogLevel.INFO,
    "debug": LogLevel.DEBUG,
    "notice": LogLevel.INFO,
    "warn": LogLevel.WARN,
    "warning": LogLevel.WARN,
    "error": LogLevel.ERROR,
    "fault": LogLevel.FATAL,
}

_LEVEL_ORDER = {
    LogLevel.VERBOSE: 0,
    LogLevel.DEBUG: 1,
    LogLevel.INFO: 2,
    LogLevel.WARN: 3,
    LogLevel.ERROR: 4,
    LogLevel.FATAL: 5,
}


def _parse_oslog_line(line: str) -> LogEntry | None:
    """Parse a single os_log line. Format varies; best-effort extraction."""
    parts = line.strip().split(None, 4)
    if len(parts) < 5:
        return None
    timestamp_a, timestamp_b, pid_s, level_token, rest = parts
    level = _OSLOG_LEVEL.get(level_token.lower(), LogLevel.INFO)
    if ":" in rest:
        tag, message = rest.split(":", 1)
        message = message.strip()
    else:
        tag, message = "ios", rest
    try:
        pid = int(pid_s)
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
    except TimeoutError:
        proc.kill()
        await proc.wait()


class IosObservationRepository(ObservationRepository):
    def __init__(self, cli: PyMobileDevice3Cli) -> None:
        self._cli = cli

    async def screenshot(self, serial: str, output_path: Path) -> Result[Path]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result = await self._cli.screenshot(serial, output_path)
        if not result.ok or not output_path.exists():
            stderr = result.stderr or ""
            # Detect the canonical "no tunneld running" failure surface and
            # emit a structured next_action so autonomous agents switch on it.
            tunneld_hint = (
                "Tunneld" in stderr
                or "tunneld" in stderr
                or "Unable to connect to Tunneld" in stderr
            )
            details: dict = {"stderr": stderr}
            next_action = None
            if tunneld_hint:
                details["fix_command"] = (
                    "sudo pymobiledevice3 remote tunneld   "
                    "(leave running in a separate terminal)"
                )
                details["docs_url"] = "docs/ios_setup.md#tunneld"
                next_action = "start_tunneld"
            else:
                details["hint"] = (
                    "Run `sudo pymobiledevice3 remote tunneld` once; "
                    "see docs/ios_setup.md."
                )
            return err(
                FlutterCliFailure(
                    message="iOS screenshot failed",
                    details=details,
                    next_action=next_action,
                )
            )
        return ok(output_path)

    async def start_recording(self, serial: str, output_path: Path) -> Result[None]:
        return err(
            FlutterCliFailure(
                message="iOS screen recording is not supported via pymobiledevice3",
                details={"workaround": "use Xcode/QuickTime or `xrecord`"},
            )
        )

    async def stop_recording(self, serial: str) -> Result[Path]:
        return err(
            FlutterCliFailure(
                message="iOS screen recording is not supported via pymobiledevice3"
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
        """Stream `syslog live` for `since_s` seconds, then return filtered lines."""
        try:
            proc = await self._cli.syslog_live_stream(serial)
        except FileNotFoundError as e:
            return err(FlutterCliFailure(message=f"pymobiledevice3 not on PATH: {e}"))

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
                    raw = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
                except TimeoutError:
                    break
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").rstrip()
                entry = _parse_oslog_line(line)
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
        """Stream syslog until pattern matches a line, or timeout."""
        try:
            proc = await self._cli.syslog_live_stream(serial)
        except FileNotFoundError as e:
            return err(FlutterCliFailure(message=f"pymobiledevice3 not on PATH: {e}"))

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
                    raw = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
                except TimeoutError:
                    return err(TimeoutFailure(message="tail_logs_until timed out"))
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").rstrip()
                entry = _parse_oslog_line(line)
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

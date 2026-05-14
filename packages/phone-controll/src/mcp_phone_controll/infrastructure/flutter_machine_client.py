"""Async client for `flutter run --machine` daemon protocol.

Spawns one long-lived `flutter run --machine` subprocess per session, reads
its line-delimited JSON output, dispatches commands, and pushes events into
a per-session ring buffer that observers can drain.

The daemon protocol over stdio:
- Commands written as `[{"id": <int>, "method": "...", "params": {...}}]\\n`
- Responses come back as `[{"id": <int>, "result": <any>}]` or with `error`
- Events come back as `[{"event": "...", "params": {...}}]` (no id)
"""

from __future__ import annotations

import asyncio
import json
from collections import deque
from pathlib import Path
from typing import Any

from ..data.parsers.flutter_machine_event_parser import (
    app_id_from_started,
    event_to_log,
    parse_machine_line,
    vm_service_uri_from_started,
)
from ..domain.entities import DebugLogEntry
from .flutter_cli import FlutterCli


class _PendingRequest:
    __slots__ = ("future",)

    def __init__(self) -> None:
        self.future: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()


class FlutterMachineClient:
    """One running `flutter run --machine` subprocess.

    Lifecycle is owned by the caller — call .start(), .send(), .stop().
    The client maintains a 5000-entry ring buffer of DebugLogEntry from the
    daemon's event stream so observers can read recent logs cheaply.
    """

    BUFFER_CAPACITY = 5000

    def __init__(self, flutter: FlutterCli) -> None:
        self._flutter = flutter
        self._proc: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._next_id = 1
        self._pending: dict[int, _PendingRequest] = {}
        self._events: deque[dict[str, Any]] = deque(maxlen=self.BUFFER_CAPACITY)
        self._log_buffer: deque[DebugLogEntry] = deque(maxlen=self.BUFFER_CAPACITY)
        self._app_id: str | None = None
        self._vm_service_uri: str | None = None
        self._started_event = asyncio.Event()

    @property
    def app_id(self) -> str | None:
        return self._app_id

    @property
    def vm_service_uri(self) -> str | None:
        return self._vm_service_uri

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc is not None else None

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def start(
        self,
        project_path: Path,
        device_serial: str,
        mode: str = "debug",
        flavor: str | None = None,
        target: str | None = None,
        startup_timeout_s: float = 120.0,
    ) -> None:
        """Spawn the subprocess and wait for app.started to fire."""
        argv = [
            self._flutter._flutter,
            "run",
            "--machine",
            f"--{mode}",
            "-d",
            device_serial,
        ]
        if flavor:
            argv += ["--flavor", flavor]
        if target:
            argv += ["--target", target]

        self._proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(project_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        try:
            await asyncio.wait_for(self._started_event.wait(), timeout=startup_timeout_s)
        except TimeoutError:
            await self.stop()
            raise

    async def stop(self) -> None:
        """Send app.stop, then terminate the subprocess if still alive."""
        if self._proc is None:
            return
        try:
            if self._app_id:
                await self.send("app.stop", {"appId": self._app_id}, response_timeout_s=10.0)
        except Exception:
            pass
        if self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5.0)
            except TimeoutError:
                self._proc.kill()
                await self._proc.wait()
        if self._reader_task is not None:
            self._reader_task.cancel()

    async def restart(self, full_restart: bool = False, timeout_s: float = 60.0) -> dict[str, Any]:
        if not self._app_id:
            raise RuntimeError("session has no app_id yet (not started?)")
        return await self.send(
            "app.restart",
            {"appId": self._app_id, "fullRestart": full_restart},
            response_timeout_s=timeout_s,
        )

    async def send(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        response_timeout_s: float = 30.0,
    ) -> dict[str, Any]:
        """Send a daemon command and await its response."""
        if self._proc is None or self._proc.stdin is None:
            raise RuntimeError("subprocess not running")
        request_id = self._next_id
        self._next_id += 1
        pending = _PendingRequest()
        self._pending[request_id] = pending
        payload = {"id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        line = "[" + json.dumps(payload) + "]\n"
        self._proc.stdin.write(line.encode("utf-8"))
        await self._proc.stdin.drain()
        try:
            return await asyncio.wait_for(pending.future, timeout=response_timeout_s)
        finally:
            self._pending.pop(request_id, None)

    def recent_logs(self, n: int = 500) -> list[DebugLogEntry]:
        """Snapshot the most-recent n entries from the log ring buffer."""
        if n >= len(self._log_buffer):
            return list(self._log_buffer)
        return list(self._log_buffer)[-n:]

    async def _read_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        try:
            while True:
                raw = await self._proc.stdout.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").rstrip()
                for obj in parse_machine_line(line):
                    self._dispatch(obj)
        except asyncio.CancelledError:
            return
        except Exception:
            return

    def _dispatch(self, obj: dict[str, Any]) -> None:
        # Response to a previous command
        if "id" in obj:
            request_id = obj.get("id")
            if isinstance(request_id, int):
                pending = self._pending.get(request_id)
                if pending and not pending.future.done():
                    pending.future.set_result(obj)
            return
        # Daemon event
        if "event" in obj:
            self._events.append(obj)
            log = event_to_log(obj)
            if log is not None:
                self._log_buffer.append(log)
            if obj.get("event") == "app.started":
                app_id = app_id_from_started(obj)
                if app_id:
                    self._app_id = app_id
                self._started_event.set()
            uri = vm_service_uri_from_started(obj)
            if uri:
                self._vm_service_uri = uri

"""DebugSessionRepository implementation backed by FlutterMachineClient.

Owns one FlutterMachineClient per active session. Enforces the device-lock
contract: starting a session requires the lock on the target serial to be
held by THIS MCP's session_id (so we never thrash a phone owned by another
Claude session).
"""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from ...domain.entities import (
    BuildMode,
    DebugLogEntry,
    DebugSession,
    DebugSessionState,
    ServiceExtensionResult,
)
from ...domain.failures import (
    DebugSessionFailure,
    DeviceBusyFailure,
    HotReloadFailure,
    ServiceExtensionFailure,
)
from ...domain.repositories import DebugSessionRepository, DeviceLockRepository
from ...domain.result import Err, Result, err, ok
from ...infrastructure.flutter_cli import FlutterCli
from ...infrastructure.flutter_machine_client import FlutterMachineClient


class FlutterDebugSessionRepository(DebugSessionRepository):
    def __init__(
        self,
        flutter: FlutterCli,
        locks: DeviceLockRepository,
        session_id: str,
    ) -> None:
        self._flutter = flutter
        self._locks = locks
        self._session_id = session_id
        self._sessions: dict[str, _Active] = {}
        self._most_recent: str | None = None
        self._mutex = asyncio.Lock()

    # ----- start / stop / restart ------------------------------------

    async def start(
        self,
        project_path: Path,
        device_serial: str,
        mode: BuildMode = BuildMode.DEBUG,
        flavor: str | None = None,
        target: str | None = None,
    ) -> Result[DebugSession]:
        # Enforce that this MCP session owns the device lock.
        lock_res = await self._locks.lock_for(device_serial)
        if isinstance(lock_res, Err):
            return lock_res
        lock = lock_res.value
        if lock is None or lock.session_id != self._session_id:
            holder = lock.session_id if lock else "no one"
            return err(
                DeviceBusyFailure(
                    message=(
                        f"start_debug_session requires this session to hold the lock "
                        f"on {device_serial} (held by {holder})"
                    ),
                    details={
                        "serial": device_serial,
                        "this_session_id": self._session_id,
                        "holder_session_id": lock.session_id if lock else None,
                    },
                    next_action="select_device_first",
                )
            )

        client = FlutterMachineClient(self._flutter)
        try:
            await client.start(
                project_path=project_path,
                device_serial=device_serial,
                mode=mode.value,
                flavor=flavor,
                target=target,
            )
        except FileNotFoundError as e:
            return err(
                DebugSessionFailure(
                    message=f"flutter binary not found: {e}",
                    next_action="install_flutter",
                )
            )
        except asyncio.TimeoutError:
            return err(
                DebugSessionFailure(
                    message="`flutter run --machine` did not emit app.started within timeout",
                    next_action="check_environment",
                )
            )
        except Exception as e:  # noqa: BLE001
            return err(
                DebugSessionFailure(
                    message=f"failed to start debug session: {e}",
                    next_action="check_environment",
                )
            )

        sid = uuid.uuid4().hex[:12]
        active = _Active(
            session_id=sid,
            client=client,
            project_path=project_path,
            device_serial=device_serial,
            mode=mode,
            flavor=flavor,
            target=target,
            started_at=datetime.now(),
            state=DebugSessionState.RUNNING,
        )
        async with self._mutex:
            self._sessions[sid] = active
            self._most_recent = sid
        return ok(active.snapshot())

    async def stop(self, session_id: str | None = None) -> Result[None]:
        target_id = session_id or self._most_recent
        if target_id is None:
            return ok(None)
        async with self._mutex:
            active = self._sessions.pop(target_id, None)
            if self._most_recent == target_id:
                self._most_recent = next(iter(reversed(self._sessions.keys())), None)
        if active is None:
            return ok(None)
        try:
            await active.client.stop()
        except Exception as e:  # noqa: BLE001
            return err(
                DebugSessionFailure(
                    message=f"failed to stop debug session: {e}",
                )
            )
        return ok(None)

    async def restart(
        self, session_id: str | None = None, full_restart: bool = False
    ) -> Result[DebugSession]:
        active = await self._resolve(session_id)
        if active is None:
            return err(
                HotReloadFailure(
                    message="no active debug session",
                    next_action="start_debug_session",
                )
            )
        active.state = DebugSessionState.RELOADING
        try:
            response = await active.client.restart(full_restart=full_restart)
        except Exception as e:  # noqa: BLE001
            active.state = DebugSessionState.ERRORED
            return err(HotReloadFailure(message=f"hot reload failed: {e}"))
        if "error" in response:
            active.state = DebugSessionState.ERRORED
            return err(
                HotReloadFailure(
                    message=str(response.get("error")),
                    details={"response": response},
                )
            )
        active.state = DebugSessionState.RUNNING
        return ok(active.snapshot())

    async def attach(
        self, vm_service_uri: str, project_path: Path
    ) -> Result[DebugSession]:
        # Attach is documented as advanced; we don't implement the full flow yet.
        # Return a clean InvalidArgumentFailure-style error so agents know to skip.
        return err(
            DebugSessionFailure(
                message="attach_debug_session is not yet implemented",
                details={"vm_service_uri": vm_service_uri},
                next_action="ask_user",
            )
        )

    # ----- introspection --------------------------------------------

    async def list_sessions(self) -> Result[list[DebugSession]]:
        async with self._mutex:
            return ok([active.snapshot() for active in self._sessions.values()])

    async def read_log(
        self,
        session_id: str | None = None,
        since_s: int = 30,
        level: str = "all",
        max_lines: int = 500,
    ) -> Result[list[DebugLogEntry]]:
        active = await self._resolve(session_id)
        if active is None:
            return err(
                DebugSessionFailure(
                    message="no active debug session",
                    next_action="start_debug_session",
                )
            )
        cutoff = datetime.now().timestamp() - since_s
        filtered = [
            entry
            for entry in active.client.recent_logs(max_lines * 4)
            if entry.timestamp.timestamp() >= cutoff
            and (level == "all" or entry.level == level)
        ]
        return ok(filtered[-max_lines:])

    async def tail_log(
        self,
        session_id: str | None,
        until_pattern: str,
        timeout_s: float = 30.0,
    ) -> Result[list[DebugLogEntry]]:
        active = await self._resolve(session_id)
        if active is None:
            return err(
                DebugSessionFailure(
                    message="no active debug session",
                    next_action="start_debug_session",
                )
            )
        pattern = re.compile(until_pattern)
        deadline = asyncio.get_event_loop().time() + timeout_s
        last_seen = len(active.client.recent_logs(active.client.BUFFER_CAPACITY))
        while asyncio.get_event_loop().time() < deadline:
            entries = active.client.recent_logs(active.client.BUFFER_CAPACITY)
            for entry in entries[last_seen:]:
                if pattern.search(entry.message):
                    return ok(entries)
            last_seen = len(entries)
            await asyncio.sleep(0.1)
        return ok(active.client.recent_logs(500))

    async def call_service_extension(
        self,
        session_id: str | None,
        method: str,
        args: dict | None = None,
    ) -> Result[ServiceExtensionResult]:
        active = await self._resolve(session_id)
        if active is None:
            return err(
                DebugSessionFailure(
                    message="no active debug session",
                    next_action="start_debug_session",
                )
            )
        if not active.client.app_id:
            return err(
                ServiceExtensionFailure(
                    message="session has no app_id (not fully started?)",
                )
            )
        params: dict[str, Any] = {"appId": active.client.app_id, "methodName": method}
        if args is not None:
            params["params"] = args
        started = asyncio.get_event_loop().time()
        try:
            response = await active.client.send("app.callServiceExtension", params)
        except Exception as e:  # noqa: BLE001
            return err(ServiceExtensionFailure(message=f"call failed: {e}"))
        elapsed_ms = int((asyncio.get_event_loop().time() - started) * 1000)
        if "error" in response:
            return err(
                ServiceExtensionFailure(
                    message=str(response.get("error")),
                    details={"method": method, "response": response},
                )
            )
        return ok(
            ServiceExtensionResult(
                method=method,
                result=response.get("result") or {},
                elapsed_ms=elapsed_ms,
            )
        )

    # ----- helpers --------------------------------------------------

    async def _resolve(self, session_id: str | None) -> "_Active | None":
        target_id = session_id or self._most_recent
        if target_id is None:
            return None
        async with self._mutex:
            return self._sessions.get(target_id)

    async def stop_all(self) -> None:
        """For atexit cleanup."""
        async with self._mutex:
            sessions = list(self._sessions.values())
            self._sessions.clear()
            self._most_recent = None
        for active in sessions:
            try:
                await active.client.stop()
            except Exception:  # noqa: BLE001
                continue


class _Active:
    """Internal record bundling DebugSession entity with its live client."""

    __slots__ = (
        "session_id", "client", "project_path", "device_serial",
        "mode", "flavor", "target", "started_at", "state",
    )

    def __init__(
        self,
        session_id: str,
        client: FlutterMachineClient,
        project_path: Path,
        device_serial: str,
        mode: BuildMode,
        flavor: str | None,
        target: str | None,
        started_at: datetime,
        state: DebugSessionState,
    ) -> None:
        self.session_id = session_id
        self.client = client
        self.project_path = project_path
        self.device_serial = device_serial
        self.mode = mode
        self.flavor = flavor
        self.target = target
        self.started_at = started_at
        self.state = state

    def snapshot(self) -> DebugSession:
        return DebugSession(
            id=self.session_id,
            project_path=self.project_path,
            device_serial=self.device_serial,
            mode=self.mode,
            started_at=self.started_at,
            state=self.state,
            app_id=self.client.app_id,
            vm_service_uri=self.client.vm_service_uri,
            flavor=self.flavor,
            target=self.target,
            pid=self.client.pid,
        )

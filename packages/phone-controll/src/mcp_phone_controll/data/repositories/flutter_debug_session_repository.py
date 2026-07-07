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
from ...infrastructure.debug_session_store import DebugSessionStore
from ...infrastructure.flutter_cli import FlutterCli
from ...infrastructure.flutter_machine_client import FlutterMachineClient
from ...observability import emit

# Flutter "web" device ids (`flutter run -d <id>`). These aren't physical
# devices we lock — `flutter run -d chrome --machine` launches a browser +
# DWDS, speaking the SAME daemon protocol as a phone, so the whole
# debug-session stack (hot reload, service extensions, logs, frame/heap
# profiling) works unchanged. We just skip the adb device-lock for them:
# there's nothing to contend on, and multiple web sessions can coexist.
_WEB_DEVICE_IDS = frozenset({"chrome", "web-server"})


class FlutterDebugSessionRepository(DebugSessionRepository):
    def __init__(
        self,
        flutter: FlutterCli,
        locks: DeviceLockRepository,
        session_id: str,
        client_factory=None,
        store: DebugSessionStore | None = None,
    ) -> None:
        self._flutter = flutter
        self._locks = locks
        self._session_id = session_id
        self._sessions: dict[str, _Active] = {}
        self._most_recent: str | None = None
        self._mutex = asyncio.Lock()
        # Injectable for tests; defaults to a real FlutterMachineClient.
        self._client_factory = client_factory or (lambda f: FlutterMachineClient(f))
        # Durable registry so sessions survive an MCP restart. Records
        # loaded here are candidates for re-attach — not yet connected; a
        # `list_sessions()` (or attach) probes each and revives the ones
        # whose VM Service is still reachable, pruning the dead.
        self._store = store if store is not None else DebugSessionStore()
        self._reattach: dict[str, dict] = {
            rec["id"]: rec for rec in self._store.load()
        }

    # ----- start / stop / restart ------------------------------------

    async def start(
        self,
        project_path: Path,
        device_serial: str,
        mode: BuildMode = BuildMode.DEBUG,
        flavor: str | None = None,
        target: str | None = None,
    ) -> Result[DebugSession]:
        # Web targets (chrome / web-server) aren't lockable physical
        # devices — skip the lock entirely. For real devices, enforce that
        # this MCP session owns the lock.
        is_web = device_serial in _WEB_DEVICE_IDS
        if not is_web:
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

        client = self._client_factory(self._flutter)
        try:
            await client.start(
                project_path=project_path,
                device_serial=device_serial,
                mode=mode.value,
                flavor=flavor,
                target=target,
                # Web (DWDS) connects its debug service after app.started —
                # wait for the VM Service URI so the session is attachable.
                await_vm_service=is_web,
            )
        except FileNotFoundError as e:
            return err(
                DebugSessionFailure(
                    message=f"flutter binary not found: {e}",
                    next_action="install_flutter",
                )
            )
        except TimeoutError:
            return err(
                DebugSessionFailure(
                    message="`flutter run --machine` did not emit app.started within timeout",
                    next_action="check_environment",
                )
            )
        except Exception as e:
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
        self._store.upsert(active.to_record())
        return ok(active.snapshot())

    async def stop(self, session_id: str | None = None) -> Result[None]:
        target_id = session_id or self._most_recent
        if target_id is None:
            # Might still be a persisted-but-not-yet-materialised session.
            return ok(None)
        async with self._mutex:
            active = self._sessions.pop(target_id, None)
            self._reattach.pop(target_id, None)
            if self._most_recent == target_id:
                self._most_recent = next(iter(reversed(self._sessions.keys())), None)
        # Drop it from the durable store either way.
        self._store.remove(target_id)
        if active is None:
            return ok(None)
        # A re-attached session has no daemon client to stop — we only
        # detach (already removed from the registry). We do NOT kill the
        # app: it wasn't ours to start, and the whole point is it's alive.
        if active.client is None:
            return ok(None)
        try:
            await active.client.stop()
        except Exception as e:
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
        if active.client is None:
            return err(
                HotReloadFailure(
                    message=(
                        "this is a re-attached session (VM Service only) — hot "
                        "reload/restart needs the `flutter --machine` daemon, "
                        "which didn't survive the MCP restart. Service "
                        "extensions, widget-tree and vm_evaluate still work. "
                        "Run start_debug_session for a fresh daemon-backed "
                        "session that can hot reload."
                    ),
                    next_action="start_debug_session",
                )
            )
        active.state = DebugSessionState.RELOADING
        try:
            response = await active.client.restart(full_restart=full_restart)
        except Exception as e:
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
        self,
        vm_service_uri: str,
        project_path: Path,
        *,
        device_serial: str = "attached",
        session_id: str | None = None,
        mode: BuildMode = BuildMode.DEBUG,
        flavor: str | None = None,
        target: str | None = None,
    ) -> Result[DebugSession]:
        """Attach to an already-running app by its VM Service ws URI —
        without a `flutter --machine` daemon. Probes reachability, then
        registers a client-less session that services VM-Service ops
        (service extensions / widget-tree / vm_evaluate) via the direct
        VmServiceClient. This is also the re-attach path after an MCP
        restart. It CANNOT hot reload (no daemon)."""
        probe = await self._probe(vm_service_uri)
        if isinstance(probe, Err):
            return probe

        sid = session_id or uuid.uuid4().hex[:12]
        active = _Active(
            session_id=sid,
            client=None,
            project_path=project_path,
            device_serial=device_serial,
            mode=mode,
            flavor=flavor,
            target=target,
            started_at=datetime.now(),
            state=DebugSessionState.RUNNING,
            vm_service_uri=vm_service_uri,
        )
        async with self._mutex:
            self._sessions[sid] = active
            self._reattach.pop(sid, None)
            self._most_recent = sid
        self._store.upsert(active.to_record())
        emit("debug_session_attached", level="info", session_id=sid, uri=vm_service_uri)
        return ok(active.snapshot())

    async def _probe(self, uri: str) -> Result[str]:
        """Return ok(isolate_id) if the VM Service is reachable, else a
        typed Err. Connect + read one isolate, then close."""
        from ...infrastructure.vm_service_client import VmServiceClient

        client = VmServiceClient(uri)
        try:
            try:
                await client.connect()
            except ImportError as e:
                return err(
                    DebugSessionFailure(
                        message=str(e), next_action="install_debug_extras"
                    )
                )
            except Exception as e:
                return err(
                    DebugSessionFailure(
                        message=f"VM Service not reachable at {uri}: {e}",
                        details={"vm_service_uri": uri},
                        next_action="check_debug_session",
                    )
                )
            isolate_id = await client.first_isolate_id()
            if not isolate_id:
                return err(
                    DebugSessionFailure(
                        message=f"VM Service at {uri} has no isolate",
                        next_action="check_debug_session",
                    )
                )
            return ok(isolate_id)
        finally:
            await client.close()

    # ----- introspection --------------------------------------------

    async def list_sessions(self) -> Result[list[DebugSession]]:
        # Auto-reattach: revive persisted sessions whose VM Service is
        # still reachable (survived an MCP restart), prune the dead. This
        # is what makes list_debug_sessions "just work" after a restart.
        await self._reconcile_reattach()
        async with self._mutex:
            return ok([active.snapshot() for active in self._sessions.values()])

    async def _reconcile_reattach(self) -> None:
        async with self._mutex:
            pending = [
                rec for sid, rec in self._reattach.items()
                if sid not in self._sessions
            ]
        for rec in pending:
            sid = rec["id"]
            uri = rec.get("vm_service_uri")
            if not uri:
                async with self._mutex:
                    self._reattach.pop(sid, None)
                self._store.remove(sid)
                continue
            probe = await self._probe(uri)
            if isinstance(probe, Err):
                async with self._mutex:
                    self._reattach.pop(sid, None)
                self._store.remove(sid)
                emit(
                    "debug_session_reattach_pruned",
                    level="info", session_id=sid, uri=uri,
                )
                continue
            active = _Active(
                session_id=sid,
                client=None,
                project_path=Path(rec.get("project_path") or "."),
                device_serial=rec.get("device_serial") or "attached",
                mode=_mode_from(rec.get("mode")),
                flavor=rec.get("flavor"),
                target=rec.get("target"),
                started_at=_dt_from(rec.get("started_at")),
                state=DebugSessionState.RUNNING,
                vm_service_uri=uri,
                app_id=rec.get("app_id"),
            )
            async with self._mutex:
                self._sessions[sid] = active
                self._reattach.pop(sid, None)
                if self._most_recent is None:
                    self._most_recent = sid
            emit("debug_session_reattached", level="info", session_id=sid, uri=uri)

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
        if active.client is None:
            return err(_reattached_no_daemon("read_debug_log"))
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
        if active.client is None:
            return err(_reattached_no_daemon("tail_debug_log"))
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
        # Route through the DIRECT VM Service when either:
        #  - web (DWDS): the daemon's app.callServiceExtension proxy doesn't
        #    reach the app isolate, but the direct VM Service does; or
        #  - re-attached (client is None): there's no daemon at all, only
        #    the VM Service ws URI.
        # ext.flutter.* register a few seconds after the app loads, so the
        # web path retries on -32601 (method-not-found) until ready.
        if active.client is None or active.device_serial in _WEB_DEVICE_IDS:
            return await self._call_service_extension_web(active, method, args)
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
        except Exception as e:
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

    async def _call_service_extension_web(
        self,
        active: _Active,
        method: str,
        args: dict | None,
        ext_timeout_s: float = 20.0,
    ) -> Result[ServiceExtensionResult]:
        uri = active.vm_uri
        if not uri:
            return err(
                ServiceExtensionFailure(
                    message="web session has no vm_service_uri yet",
                    next_action="check_debug_session",
                )
            )
        from ...infrastructure.vm_service_client import VmServiceClient

        loop = asyncio.get_event_loop()
        started = loop.time()
        client = VmServiceClient(uri)
        try:
            try:
                await client.connect()
            except ImportError as e:
                return err(
                    ServiceExtensionFailure(
                        message=str(e), next_action="install_debug_extras"
                    )
                )
            isolate_id = await client.first_isolate_id()
            if not isolate_id:
                return err(
                    ServiceExtensionFailure(
                        message="no isolate on the web VM service"
                    )
                )
            deadline = loop.time() + ext_timeout_s
            while True:
                resp = await client.call_service_extension(isolate_id, method, args)
                if "result" in resp:
                    elapsed_ms = int((loop.time() - started) * 1000)
                    return ok(
                        ServiceExtensionResult(
                            method=method,
                            result=resp.get("result") or {},
                            elapsed_ms=elapsed_ms,
                        )
                    )
                error = resp.get("error") or {}
                # -32601 = method not found: ext.flutter.* register a few
                # seconds after the web app boots — retry until they do.
                if error.get("code") == -32601:
                    if loop.time() < deadline:
                        await asyncio.sleep(1.0)
                        continue
                    # Still unregistered after the window — the app likely
                    # never reached its first frame (e.g. it's waiting on a
                    # backend, or threw before runApp). Not a plumbing bug.
                    return err(
                        ServiceExtensionFailure(
                            message=(
                                f"service extension {method} not registered after "
                                f"{ext_timeout_s:.0f}s — the web app hasn't reached "
                                "its first frame (ext.flutter.* register on "
                                "WidgetsBinding init). Confirm the app actually "
                                "renders in the browser (deps/backend up?)."
                            ),
                            details={"method": method, "response": resp},
                            next_action="check_debug_session",
                        )
                    )
                return err(
                    ServiceExtensionFailure(
                        message=str(error.get("message", error)),
                        details={"method": method, "response": resp},
                    )
                )
        except Exception as e:
            return err(
                ServiceExtensionFailure(
                    message=f"web service extension call failed: {e}"
                )
            )
        finally:
            await client.close()

    # ----- helpers --------------------------------------------------

    async def _resolve(self, session_id: str | None) -> _Active | None:
        target_id = session_id or self._most_recent
        if target_id is None:
            return None
        async with self._mutex:
            return self._sessions.get(target_id)

    async def stop_all(self) -> None:
        """For atexit cleanup. Only daemon-backed sessions have a client to
        stop; re-attached sessions (client is None) are just dropped — we
        never kill an app we didn't start. Their record stays in the store
        so a future MCP start can re-attach."""
        async with self._mutex:
            sessions = list(self._sessions.values())
            self._sessions.clear()
            self._most_recent = None
        for active in sessions:
            if active.client is None:
                continue
            try:
                await active.client.stop()
            except Exception:
                continue


def _reattached_no_daemon(op: str) -> DebugSessionFailure:
    return DebugSessionFailure(
        message=(
            f"{op} needs the flutter --machine daemon, which didn't survive "
            "the MCP restart — this is a re-attached (VM-Service-only) "
            "session. Service extensions / dump_widget_tree / vm_evaluate "
            "still work. Run start_debug_session for a fresh daemon-backed "
            "session."
        ),
        next_action="start_debug_session",
    )


def _mode_from(value: str | None) -> BuildMode:
    try:
        return BuildMode(value) if value else BuildMode.DEBUG
    except ValueError:
        return BuildMode.DEBUG


def _dt_from(value: str | None) -> datetime:
    try:
        return datetime.fromisoformat(value) if value else datetime.now()
    except (ValueError, TypeError):
        return datetime.now()


class _Active:
    """Internal record bundling a DebugSession with its live daemon client.

    `client` is None for a **re-attached** session — one revived from the
    durable store (or `attach()`) after the daemon connection was lost.
    Such a session talks only to the VM Service (via its uri); it can run
    service extensions but not hot reload. The vm_uri/app_id/pid come from
    the client when present, else from the stored values.
    """

    __slots__ = (
        "_app_id",
        "_pid",
        "_vm_service_uri",
        "client",
        "device_serial",
        "flavor",
        "mode",
        "project_path",
        "session_id",
        "started_at",
        "state",
        "target",
    )

    def __init__(
        self,
        session_id: str,
        client: FlutterMachineClient | None,
        project_path: Path,
        device_serial: str,
        mode: BuildMode,
        flavor: str | None,
        target: str | None,
        started_at: datetime,
        state: DebugSessionState,
        vm_service_uri: str | None = None,
        app_id: str | None = None,
        pid: int | None = None,
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
        self._vm_service_uri = vm_service_uri
        self._app_id = app_id
        self._pid = pid

    @property
    def vm_uri(self) -> str | None:
        return self.client.vm_service_uri if self.client is not None else self._vm_service_uri

    @property
    def app_id(self) -> str | None:
        return self.client.app_id if self.client is not None else self._app_id

    @property
    def pid(self) -> int | None:
        return self.client.pid if self.client is not None else self._pid

    def snapshot(self) -> DebugSession:
        return DebugSession(
            id=self.session_id,
            project_path=self.project_path,
            device_serial=self.device_serial,
            mode=self.mode,
            started_at=self.started_at,
            state=self.state,
            app_id=self.app_id,
            vm_service_uri=self.vm_uri,
            flavor=self.flavor,
            target=self.target,
            pid=self.pid,
        )

    def to_record(self) -> dict:
        """Durable metadata for the store — everything needed to re-attach."""
        return {
            "id": self.session_id,
            "device_serial": self.device_serial,
            "project_path": str(self.project_path),
            "vm_service_uri": self.vm_uri,
            "app_id": self.app_id,
            "mode": self.mode.value,
            "flavor": self.flavor,
            "target": self.target,
            "started_at": self.started_at.isoformat(),
        }

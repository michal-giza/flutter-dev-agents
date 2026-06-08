"""Web debug-session support (v0.7.0).

Field report #2: profiling/inspector tools (frame profile, heap snapshot,
widget/render tree, service extensions, debug log) were device-coupled,
so Flutter **web** apps couldn't be driven through a live session.

Fix: `start_debug_session(serial='chrome')` runs `flutter run -d chrome
--machine`, which speaks the SAME daemon protocol as a phone (via DWDS) —
so the whole stack works unchanged. The only repo change is skipping the
adb device-lock for web ids (`chrome` / `web-server`), since there's no
physical device to contend on.

Hermetic: a fake daemon client (no real `flutter run`) lets us assert the
lock is skipped for web, still enforced for real devices, and that the
session carries the VM Service URI that the profiler tools attach to.

NOTE: end-to-end behaviour against a real `flutter run -d chrome` is
verified separately on a live Flutter+Chrome host — these tests pin the
repo contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.data.repositories.flutter_debug_session_repository import (
    FlutterDebugSessionRepository,
)
from mcp_phone_controll.domain.entities import BuildMode
from mcp_phone_controll.domain.failures import DeviceBusyFailure
from mcp_phone_controll.domain.result import Err, Ok, ok


class _FakeMachineClient:
    """Stands in for FlutterMachineClient. Records the start() call and
    exposes the attributes _Active.snapshot() reads."""

    def __init__(self, flutter) -> None:
        self.flutter = flutter
        self.app_id: str | None = None
        self.vm_service_uri: str | None = None
        self.pid: int | None = None
        self.started_with: dict | None = None
        self.stopped = False

    async def start(
        self, project_path, device_serial, mode="debug",
        flavor=None, target=None, startup_timeout_s=120.0,
        await_vm_service=False, vm_service_timeout_s=60.0,
    ) -> None:
        self.started_with = {
            "project_path": project_path,
            "device_serial": device_serial,
            "mode": mode,
            "await_vm_service": await_vm_service,
        }
        # Simulate a successful app.started + app.debugPort (DWDS for web).
        self.app_id = "app-web-1"
        self.vm_service_uri = "ws://127.0.0.1:5566/abcDEF=/ws"
        self.pid = 4242

    async def stop(self) -> None:
        self.stopped = True


class _FakeLocks:
    """lock_for() is the only method start() touches."""

    def __init__(self, lock=None) -> None:
        self._lock = lock

    async def lock_for(self, serial):
        return ok(self._lock)


def _repo(locks, created: list):
    def factory(flutter):
        client = _FakeMachineClient(flutter)
        created.append(client)
        return client

    return FlutterDebugSessionRepository(
        flutter=object(),
        locks=locks,
        session_id="sess-A",
        client_factory=factory,
    )


# ---- web targets skip the lock -----------------------------------------


@pytest.mark.asyncio
async def test_chrome_starts_without_a_lock(tmp_path: Path):
    """The headline: a web session boots with NO device lock held."""
    created: list = []
    repo = _repo(_FakeLocks(lock=None), created)  # no lock anywhere

    res = await repo.start(project_path=tmp_path, device_serial="chrome")

    assert isinstance(res, Ok)
    assert res.value.device_serial == "chrome"
    assert res.value.vm_service_uri == "ws://127.0.0.1:5566/abcDEF=/ws"
    assert res.value.app_id == "app-web-1"
    # flutter run was invoked with -d chrome
    assert created[0].started_with["device_serial"] == "chrome"


@pytest.mark.asyncio
async def test_web_server_target_also_skips_lock(tmp_path: Path):
    created: list = []
    repo = _repo(_FakeLocks(lock=None), created)

    res = await repo.start(project_path=tmp_path, device_serial="web-server")

    assert isinstance(res, Ok)
    assert created[0].started_with["device_serial"] == "web-server"


@pytest.mark.asyncio
async def test_web_session_mode_passed_through(tmp_path: Path):
    created: list = []
    repo = _repo(_FakeLocks(lock=None), created)

    res = await repo.start(
        project_path=tmp_path, device_serial="chrome", mode=BuildMode.PROFILE
    )

    assert isinstance(res, Ok)
    # profile mode is what you want for honest web frame timings
    assert created[0].started_with["mode"] == "profile"


# ---- real devices still require the lock (regression guard) ------------


@pytest.mark.asyncio
async def test_real_device_without_lock_is_rejected(tmp_path: Path):
    created: list = []
    repo = _repo(_FakeLocks(lock=None), created)  # lock not held

    res = await repo.start(project_path=tmp_path, device_serial="R3CY1234XYZ")

    assert isinstance(res, Err)
    assert isinstance(res.failure, DeviceBusyFailure)
    assert created == []  # never spawned a client


@pytest.mark.asyncio
async def test_real_device_with_held_lock_starts(tmp_path: Path):
    from datetime import datetime

    from mcp_phone_controll.domain.entities import DeviceLock

    lock = DeviceLock(
        serial="R3CY1234XYZ", session_id="sess-A", pid=1,
        started_at=datetime(2026, 1, 1),
    )
    created: list = []
    repo = _repo(_FakeLocks(lock=lock), created)

    res = await repo.start(project_path=tmp_path, device_serial="R3CY1234XYZ")

    assert isinstance(res, Ok)
    assert created[0].started_with["device_serial"] == "R3CY1234XYZ"


# ---- web service extensions via direct VM Service (v0.8.0) --------------

_VM_CLIENT_PATH = (
    "mcp_phone_controll.infrastructure.vm_service_client.VmServiceClient"
)
_SLEEP_PATH = (
    "mcp_phone_controll.data.repositories"
    ".flutter_debug_session_repository.asyncio.sleep"
)


def _make_fake_vm(script, isolate="iso-1", raise_import=False):
    """Returns a (class, created_instances) pair for monkeypatching
    VmServiceClient. `script` is the list of call_service_extension
    responses, consumed in order (last repeats)."""
    created: list = []

    class _FakeVm:
        def __init__(self, uri):
            self.uri = uri
            self.closed = False
            self._n = 0
            created.append(self)

        async def connect(self):
            if raise_import:
                raise ImportError("websockets not installed; run `… .[debug]`")

        async def close(self):
            self.closed = True

        async def first_isolate_id(self):
            return isolate

        async def call_service_extension(self, isolate_id, method, args=None):
            resp = script[min(self._n, len(script) - 1)]
            self._n += 1
            return resp

    return _FakeVm, created


async def _noop_sleep(*_a, **_k):
    return None


async def _started_web_repo(tmp_path):
    created: list = []
    repo = _repo(_FakeLocks(lock=None), created)
    await repo.start(project_path=tmp_path, device_serial="chrome")
    return repo


@pytest.mark.asyncio
async def test_web_service_extension_retries_until_registered(tmp_path, monkeypatch):
    """The headline v0.8.0 win: ext.flutter.* register a few seconds after
    the web app loads. The web path retries on -32601 (method-not-found)
    and succeeds once the extension appears."""
    repo = await _started_web_repo(tmp_path)
    cls, created = _make_fake_vm(script=[
        {"error": {"code": -32601, "message": 'Unknown method "ext.flutter.debugDumpApp"'}},
        {"error": {"code": -32601, "message": "Unknown method"}},
        {"result": {"data": "<widget tree>"}},
    ])
    monkeypatch.setattr(_VM_CLIENT_PATH, cls)
    monkeypatch.setattr(_SLEEP_PATH, _noop_sleep)

    res = await repo.call_service_extension(None, "ext.flutter.debugDumpApp")

    assert isinstance(res, Ok)
    assert res.value.result == {"data": "<widget tree>"}
    assert created[0].closed is True  # connection cleaned up


@pytest.mark.asyncio
async def test_web_service_extension_success_first_try(tmp_path, monkeypatch):
    repo = await _started_web_repo(tmp_path)
    cls, _ = _make_fake_vm(script=[{"result": {"enabled": True}}])
    monkeypatch.setattr(_VM_CLIENT_PATH, cls)
    monkeypatch.setattr(_SLEEP_PATH, _noop_sleep)

    res = await repo.call_service_extension(
        None, "ext.flutter.inspector.show", {"enabled": True}
    )
    assert isinstance(res, Ok)
    assert res.value.result == {"enabled": True}


@pytest.mark.asyncio
async def test_web_service_extension_import_error(tmp_path, monkeypatch):
    repo = await _started_web_repo(tmp_path)
    cls, _ = _make_fake_vm(script=[{"result": {}}], raise_import=True)
    monkeypatch.setattr(_VM_CLIENT_PATH, cls)

    res = await repo.call_service_extension(None, "ext.flutter.debugDumpApp")
    assert isinstance(res, Err)
    assert res.failure.next_action == "install_debug_extras"


@pytest.mark.asyncio
async def test_web_service_extension_no_isolate(tmp_path, monkeypatch):
    repo = await _started_web_repo(tmp_path)
    cls, _ = _make_fake_vm(script=[{"result": {}}], isolate=None)
    monkeypatch.setattr(_VM_CLIENT_PATH, cls)

    res = await repo.call_service_extension(None, "ext.flutter.debugDumpApp")
    assert isinstance(res, Err)
    assert "no isolate" in res.failure.message


@pytest.mark.asyncio
async def test_web_service_extension_real_error_surfaces(tmp_path, monkeypatch):
    """A non -32601 error (e.g. the extension threw) surfaces immediately,
    not retried into a circuit break."""
    repo = await _started_web_repo(tmp_path)
    cls, _ = _make_fake_vm(script=[
        {"error": {"code": 100, "message": "boom inside extension"}},
    ])
    monkeypatch.setattr(_VM_CLIENT_PATH, cls)
    monkeypatch.setattr(_SLEEP_PATH, _noop_sleep)

    res = await repo.call_service_extension(None, "ext.flutter.debugDumpApp")
    assert isinstance(res, Err)
    assert "boom inside extension" in res.failure.message

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

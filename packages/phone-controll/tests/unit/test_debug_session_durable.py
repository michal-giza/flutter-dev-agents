"""Durable debug sessions — attach + auto-reattach across MCP restart (v0.16.0).

Field-reported "gap #6": the registry was in-memory, so restarting the
tool server orphaned still-alive sessions; attach() was a stub. These
tests pin the fix: metadata persists, attach() works via the VM Service,
and list_sessions() revives reachable sessions / prunes dead ones.
"""

from __future__ import annotations

import pytest

from mcp_phone_controll.data.repositories.flutter_debug_session_repository import (
    FlutterDebugSessionRepository,
)
from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.infrastructure.debug_session_store import DebugSessionStore

_VM_CLIENT_PATH = "mcp_phone_controll.infrastructure.vm_service_client.VmServiceClient"
_SLEEP_PATH = (
    "mcp_phone_controll.data.repositories"
    ".flutter_debug_session_repository.asyncio.sleep"
)
_URI = "ws://127.0.0.1:5566/tok=/ws"


def _reachable_vm(script=None, isolate="iso-1"):
    created: list = []

    class _Vm:
        def __init__(self, uri):
            self.uri = uri
            created.append(self)

        async def connect(self):  # reachable
            return None

        async def close(self):
            return None

        async def first_isolate_id(self):
            return isolate

        async def call_service_extension(self, isolate_id, method, args=None):
            return (script or [{"result": {"ok": True}}])[0]

    return _Vm, created


def _unreachable_vm():
    class _Vm:
        def __init__(self, uri):
            self.uri = uri

        async def connect(self):
            raise ConnectionRefusedError("connection refused")

        async def close(self):
            return None

    return _Vm


class _Locks:
    async def lock_for(self, serial):
        from mcp_phone_controll.domain.result import ok

        return ok(None)


def _repo(store):
    return FlutterDebugSessionRepository(
        flutter=object(), locks=_Locks(), session_id="sess-A", store=store
    )


# ---- attach() (was a stub) ---------------------------------------------


@pytest.mark.asyncio
async def test_attach_reachable_registers_session(tmp_path, monkeypatch):
    cls, _ = _reachable_vm()
    monkeypatch.setattr(_VM_CLIENT_PATH, cls)
    store = DebugSessionStore(tmp_path / "ds.json")
    repo = _repo(store)

    res = await repo.attach(_URI, tmp_path)
    assert isinstance(res, Ok), res
    assert res.value.vm_service_uri == _URI
    assert res.value.state.value == "running"
    # persisted so it survives a restart
    assert store.load()[0]["vm_service_uri"] == _URI
    # visible via list_sessions
    listed = await repo.list_sessions()
    assert any(s.vm_service_uri == _URI for s in listed.value)


@pytest.mark.asyncio
async def test_attach_unreachable_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(_VM_CLIENT_PATH, _unreachable_vm())
    repo = _repo(DebugSessionStore(tmp_path / "ds.json"))
    res = await repo.attach(_URI, tmp_path)
    assert isinstance(res, Err)
    assert res.failure.next_action == "check_debug_session"


# ---- auto-reattach across a "restart" ----------------------------------


@pytest.mark.asyncio
async def test_list_reattaches_persisted_session(tmp_path, monkeypatch):
    """Simulate a restart: a record is already on disk; a fresh repo
    (new process) revives it on list_sessions because the VM is reachable."""
    path = tmp_path / "ds.json"
    DebugSessionStore(path).upsert({
        "id": "sid1", "device_serial": "chrome",
        "project_path": str(tmp_path), "vm_service_uri": _URI,
        "mode": "debug", "started_at": "2026-06-21T10:00:00",
    })
    cls, _ = _reachable_vm()
    monkeypatch.setattr(_VM_CLIENT_PATH, cls)

    repo = _repo(DebugSessionStore(path))          # "new process"
    listed = await repo.list_sessions()
    assert isinstance(listed, Ok)
    assert [s.id for s in listed.value] == ["sid1"]
    assert listed.value[0].vm_service_uri == _URI


@pytest.mark.asyncio
async def test_list_prunes_dead_persisted_session(tmp_path, monkeypatch):
    path = tmp_path / "ds.json"
    store = DebugSessionStore(path)
    store.upsert({"id": "dead", "vm_service_uri": _URI, "project_path": str(tmp_path)})
    monkeypatch.setattr(_VM_CLIENT_PATH, _unreachable_vm())

    repo = _repo(DebugSessionStore(path))
    listed = await repo.list_sessions()
    assert listed.value == []                       # pruned
    assert store.load() == []                        # and removed from disk


# ---- re-attached session can query VM, but not hot reload --------------


@pytest.mark.asyncio
async def test_reattached_session_serves_service_extensions(tmp_path, monkeypatch):
    cls, _created = _reachable_vm(script=[{"result": {"data": "<tree>"}}])
    monkeypatch.setattr(_VM_CLIENT_PATH, cls)
    monkeypatch.setattr(_SLEEP_PATH, _noop)
    repo = _repo(DebugSessionStore(tmp_path / "ds.json"))
    await repo.attach(_URI, tmp_path)

    res = await repo.call_service_extension(None, "ext.flutter.debugDumpApp")
    assert isinstance(res, Ok), res
    assert res.value.result == {"data": "<tree>"}


@pytest.mark.asyncio
async def test_reattached_session_cannot_hot_reload(tmp_path, monkeypatch):
    cls, _ = _reachable_vm()
    monkeypatch.setattr(_VM_CLIENT_PATH, cls)
    repo = _repo(DebugSessionStore(tmp_path / "ds.json"))
    await repo.attach(_URI, tmp_path)

    res = await repo.restart(None)
    assert isinstance(res, Err)
    assert res.failure.next_action == "start_debug_session"
    assert "daemon" in res.failure.message.lower()


@pytest.mark.asyncio
async def test_stop_reattached_detaches_without_killing(tmp_path, monkeypatch):
    cls, _ = _reachable_vm()
    monkeypatch.setattr(_VM_CLIENT_PATH, cls)
    store = DebugSessionStore(tmp_path / "ds.json")
    repo = _repo(store)
    attached = await repo.attach(_URI, tmp_path)
    sid = attached.value.id

    res = await repo.stop(sid)
    assert isinstance(res, Ok)
    assert store.load() == []                        # removed from durable store
    assert (await repo.list_sessions()).value == []  # gone from registry


async def _noop(*_a, **_k):
    return None

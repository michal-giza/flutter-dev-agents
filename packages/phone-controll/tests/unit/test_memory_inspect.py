"""Tests for the v0.3.0 memory introspection use cases.

Hermetic — uses a stub VmServiceClient via module-level monkeypatch
so no real Flutter app + flutter run --machine is needed in CI.

Coverage goals:
- happy-path: each use case returns a well-shaped Ok value for a
  realistic VM service response shape;
- bad-input: missing session, no isolate, target class not present
  → typed failure with the right next_action;
- leak-detection: AllocationProfile with reset_accumulator surfaces
  accumulated-since-reset counts (the leak-detection workflow);
- DetectUndisposedControllers: returns counts in canonical class
  order even when some classes have zero instances (shape stability
  for the agent).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from mcp_phone_controll.domain.entities import DebugSession, DebugSessionState
from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.memory_inspect import (
    AllocationProfile,
    AllocationProfileParams,
    DetectUndisposedControllers,
    DetectUndisposedControllersParams,
    FindRetainingPath,
    FindRetainingPathParams,
    MemorySummary,
    MemorySummaryParams,
)

# ---- test fixtures: fakes for the VM service + repo --------------------


@dataclass
class _StubVmClient:
    """Replays scripted responses indexed by JSON-RPC method name.

    The real VmServiceClient connects via WebSocket; for tests we
    swap the whole class out at the import boundary so no socket is
    opened.
    """

    responses: dict[str, Any]

    async def connect(self, timeout_s: float = 10.0) -> None:
        pass

    async def close(self) -> None:
        pass

    async def get_vm(self) -> dict:
        return self.responses.get(
            "getVM",
            {"result": {"isolates": [{"id": "isolates/1", "name": "main", "runnable": True}]}},
        )

    async def call(self, method: str, params: dict) -> dict:
        return self.responses.get(method, {"result": {}})


def _patch_vm(monkeypatch, stub: _StubVmClient) -> None:
    """Replace VmServiceClient with a factory that returns our stub."""
    import mcp_phone_controll.domain.usecases.memory_inspect as mod

    async def _fake_with_vm(uri, op, **kwargs):
        return await op(stub, **kwargs)

    monkeypatch.setattr(mod, "_with_vm", _fake_with_vm)


class _FakeDebugRepo:
    """Returns a fake debug session with a VM service URI set."""

    def __init__(self, vm_service_uri: str | None = "ws://127.0.0.1:55555/ws"):
        self._uri = vm_service_uri

    async def list_sessions(self):
        from mcp_phone_controll.domain.result import ok
        return ok([
            DebugSession(
                id="dbg-1",
                project_path="/p",
                device_serial="X",
                mode="debug",
                started_at=0.0,
                vm_service_uri=self._uri,
                app_id="app-1",
                state=DebugSessionState.RUNNING,
            )
        ])


# ---- memory_summary ----------------------------------------------------


@pytest.mark.asyncio
async def test_memory_summary_happy_path(monkeypatch):
    """One isolate, heap 12MB used / 16MB capacity / 4MB external."""
    stub = _StubVmClient(
        responses={
            "getVM": {"result": {"isolates": [
                {"id": "isolates/1", "name": "main", "runnable": True}
            ]}},
            "getIsolateMemoryUsage": {"result": {
                "heapUsage": 12_582_912,
                "heapCapacity": 16_777_216,
                "externalUsage": 4_194_304,
            }},
        }
    )
    _patch_vm(monkeypatch, stub)

    res = await MemorySummary(_FakeDebugRepo())(MemorySummaryParams())
    assert isinstance(res, Ok)
    v = res.value
    assert v.total_heap_used_bytes == 12_582_912
    assert v.total_external_bytes == 4_194_304
    assert len(v.isolates) == 1
    assert v.isolates[0].isolate_name == "main"


@pytest.mark.asyncio
async def test_memory_summary_no_active_session_returns_typed_error():
    """No active debug session → DebugSessionFailure with
    next_action='start_debug_session'."""
    res = await MemorySummary(_FakeDebugRepo(vm_service_uri=None))(
        MemorySummaryParams()
    )
    assert isinstance(res, Err)
    assert res.failure.next_action == "start_debug_session"


# ---- allocation_profile ------------------------------------------------


@pytest.mark.asyncio
async def test_allocation_profile_returns_top_n_by_count_and_bytes(monkeypatch):
    """Returns top-N classes sorted by count and bytes separately."""
    stub = _StubVmClient(responses={
        "getAllocationProfile": {"result": {
            "members": [
                {"classRef": {"name": "MyBloc"}, "instancesCurrent": 6, "bytesCurrent": 600},
                {"classRef": {"name": "_String"}, "instancesCurrent": 1000, "bytesCurrent": 50_000},
                {"classRef": {"name": "Map"}, "instancesCurrent": 20, "bytesCurrent": 2000},
                # noise — count + bytes both zero
                {"classRef": {"name": "FilteredOut"}, "instancesCurrent": 0, "bytesCurrent": 0},
            ]
        }},
    })
    _patch_vm(monkeypatch, stub)

    res = await AllocationProfile(_FakeDebugRepo())(
        AllocationProfileParams(top_n=2)
    )
    assert isinstance(res, Ok)
    v = res.value
    assert len(v.top_by_count) == 2
    assert v.top_by_count[0].class_name == "_String"
    assert v.top_by_count[0].instance_count == 1000
    assert v.top_by_bytes[0].class_name == "_String"
    # zero-instance class filtered out
    assert all(r.class_name != "FilteredOut" for r in v.top_by_count)


@pytest.mark.asyncio
async def test_allocation_profile_reset_mode_uses_accumulator_fields(monkeypatch):
    """With reset_accumulator=True, the use case returns
    accumulated-since-reset counts — the leak-detection metric."""
    stub = _StubVmClient(responses={
        "getAllocationProfile": {"result": {
            "members": [
                {
                    "classRef": {"name": "Bloc"},
                    "instancesCurrent": 1,        # current snapshot
                    "bytesCurrent": 100,
                    "accumulatedInstances": 5,    # ← deltas since reset
                    "accumulatedSize": 500,
                },
            ]
        }},
    })
    _patch_vm(monkeypatch, stub)

    res = await AllocationProfile(_FakeDebugRepo())(
        AllocationProfileParams(reset_accumulator=True, top_n=5)
    )
    assert isinstance(res, Ok)
    v = res.value
    assert v.top_by_count[0].instance_count == 5
    assert v.top_by_count[0].bytes_held == 500


# ---- detect_undisposed_controllers -------------------------------------


@pytest.mark.asyncio
async def test_detect_undisposed_counts_canonical_classes(monkeypatch):
    """Returns counts in canonical-class order, with 0 for absent."""
    stub = _StubVmClient(responses={
        "getAllocationProfile": {"result": {
            "members": [
                {"classRef": {"name": "TextEditingController"}, "instancesCurrent": 4},
                {"classRef": {"name": "ScrollController"}, "instancesCurrent": 2},
                {"classRef": {"name": "OtherClass"}, "instancesCurrent": 100},
                # AnimationController not present — should appear as 0
            ]
        }},
    })
    _patch_vm(monkeypatch, stub)

    res = await DetectUndisposedControllers(_FakeDebugRepo())(
        DetectUndisposedControllersParams()
    )
    assert isinstance(res, Ok)
    v = res.value
    by_name = {c.class_name: c.instance_count for c in v.counts}
    assert by_name["TextEditingController"] == 4
    assert by_name["ScrollController"] == 2
    # absent class shows as 0 — shape stability for the agent
    assert by_name["AnimationController"] == 0
    assert v.total_suspect_instances == 6
    assert "instances" in v.advice.lower()


@pytest.mark.asyncio
async def test_detect_undisposed_zero_total_produces_clean_advice(monkeypatch):
    """All-zero counts → the 'looks clean ✓' branch of advice."""
    stub = _StubVmClient(responses={
        "getAllocationProfile": {"result": {"members": []}},
    })
    _patch_vm(monkeypatch, stub)

    res = await DetectUndisposedControllers(_FakeDebugRepo())(
        DetectUndisposedControllersParams()
    )
    assert isinstance(res, Ok)
    assert res.value.total_suspect_instances == 0
    assert "✓" in res.value.advice or "clear" in res.value.advice.lower() or "no" in res.value.advice.lower()


@pytest.mark.asyncio
async def test_detect_undisposed_high_count_produces_alarm_advice(monkeypatch):
    """Large total → 'strong signal of accumulated leaks' branch."""
    stub = _StubVmClient(responses={
        "getAllocationProfile": {"result": {
            "members": [
                {"classRef": {"name": "TextEditingController"}, "instancesCurrent": 50},
            ]
        }},
    })
    _patch_vm(monkeypatch, stub)

    res = await DetectUndisposedControllers(_FakeDebugRepo())(
        DetectUndisposedControllersParams()
    )
    assert isinstance(res, Ok)
    assert res.value.total_suspect_instances == 50
    # advice mentions investigation
    assert "retaining" in res.value.advice.lower() or "leaks" in res.value.advice.lower()


# ---- find_retaining_path -----------------------------------------------


@pytest.mark.asyncio
async def test_find_retaining_path_no_live_instances_returns_typed_failure(monkeypatch):
    """If the class isn't in the heap, surface a structured next_action
    rather than a generic exception."""
    stub = _StubVmClient(responses={
        "getAllocationProfile": {"result": {
            "members": [
                {"classRef": {"name": "OtherClass", "id": "c/1"}, "instancesCurrent": 5},
            ]
        }},
    })
    _patch_vm(monkeypatch, stub)

    res = await FindRetainingPath(_FakeDebugRepo())(
        FindRetainingPathParams(class_name="MissingClass")
    )
    assert isinstance(res, Err)
    assert res.failure.next_action == "check_class_name_or_take_heap_snapshot"


@pytest.mark.asyncio
async def test_find_retaining_path_happy(monkeypatch):
    """Resolves classId → instanceId → calls getRetainingPath →
    surfaces the field chain."""
    stub = _StubVmClient(responses={
        "getAllocationProfile": {"result": {
            "members": [
                {"classRef": {"name": "MyBloc", "id": "classes/42"}, "instancesCurrent": 1},
            ]
        }},
        "getInstances": {"result": {
            "instances": [{"id": "objects/123"}],
        }},
        "getRetainingPath": {"result": {
            "elements": [
                {"value": {"class": {"name": "_HomeState"}}, "parentField": "_bloc"},
                {"value": {"class": {"name": "GlobalKey"}}, "parentField": "_currentState"},
                {"value": {"class": {"name": "MyBloc"}}},
            ],
            "gcRootType": "library",
        }},
    })
    _patch_vm(monkeypatch, stub)

    res = await FindRetainingPath(_FakeDebugRepo())(
        FindRetainingPathParams(class_name="MyBloc")
    )
    assert isinstance(res, Ok)
    v = res.value
    assert v.target_class == "MyBloc"
    assert v.gc_root_kind == "library"
    assert len(v.path) == 3
    assert v.path[0].class_name == "_HomeState"
    assert v.path[0].field_or_index == "_bloc"
    # Final element is the target itself
    assert v.path[-1].class_name == "MyBloc"

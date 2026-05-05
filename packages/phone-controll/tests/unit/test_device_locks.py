"""Cross-session device lock semantics.

Simulates the user's factory scenario: 3 Claude sessions, each owning a
different device — emulator, Android, iPhone simulator — and prevents two
sessions from grabbing the same device.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from mcp_phone_controll.data.repositories.filesystem_device_lock_repository import (
    FilesystemDeviceLockRepository,
)
from mcp_phone_controll.data.repositories.in_memory_device_lock_repository import (
    InMemoryDeviceLockRepository,
)
from mcp_phone_controll.domain.failures import (
    DeviceBusyFailure,
    LockNotHeldFailure,
)
from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.base import NoParams
from mcp_phone_controll.domain.usecases.devices import (
    ForceReleaseLock,
    ForceReleaseLockParams,
    ListLocks,
    ReleaseDevice,
    ReleaseDeviceParams,
    SelectDevice,
    SelectDeviceParams,
)
from tests.fakes.fake_repositories import (
    FakeDeviceRepository,
    FakeSessionStateRepository,
)


# ----- filesystem repo: low-level lock semantics ---------------------------


@pytest.mark.asyncio
async def test_filesystem_acquire_succeeds(tmp_path: Path):
    repo = FilesystemDeviceLockRepository(root=tmp_path)
    res = await repo.acquire("EMU01", "session-A")
    assert isinstance(res, Ok)
    assert res.value.serial == "EMU01"
    assert res.value.session_id == "session-A"
    # File on disk
    files = list(tmp_path.glob("*.lock"))
    assert len(files) == 1


@pytest.mark.asyncio
async def test_filesystem_second_session_gets_busy(tmp_path: Path):
    repo = FilesystemDeviceLockRepository(root=tmp_path)
    await repo.acquire("EMU01", "session-A")
    res = await repo.acquire("EMU01", "session-B")
    assert isinstance(res, Err)
    assert isinstance(res.failure, DeviceBusyFailure)
    assert res.failure.next_action == "wait_or_force"
    assert res.failure.details["holder_session_id"] == "session-A"


@pytest.mark.asyncio
async def test_filesystem_same_session_is_idempotent(tmp_path: Path):
    repo = FilesystemDeviceLockRepository(root=tmp_path)
    a = await repo.acquire("EMU01", "session-A")
    b = await repo.acquire("EMU01", "session-A")
    assert isinstance(a, Ok) and isinstance(b, Ok)
    assert a.value.session_id == b.value.session_id


@pytest.mark.asyncio
async def test_filesystem_force_overrides(tmp_path: Path):
    repo = FilesystemDeviceLockRepository(root=tmp_path)
    await repo.acquire("EMU01", "session-A")
    res = await repo.acquire("EMU01", "session-B", force=True)
    assert isinstance(res, Ok)
    assert res.value.session_id == "session-B"


@pytest.mark.asyncio
async def test_filesystem_release_by_holder(tmp_path: Path):
    repo = FilesystemDeviceLockRepository(root=tmp_path)
    await repo.acquire("EMU01", "session-A")
    res = await repo.release("EMU01", "session-A")
    assert isinstance(res, Ok)
    assert list(tmp_path.glob("*.lock")) == []


@pytest.mark.asyncio
async def test_filesystem_release_by_non_holder_fails(tmp_path: Path):
    repo = FilesystemDeviceLockRepository(root=tmp_path)
    await repo.acquire("EMU01", "session-A")
    res = await repo.release("EMU01", "session-B")
    assert isinstance(res, Err)
    assert isinstance(res.failure, LockNotHeldFailure)
    assert res.failure.next_action == "force_release_lock"


@pytest.mark.asyncio
async def test_filesystem_force_release_breaks_lock(tmp_path: Path):
    repo = FilesystemDeviceLockRepository(root=tmp_path)
    await repo.acquire("EMU01", "session-A")
    await repo.force_release("EMU01")
    res = await repo.acquire("EMU01", "session-B")
    assert isinstance(res, Ok)


@pytest.mark.asyncio
async def test_filesystem_stale_pid_lock_is_reclaimed(tmp_path: Path):
    """Lock from a dead process gets cleaned up automatically."""
    repo = FilesystemDeviceLockRepository(root=tmp_path)
    # Hand-craft a lock owned by a PID that almost certainly doesn't exist.
    fake_lock = {
        "serial": "EMU01",
        "session_id": "ghost-session",
        "pid": 999999,                     # very unlikely to be alive
        "started_at": "2020-01-01T00:00:00",
        "note": None,
    }
    (tmp_path / "EMU01.lock").write_text(json.dumps(fake_lock))
    res = await repo.acquire("EMU01", "session-NEW")
    assert isinstance(res, Ok)
    assert res.value.session_id == "session-NEW"


@pytest.mark.asyncio
async def test_filesystem_list_locks_omits_stale(tmp_path: Path):
    repo = FilesystemDeviceLockRepository(root=tmp_path)
    await repo.acquire("EMU01", "session-A")
    fake = {
        "serial": "DEAD",
        "session_id": "ghost",
        "pid": 999999,
        "started_at": "2020-01-01T00:00:00",
        "note": None,
    }
    (tmp_path / "DEAD.lock").write_text(json.dumps(fake))
    res = await repo.list_locks()
    assert isinstance(res, Ok)
    serials = {l.serial for l in res.value}
    assert "EMU01" in serials
    assert "DEAD" not in serials  # stale PID auto-cleaned


# ----- end-to-end: 3-session factory simulation --------------------------


@pytest.mark.asyncio
async def test_three_sessions_each_own_a_different_device(tmp_path: Path):
    """Galaxy + Android + iPhone simulator — three Claude sessions, no conflicts."""
    repo = FilesystemDeviceLockRepository(root=tmp_path)
    galaxy = await repo.acquire("R3CYA05CHXB", "session-android-physical")
    emu = await repo.acquire("emulator-5554", "session-android-emu")
    sim = await repo.acquire("UDID-IPHONE-SIM", "session-ios-sim")
    assert all(isinstance(r, Ok) for r in (galaxy, emu, sim))
    listed = await repo.list_locks()
    assert isinstance(listed, Ok)
    assert {l.serial for l in listed.value} == {
        "R3CYA05CHXB",
        "emulator-5554",
        "UDID-IPHONE-SIM",
    }


@pytest.mark.asyncio
async def test_two_sessions_fight_over_one_device(tmp_path: Path):
    repo = FilesystemDeviceLockRepository(root=tmp_path)
    a = await repo.acquire("R3CYA05CHXB", "session-A")
    b = await repo.acquire("R3CYA05CHXB", "session-B")
    assert isinstance(a, Ok)
    assert isinstance(b, Err)
    assert isinstance(b.failure, DeviceBusyFailure)
    assert b.failure.details["holder_session_id"] == "session-A"


# ----- SelectDevice / ReleaseDevice integration ---------------------------


@pytest.mark.asyncio
async def test_select_device_acquires_lock_then_release_clears_state():
    devices = FakeDeviceRepository()
    state = FakeSessionStateRepository()
    locks = InMemoryDeviceLockRepository()

    select = SelectDevice(devices, state, locks, "session-1")
    sel_res = await select(SelectDeviceParams(serial="EMU01"))
    assert isinstance(sel_res, Ok)

    holder = await locks.lock_for("EMU01")
    assert isinstance(holder, Ok)
    assert holder.value is not None
    assert holder.value.session_id == "session-1"

    release = ReleaseDevice(state, locks, "session-1")
    rel_res = await release(ReleaseDeviceParams())
    assert isinstance(rel_res, Ok)

    holder = await locks.lock_for("EMU01")
    assert isinstance(holder, Ok) and holder.value is None
    sel = await state.get_selected_serial()
    assert isinstance(sel, Ok) and sel.value is None


@pytest.mark.asyncio
async def test_select_device_rejects_when_other_session_holds_lock():
    devices = FakeDeviceRepository()
    state = FakeSessionStateRepository()
    locks = InMemoryDeviceLockRepository()
    await locks.acquire("EMU01", "session-other")

    select = SelectDevice(devices, state, locks, "session-mine")
    res = await select(SelectDeviceParams(serial="EMU01"))
    assert isinstance(res, Err)
    assert isinstance(res.failure, DeviceBusyFailure)


@pytest.mark.asyncio
async def test_select_device_force_overrides_other_session():
    devices = FakeDeviceRepository()
    state = FakeSessionStateRepository()
    locks = InMemoryDeviceLockRepository()
    await locks.acquire("EMU01", "session-other")

    select = SelectDevice(devices, state, locks, "session-mine")
    res = await select(SelectDeviceParams(serial="EMU01", force=True))
    assert isinstance(res, Ok)
    holder = await locks.lock_for("EMU01")
    assert isinstance(holder, Ok)
    assert holder.value.session_id == "session-mine"


@pytest.mark.asyncio
async def test_release_by_non_holder_fails():
    state = FakeSessionStateRepository(serial="EMU01")
    locks = InMemoryDeviceLockRepository()
    await locks.acquire("EMU01", "session-other")

    release = ReleaseDevice(state, locks, "session-mine")
    res = await release(ReleaseDeviceParams(serial="EMU01"))
    assert isinstance(res, Err)
    assert isinstance(res.failure, LockNotHeldFailure)


@pytest.mark.asyncio
async def test_force_release_clears_any_lock():
    locks = InMemoryDeviceLockRepository()
    await locks.acquire("EMU01", "session-stuck")
    force = ForceReleaseLock(locks)
    res = await force(ForceReleaseLockParams(serial="EMU01"))
    assert isinstance(res, Ok)
    holder = await locks.lock_for("EMU01")
    assert isinstance(holder, Ok) and holder.value is None


@pytest.mark.asyncio
async def test_list_locks_returns_all_sessions():
    locks = InMemoryDeviceLockRepository()
    await locks.acquire("A", "session-1")
    await locks.acquire("B", "session-2")
    list_uc = ListLocks(locks)
    res = await list_uc(NoParams())
    assert isinstance(res, Ok)
    holders = {l.serial: l.session_id for l in res.value}
    assert holders == {"A": "session-1", "B": "session-2"}


# ----- safe-name + special characters in serials --------------------------


@pytest.mark.asyncio
async def test_filesystem_handles_serials_with_special_chars(tmp_path: Path):
    repo = FilesystemDeviceLockRepository(root=tmp_path)
    weird = "00008120-001A42542E30201E"
    res = await repo.acquire(weird, "session-A")
    assert isinstance(res, Ok)
    listed = await repo.list_locks()
    assert isinstance(listed, Ok)
    assert weird in {l.serial for l in listed.value}

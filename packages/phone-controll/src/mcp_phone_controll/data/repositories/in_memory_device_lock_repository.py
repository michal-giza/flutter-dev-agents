"""DeviceLockRepository — in-memory.

Use this in tests and in HTTP shared-server mode (single process serving N
Claude clients), where filesystem coordination is unnecessary overhead.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime

from ...domain.entities import DeviceLock
from ...domain.failures import DeviceBusyFailure, LockNotHeldFailure
from ...domain.repositories import DeviceLockRepository
from ...domain.result import Result, err, ok


class InMemoryDeviceLockRepository(DeviceLockRepository):
    def __init__(self) -> None:
        self._locks: dict[str, DeviceLock] = {}
        self._mutex = asyncio.Lock()

    async def acquire(
        self,
        serial: str,
        session_id: str,
        force: bool = False,
        note: str | None = None,
    ) -> Result[DeviceLock]:
        async with self._mutex:
            existing = self._locks.get(serial)
            if existing is not None and existing.session_id == session_id:
                return ok(existing)
            if existing is not None and not force:
                return err(
                    DeviceBusyFailure(
                        message=(
                            f"device {serial} is held by session "
                            f"{existing.session_id} (pid {existing.pid})"
                        ),
                        details={
                            "serial": serial,
                            "holder_session_id": existing.session_id,
                            "holder_pid": existing.pid,
                            "started_at": existing.started_at.isoformat(),
                        },
                        next_action="wait_or_force",
                    )
                )
            new_lock = DeviceLock(
                serial=serial,
                session_id=session_id,
                pid=os.getpid(),
                started_at=datetime.now(),
                note=note,
            )
            self._locks[serial] = new_lock
            return ok(new_lock)

    async def release(self, serial: str, session_id: str) -> Result[None]:
        async with self._mutex:
            existing = self._locks.get(serial)
            if existing is None:
                return ok(None)
            if existing.session_id != session_id:
                return err(
                    LockNotHeldFailure(
                        message=(
                            f"cannot release {serial}: held by {existing.session_id}, "
                            f"not {session_id}"
                        ),
                        next_action="force_release_lock",
                    )
                )
            self._locks.pop(serial, None)
            return ok(None)

    async def force_release(self, serial: str) -> Result[None]:
        async with self._mutex:
            self._locks.pop(serial, None)
            return ok(None)

    async def list_locks(self) -> Result[list[DeviceLock]]:
        async with self._mutex:
            return ok(list(self._locks.values()))

    async def lock_for(self, serial: str) -> Result[DeviceLock | None]:
        async with self._mutex:
            return ok(self._locks.get(serial))

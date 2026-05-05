"""DeviceLockRepository — filesystem-coordinated cross-process locks.

One lock file per serial under <root>/. Acquired with O_EXCL so two processes
racing to create the same file cannot both succeed. Stale locks (PID gone) are
auto-reclaimed. Force-acquire and force-release are explicit, never silent.

This is the right backend when each Claude session spawns its own MCP process
(stdio mode). For the HTTP shared-server mode, use InMemoryDeviceLockRepository.
"""

from __future__ import annotations

import asyncio
import errno
import json
import os
import re
from datetime import datetime
from pathlib import Path

from ...domain.entities import DeviceLock
from ...domain.failures import (
    DeviceBusyFailure,
    FilesystemFailure,
    LockNotHeldFailure,
)
from ...domain.repositories import DeviceLockRepository
from ...domain.result import Result, err, ok


# Filesystem-friendly serial: replace anything that isn't [A-Za-z0-9_.-] with _
_SAFE = re.compile(r"[^A-Za-z0-9_.\-]")


def _safe_name(serial: str) -> str:
    return _SAFE.sub("_", serial)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but isn't ours — still alive.
        return True
    except OSError as e:
        if e.errno == errno.ESRCH:
            return False
        return True
    return True


class FilesystemDeviceLockRepository(DeviceLockRepository):
    def __init__(self, root: Path | None = None) -> None:
        self._root = root or Path.home() / ".mcp_phone_controll" / "locks"
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    def _path_for(self, serial: str) -> Path:
        return self._root / f"{_safe_name(serial)}.lock"

    # ----- public API ----------------------------------------------------

    async def acquire(
        self,
        serial: str,
        session_id: str,
        force: bool = False,
        note: str | None = None,
    ) -> Result[DeviceLock]:
        async with self._lock:
            path = self._path_for(serial)
            existing = self._read(path)
            if existing is not None:
                # Same session already holds it → idempotent success.
                if existing.session_id == session_id:
                    return ok(existing)
                # Held by a dead process → stale, reclaim.
                if not _pid_alive(existing.pid):
                    self._delete_silent(path)
                elif not force:
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
                                "note": existing.note,
                            },
                            next_action="wait_or_force",
                        )
                    )
                else:
                    self._delete_silent(path)
            new_lock = DeviceLock(
                serial=serial,
                session_id=session_id,
                pid=os.getpid(),
                started_at=datetime.now(),
                note=note,
            )
            try:
                self._write(path, new_lock)
            except OSError as e:
                return err(
                    FilesystemFailure(
                        message=f"failed to write lock file {path}: {e}",
                        next_action="check_lock_dir_permissions",
                    )
                )
            return ok(new_lock)

    async def release(self, serial: str, session_id: str) -> Result[None]:
        async with self._lock:
            path = self._path_for(serial)
            existing = self._read(path)
            if existing is None:
                return ok(None)
            if existing.session_id != session_id:
                return err(
                    LockNotHeldFailure(
                        message=(
                            f"cannot release {serial}: lock is held by "
                            f"{existing.session_id}, not {session_id}"
                        ),
                        details={
                            "serial": serial,
                            "holder_session_id": existing.session_id,
                            "holder_pid": existing.pid,
                        },
                        next_action="force_release_lock",
                    )
                )
            self._delete_silent(path)
            return ok(None)

    async def force_release(self, serial: str) -> Result[None]:
        async with self._lock:
            self._delete_silent(self._path_for(serial))
            return ok(None)

    async def list_locks(self) -> Result[list[DeviceLock]]:
        async with self._lock:
            locks: list[DeviceLock] = []
            for child in sorted(self._root.glob("*.lock")):
                lock = self._read(child)
                if lock is None:
                    continue
                # Don't surface stale locks to callers.
                if not _pid_alive(lock.pid):
                    self._delete_silent(child)
                    continue
                locks.append(lock)
            return ok(locks)

    async def lock_for(self, serial: str) -> Result[DeviceLock | None]:
        async with self._lock:
            path = self._path_for(serial)
            existing = self._read(path)
            if existing is None:
                return ok(None)
            if not _pid_alive(existing.pid):
                self._delete_silent(path)
                return ok(None)
            return ok(existing)

    # ----- helpers ------------------------------------------------------

    def _read(self, path: Path) -> DeviceLock | None:
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        try:
            return DeviceLock(
                serial=data["serial"],
                session_id=data["session_id"],
                pid=int(data["pid"]),
                started_at=datetime.fromisoformat(data["started_at"]),
                note=data.get("note"),
            )
        except (KeyError, ValueError):
            return None

    def _write(self, path: Path, lock: DeviceLock) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # O_EXCL keeps two racing processes from both succeeding.
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        try:
            fd = os.open(path, flags, 0o644)
        except FileExistsError:
            # Another process wrote between our read and write — reread and
            # check whether the new holder is us.
            existing = self._read(path)
            if existing is not None and existing.session_id == lock.session_id:
                return
            raise
        try:
            os.write(
                fd,
                json.dumps(
                    {
                        "serial": lock.serial,
                        "session_id": lock.session_id,
                        "pid": lock.pid,
                        "started_at": lock.started_at.isoformat(),
                        "note": lock.note,
                    }
                ).encode("utf-8"),
            )
        finally:
            os.close(fd)

    def _delete_silent(self, path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            return
        except OSError:
            return

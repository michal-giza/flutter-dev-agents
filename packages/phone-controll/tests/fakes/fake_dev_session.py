"""Fake DebugSessionRepository + IdeRepository + WdaSetupCli for tests."""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from pathlib import Path

from mcp_phone_controll.domain.entities import (
    BuildMode,
    DebugLogEntry,
    DebugSession,
    DebugSessionState,
    IdeKind,
    IdeWindow,
    ServiceExtensionResult,
)
from mcp_phone_controll.domain.failures import IdeWindowNotFoundFailure
from mcp_phone_controll.domain.result import ok, err
from mcp_phone_controll.infrastructure.process_runner import ProcessResult


class FakeDebugSessionRepository:
    def __init__(self) -> None:
        self._sessions: dict[str, DebugSession] = {}
        self._most_recent: str | None = None

    async def start(
        self,
        project_path: Path,
        device_serial: str,
        mode: BuildMode = BuildMode.DEBUG,
        flavor: str | None = None,
        target: str | None = None,
    ):
        sid = uuid.uuid4().hex[:12]
        sess = DebugSession(
            id=sid,
            project_path=project_path,
            device_serial=device_serial,
            mode=mode,
            started_at=datetime.now(),
            state=DebugSessionState.RUNNING,
            app_id=f"app-{sid}",
            vm_service_uri=f"ws://localhost:1234/{sid}/ws",
            flavor=flavor,
            target=target,
            pid=os.getpid(),
        )
        self._sessions[sid] = sess
        self._most_recent = sid
        return ok(sess)

    async def stop(self, session_id=None):
        target = session_id or self._most_recent
        if target is not None:
            self._sessions.pop(target, None)
            if self._most_recent == target:
                self._most_recent = next(iter(reversed(self._sessions)), None)
        return ok(None)

    async def restart(self, session_id=None, full_restart=False):
        target = session_id or self._most_recent
        if target is None or target not in self._sessions:
            return ok(None)
        return ok(self._sessions[target])

    async def attach(self, vm_service_uri, project_path):
        from mcp_phone_controll.domain.failures import DebugSessionFailure
        return err(
            DebugSessionFailure(message="not implemented in fake", next_action="ask_user")
        )

    async def list_sessions(self):
        return ok(list(self._sessions.values()))

    async def read_log(self, session_id=None, since_s=30, level="all", max_lines=500):
        return ok([
            DebugLogEntry(
                timestamp=datetime.now(),
                level="info",
                source="app",
                message="hello from fake",
            )
        ])

    async def tail_log(self, session_id, until_pattern, timeout_s=30.0):
        return ok([])

    async def call_service_extension(self, session_id, method, args=None):
        return ok(
            ServiceExtensionResult(method=method, result={"ok": True}, elapsed_ms=1)
        )


class FakeIdeRepository:
    def __init__(self) -> None:
        self._windows: dict[str, IdeWindow] = {}

    async def open_project(
        self, project_path, ide=IdeKind.VSCODE, new_window=True
    ):
        wid = uuid.uuid4().hex[:8]
        window = IdeWindow(
            window_id=wid,
            project_path=project_path,
            ide=ide,
            pid=os.getpid(),
            opened_at=datetime.now(),
        )
        self._windows[wid] = window
        return ok(window)

    async def list_windows(self):
        return ok(list(self._windows.values()))

    async def close_window(self, project_path=None, window_id=None):
        for wid, w in list(self._windows.items()):
            if (window_id and wid == window_id) or (
                project_path and w.project_path == project_path
            ):
                self._windows.pop(wid, None)
                return ok(None)
        return err(IdeWindowNotFoundFailure(message="no match"))

    async def focus_window(self, project_path):
        return ok(None)

    async def is_available(self, ide=IdeKind.VSCODE):
        return ok("Code 1.95.0")


class FakeWdaSetupCli:
    """Pretends to clone + xcodebuild without doing anything."""

    async def clone(self, target_dir, repo_url=None, timeout_s=300.0):
        target_dir.mkdir(parents=True, exist_ok=True)
        return ProcessResult(returncode=0, stdout="cloned", stderr="")

    async def build_for_testing(
        self, wda_dir, udid, scheme="WebDriverAgentRunner", timeout_s=1800.0
    ):
        return ProcessResult(returncode=0, stdout="** TEST BUILD SUCCEEDED **", stderr="")

"""flutter_machine_client — extended coverage with a scripted fake process.

Existing test (`test_flutter_machine_client.py`) covers a couple of paths
end-to-end. This file fills in the gaps the May 2026 code-review flagged
(24% → target 80%+):

  - start() spawns the right argv (modes, flavors, targets)
  - app.started event sets app_id + vm_service_uri + the started event
  - send() correlates response by id, cleans up pending dict on timeout
  - restart() before app_id raises a clear RuntimeError
  - stop() sends app.stop, terminates if still alive, escalates to kill
  - reader loop ignores malformed lines (graceful degradation)
  - log buffer respects BUFFER_CAPACITY ring eviction
  - is_running / pid / app_id / vm_service_uri properties update right

All hermetic: no real `flutter`, no real subprocess. We patch
`asyncio.create_subprocess_exec` to hand back a `_FakeFlutterProc` that
mimics the relevant `asyncio.subprocess.Process` surface.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_phone_controll.infrastructure.flutter_cli import FlutterCli
from mcp_phone_controll.infrastructure.flutter_machine_client import (
    FlutterMachineClient,
)


class _FakeStdin:
    """Auto-echoes responses for sent commands so tests don't hang for
    10s waiting on `app.stop` etc. Tests that want to control the
    response timing can set `auto_respond = False` before sending."""

    def __init__(self) -> None:
        self.lines: list[bytes] = []
        self.auto_respond = True
        self._stdout: _FakeStdout | None = None

    def bind_stdout(self, stdout: _FakeStdout) -> None:
        self._stdout = stdout

    def write(self, data: bytes) -> None:
        self.lines.append(data)
        if not self.auto_respond or self._stdout is None:
            return
        # Parse the outgoing daemon frame, push an empty-result response
        # with the same id so `send()` doesn't block on its timeout.
        try:
            raw = data.decode("utf-8").strip()
            if raw.startswith("[") and raw.endswith("]"):
                items = json.loads(raw)
                for item in items:
                    rid = item.get("id")
                    if isinstance(rid, int):
                        self._stdout.push_line(
                            json.dumps([{"id": rid, "result": {}}])
                        )
        except (ValueError, UnicodeDecodeError):
            pass

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        pass


class _FakeStdout:
    """Async-readable line source. Tests push frames via push_line() and
    None to signal EOF."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    def push_line(self, line: str) -> None:
        self._queue.put_nowait(line.encode("utf-8") + b"\n")

    def eof(self) -> None:
        self._queue.put_nowait(None)

    async def readline(self) -> bytes:
        item = await self._queue.get()
        return item if item is not None else b""


class _FakeFlutterProc:
    """Mimics the slice of `asyncio.subprocess.Process` the client uses."""

    def __init__(self) -> None:
        self.stdin = _FakeStdin()
        self.stdout = _FakeStdout()
        self.stderr = _FakeStdout()  # never read; included for shape
        self.stdin.bind_stdout(self.stdout)
        self.pid = 13371
        self.returncode: int | None = None
        self.terminated = False
        self.killed = False
        self._wait_event = asyncio.Event()

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15
        self._wait_event.set()
        self.stdout.eof()

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9
        self._wait_event.set()
        self.stdout.eof()

    async def wait(self) -> int:
        await self._wait_event.wait()
        return self.returncode or 0


# ---- helpers -----------------------------------------------------------


def _frame_started(app_id: str = "app-A", vm_uri: str = "ws://127.0.0.1:54321/ws") -> str:
    return json.dumps(
        [{"event": "app.started", "params": {"appId": app_id, "wsUri": vm_uri}}]
    )


def _frame_log(message: str) -> str:
    return json.dumps([{"event": "app.log", "params": {"log": message}}])


def _frame_response(req_id: int, result: object) -> str:
    return json.dumps([{"id": req_id, "result": result}])


async def _spawn_with_fake_proc(client: FlutterMachineClient, fake: _FakeFlutterProc):
    """Patch create_subprocess_exec to return our fake. Returns the
    started client. Caller is responsible for pushing app.started
    BEFORE awaiting start() — easiest pattern is a tiny background
    coroutine."""
    async def _fake_spawn(*a, **k):
        return fake

    return _fake_spawn


# ---- tests --------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_spawns_correct_argv(tmp_path: Path, monkeypatch):
    fake = _FakeFlutterProc()
    captured_argv: list[str] = []

    async def _fake_spawn(*argv, **kwargs):
        captured_argv.extend(argv)
        # Push app.started so the wait_for succeeds.
        fake.stdout.push_line(_frame_started())
        return fake

    cli = FlutterCli(runner=None)  # type: ignore[arg-type]
    client = FlutterMachineClient(cli)

    with patch(
        "mcp_phone_controll.infrastructure.flutter_machine_client.asyncio.create_subprocess_exec",
        new=_fake_spawn,
    ):
        await client.start(
            project_path=tmp_path,
            device_serial="emulator-5554",
            mode="profile",
            flavor="dev",
            target="lib/main_dev.dart",
            startup_timeout_s=2.0,
        )

    # argv must include the flutter binary, run --machine, mode flag, -d,
    # the serial, and both --flavor and --target.
    assert "run" in captured_argv
    assert "--machine" in captured_argv
    assert "--profile" in captured_argv
    assert "emulator-5554" in captured_argv
    assert "--flavor" in captured_argv and "dev" in captured_argv
    assert "--target" in captured_argv and "lib/main_dev.dart" in captured_argv

    # app.started should have populated app_id + vm_service_uri.
    assert client.app_id == "app-A"
    assert client.vm_service_uri and "ws://127.0.0.1" in client.vm_service_uri
    assert client.is_running is True
    assert client.pid == 13371

    await client.stop()


@pytest.mark.asyncio
async def test_send_correlates_response_by_id(tmp_path: Path):
    fake = _FakeFlutterProc()

    async def _fake_spawn(*a, **k):
        fake.stdout.push_line(_frame_started())
        return fake

    cli = FlutterCli(runner=None)  # type: ignore[arg-type]
    client = FlutterMachineClient(cli)
    with patch(
        "mcp_phone_controll.infrastructure.flutter_machine_client.asyncio.create_subprocess_exec",
        new=_fake_spawn,
    ):
        await client.start(
            project_path=tmp_path,
            device_serial="EMU",
            startup_timeout_s=2.0,
        )
        fake.stdin.auto_respond = False  # don't echo {} — push real result below

        # Kick off the send AND simultaneously push a matching response.
        async def _push_response_eventually():
            await asyncio.sleep(0.05)
            # First-issued id starts at 1.
            fake.stdout.push_line(_frame_response(1, {"echo": "hot reloaded"}))

        push_task = asyncio.create_task(_push_response_eventually())
        result = await client.send("app.restart", {"appId": "app-A"})
        await push_task

        assert result["result"] == {"echo": "hot reloaded"}
        # Pending dict cleaned up.
        assert client._pending == {}
        # The right line was written to stdin (one daemon frame).
        sent = fake.stdin.lines[0].decode()
        assert '"method": "app.restart"' in sent
        assert '"id": 1' in sent

        fake.stdin.auto_respond = True  # restore so stop() doesn't hang
        await client.stop()


@pytest.mark.asyncio
async def test_send_timeout_cleans_up_pending(tmp_path: Path):
    fake = _FakeFlutterProc()

    async def _fake_spawn(*a, **k):
        fake.stdout.push_line(_frame_started())
        return fake

    client = FlutterMachineClient(FlutterCli(runner=None))  # type: ignore[arg-type]
    with patch(
        "mcp_phone_controll.infrastructure.flutter_machine_client.asyncio.create_subprocess_exec",
        new=_fake_spawn,
    ):
        await client.start(
            project_path=tmp_path, device_serial="EMU", startup_timeout_s=2.0,
        )
        fake.stdin.auto_respond = False  # force the send() to time out
        with pytest.raises(asyncio.TimeoutError):
            await client.send("app.restart", response_timeout_s=0.05)
        # No leaked pending entry.
        assert client._pending == {}
        fake.stdin.auto_respond = True
        await client.stop()


@pytest.mark.asyncio
async def test_restart_before_app_id_raises(tmp_path: Path):
    client = FlutterMachineClient(FlutterCli(runner=None))  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="no app_id"):
        await client.restart()


@pytest.mark.asyncio
async def test_send_before_start_raises(tmp_path: Path):
    client = FlutterMachineClient(FlutterCli(runner=None))  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="not running"):
        await client.send("app.restart")


@pytest.mark.asyncio
async def test_stop_terminates_then_kills_if_needed(tmp_path: Path):
    """If `terminate` doesn't bring the process down within 5s, the
    client must escalate to `kill`. We simulate the slow-to-die case
    by overriding `wait()` to never resolve until kill() is called."""

    class _StuckProc(_FakeFlutterProc):
        def terminate(self) -> None:
            self.terminated = True
            # Deliberately do NOT set returncode/wait_event — emulates
            # a hung flutter process.
            self.stdout.eof()

    fake = _StuckProc()

    async def _fake_spawn(*a, **k):
        fake.stdout.push_line(_frame_started())
        return fake

    client = FlutterMachineClient(FlutterCli(runner=None))  # type: ignore[arg-type]
    with patch(
        "mcp_phone_controll.infrastructure.flutter_machine_client.asyncio.create_subprocess_exec",
        new=_fake_spawn,
    ):
        await client.start(
            project_path=tmp_path, device_serial="EMU", startup_timeout_s=2.0,
        )
        # auto-respond is on, so app.stop returns immediately and we
        # proceed straight to terminate. terminate doesn't set
        # _wait_event in this stuck variant → the 5 s wait_for inside
        # stop() raises TimeoutError → kill() escalates → wait_event
        # set → stop() returns. Budget: ~6 s wall clock.
        await asyncio.wait_for(client.stop(), timeout=10.0)
        assert fake.terminated is True
        assert fake.killed is True


@pytest.mark.asyncio
async def test_reader_ignores_malformed_lines(tmp_path: Path):
    fake = _FakeFlutterProc()

    async def _fake_spawn(*a, **k):
        fake.stdout.push_line(_frame_started())
        # Push garbage; reader must NOT die.
        fake.stdout.push_line("not json {{{")
        fake.stdout.push_line(_frame_log("hello world"))
        return fake

    client = FlutterMachineClient(FlutterCli(runner=None))  # type: ignore[arg-type]
    with patch(
        "mcp_phone_controll.infrastructure.flutter_machine_client.asyncio.create_subprocess_exec",
        new=_fake_spawn,
    ):
        await client.start(
            project_path=tmp_path, device_serial="EMU", startup_timeout_s=2.0,
        )
        # Give the reader a moment to drain.
        await asyncio.sleep(0.05)
        logs = client.recent_logs()
        # At least the "hello world" should have made it through despite
        # the garbage frame in between.
        assert any("hello world" in entry.message for entry in logs)
        await client.stop()


@pytest.mark.asyncio
async def test_log_buffer_respects_capacity(tmp_path: Path, monkeypatch):
    """The log ring buffer is capped at BUFFER_CAPACITY; older entries
    must be evicted, not memory-bombed."""
    # Shrink the cap so the test runs fast.
    monkeypatch.setattr(FlutterMachineClient, "BUFFER_CAPACITY", 5)

    fake = _FakeFlutterProc()

    async def _fake_spawn(*a, **k):
        fake.stdout.push_line(_frame_started())
        for i in range(20):
            fake.stdout.push_line(_frame_log(f"line-{i}"))
        return fake

    client = FlutterMachineClient(FlutterCli(runner=None))  # type: ignore[arg-type]
    with patch(
        "mcp_phone_controll.infrastructure.flutter_machine_client.asyncio.create_subprocess_exec",
        new=_fake_spawn,
    ):
        await client.start(
            project_path=tmp_path, device_serial="EMU", startup_timeout_s=2.0,
        )
        await asyncio.sleep(0.1)
        logs = client.recent_logs()
        # Buffer cap is 5 — most-recent five wins.
        assert len(logs) <= 5
        messages = [e.message for e in logs]
        assert any("line-19" in m for m in messages)
        # Oldest evicted.
        assert not any("line-0" in m for m in messages)
        await client.stop()

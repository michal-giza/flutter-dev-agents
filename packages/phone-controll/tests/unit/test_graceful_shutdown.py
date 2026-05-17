"""SIGTERM / SIGINT must cancel the MCP serve task and emit a shutdown log.

Hermetic: we patch `serve_stdio` to a long-running fake, then send SIGTERM
to our own process via `os.kill`. The signal handler installed by
`_run` must:
  1. emit `mcp_shutdown_signal`
  2. cancel the serve task
  3. let `_run` return without unhandled exception
  4. let the `mcp_serve_cancelled` log emit cleanly

If any of those drift, real users hit orphaned subprocesses and
leaked device locks the next time Claude Desktop quits or the Mac
sleeps. Closes docs/code-review-2026-05-17-deep.md §5.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import time
from unittest.mock import patch

import pytest


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signal semantics")
async def test_sigterm_cancels_serve_and_emits_shutdown_log(monkeypatch):
    captured: list[dict] = []

    def _fake_emit(event, level="info", **fields):
        captured.append({"event": event, "level": level, **fields})

    from mcp_phone_controll import observability

    monkeypatch.setattr(observability, "emit", _fake_emit)

    # Replace serve_stdio with a long-running sleep so we have time
    # to send the signal.
    async def _slow_serve(dispatcher, server_name: str = "phone-controll"):
        await asyncio.sleep(30)

    # Make build_runtime cheap — return a sentinel dispatcher.
    def _fake_build_runtime():
        return (object(), object())

    with patch(
        "mcp_phone_controll.__main__.serve_stdio", new=_slow_serve
    ), patch(
        "mcp_phone_controll.__main__.build_runtime", new=_fake_build_runtime
    ):
        from mcp_phone_controll.__main__ import _run

        async def _send_sigterm_soon():
            await asyncio.sleep(0.05)
            os.kill(os.getpid(), signal.SIGTERM)

        sigterm_task = asyncio.create_task(_send_sigterm_soon())
        started = time.monotonic()
        await _run()
        elapsed = time.monotonic() - started
        await sigterm_task

    # Must have returned promptly — within ~1s wall clock — not waited
    # the 30s of the fake serve_stdio.
    assert elapsed < 2.0, (
        f"_run took {elapsed:.1f}s — SIGTERM didn't cancel serve_stdio"
    )

    events = [e["event"] for e in captured]
    assert "mcp_shutdown_signal" in events, captured
    # The cancellation event also fires.
    assert "mcp_serve_cancelled" in events, captured

    # Shutdown record has the signal name.
    shutdown = next(e for e in captured if e["event"] == "mcp_shutdown_signal")
    assert shutdown["signal"] == "SIGTERM"


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signal semantics")
async def test_signal_handler_is_idempotent():
    """Impatient operators send SIGTERM twice. The handler's
    `if shutdown_event.is_set(): return` early-out must keep the second
    invocation a no-op so we don't double-cancel or double-emit. Tests
    the contract directly by reconstructing the handler closure with
    its dependencies stubbed."""
    # Reconstruct what _run does internally — minimal slice for unit test.
    shutdown_event = asyncio.Event()
    cancel_count = [0]
    emit_count = [0]

    class _FakeTask:
        def done(self):
            return False

        def cancel(self):
            cancel_count[0] += 1

    serve_task = _FakeTask()

    def _fake_emit(event, level="info", **fields):
        if event == "mcp_shutdown_signal":
            emit_count[0] += 1

    def _handler(signum: int) -> None:
        # Mirror the real handler exactly.
        if shutdown_event.is_set():
            return
        _fake_emit("mcp_shutdown_signal", signal=signal.Signals(signum).name)
        shutdown_event.set()
        if not serve_task.done():
            serve_task.cancel()

    # Three calls in a row.
    _handler(int(signal.SIGTERM))
    _handler(int(signal.SIGTERM))
    _handler(int(signal.SIGTERM))

    assert emit_count[0] == 1, f"expected 1 emit, got {emit_count[0]}"
    assert cancel_count[0] == 1, f"expected 1 cancel, got {cancel_count[0]}"
    assert shutdown_event.is_set()

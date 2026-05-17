"""Entrypoint: `python -m mcp_phone_controll`.

Wires the stdio MCP transport plus graceful-shutdown handlers. On
SIGTERM/SIGINT we:
  1. cancel the serve_stdio task (no new dispatches accepted)
  2. the container's atexit hook releases device locks held by this
     session_id (see container._release_session_locks_atexit)
  3. asyncio teardown lets spawned child processes finish via their
     normal cleanup

Why this matters: without signal handlers, killing the MCP process
(Claude Desktop quit, Mac sleep, `kill -TERM`) orphans
`flutter run --machine` + `xcodebuild` + `pymobiledevice3 tunneld`
children and leaves device locks on disk that the next session has
to `force_release_lock` manually. Closes the gap flagged in
docs/code-review-2026-05-17-deep.md §5.
"""

from __future__ import annotations

import asyncio
import signal

from .container import build_runtime
from .observability import emit
from .presentation.mcp_server import serve_stdio


async def _run() -> None:
    _, dispatcher = build_runtime()

    serve_task = asyncio.create_task(serve_stdio(dispatcher))

    loop = asyncio.get_event_loop()
    shutdown_event = asyncio.Event()

    def _handle_signal(signum: int) -> None:
        # Idempotent: a second SIGTERM (impatient operator) is a no-op.
        if shutdown_event.is_set():
            return
        emit(
            "mcp_shutdown_signal",
            signal=signal.Signals(signum).name,
            level="info",
        )
        shutdown_event.set()
        # Cancel the serve task so stdio_server() unwinds cleanly. The
        # container's atexit hook + child-process cleanup take it from
        # there. We do NOT call sys.exit — let asyncio drain naturally.
        if not serve_task.done():
            serve_task.cancel()

    # Register on the event loop where possible (async-friendly). On
    # Windows or non-main threads, fall back to signal.signal.
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _handle_signal, int(sig))
        except (NotImplementedError, RuntimeError):
            signal.signal(sig, lambda s, _f: _handle_signal(s))

    try:
        await serve_task
    except asyncio.CancelledError:
        # Expected on graceful shutdown.
        emit("mcp_serve_cancelled", level="info")


def main() -> None:
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        # Belt-and-suspenders: if Ctrl+C escapes the signal handler,
        # exit quietly rather than print a traceback.
        emit("mcp_keyboard_interrupt", level="info")


if __name__ == "__main__":
    main()

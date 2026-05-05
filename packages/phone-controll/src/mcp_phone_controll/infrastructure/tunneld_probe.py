"""Probe for `pymobiledevice3 remote tunneld` daemon.

Tunneld serves a small HTTP API on localhost (default port 49151) and exposes
the per-device RemoteServiceDiscovery endpoints needed for iOS 17+ developer
services (screenshot, dvt launch, syslog live, etc.). When tunneld isn't
running, every developer-tier call from `pymobiledevice3 ... --tunnel` fails
with "Unable to connect to Tunneld."

This module is a thin async health probe — it doesn't start tunneld (that
needs sudo and stays as a manual setup step), it just answers the question
"is it running right now?"
"""

from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass


DEFAULT_TUNNELD_HOST = "127.0.0.1"
DEFAULT_TUNNELD_PORT = 49151


@dataclass(frozen=True, slots=True)
class TunneldStatus:
    running: bool
    host: str
    port: int
    detail: str | None = None


async def probe_tunneld(
    host: str = DEFAULT_TUNNELD_HOST,
    port: int = DEFAULT_TUNNELD_PORT,
    timeout_s: float = 1.5,
) -> TunneldStatus:
    """Best-effort TCP probe of the tunneld daemon.

    Doesn't authenticate, doesn't enumerate tunnels — just checks the daemon
    accepts a connection. That's enough to distinguish "not running" from
    "running but maybe broken" for the doctor surface.
    """
    try:
        await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, _connect, host, port),
            timeout=timeout_s,
        )
        return TunneldStatus(running=True, host=host, port=port)
    except (OSError, asyncio.TimeoutError) as e:
        return TunneldStatus(
            running=False, host=host, port=port, detail=f"{type(e).__name__}: {e}"
        )


def _connect(host: str, port: int) -> None:
    with socket.create_connection((host, port), timeout=1.0):
        return

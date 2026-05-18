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
import json
import socket
import urllib.request
from dataclasses import dataclass

DEFAULT_TUNNELD_HOST = "127.0.0.1"
DEFAULT_TUNNELD_PORT = 49151


@dataclass(frozen=True, slots=True)
class TunneldStatus:
    running: bool
    host: str
    port: int
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class RsdEndpoint:
    """Per-device RemoteServiceDiscovery endpoint exposed by tunneld.

    `developer dvt screenshot`, `developer dvt launch`, `syslog live` and
    every other developer-tier subcommand on iOS 17+ requires `--rsd HOST
    PORT` (the deprecated `--tunnel UDID` shortcut was retired on the
    DVT path — pymobiledevice3 returns "Failed to start service" without
    explicit RSD coordinates).
    """

    host: str
    port: int


async def resolve_rsd(
    udid: str,
    tunneld_host: str = DEFAULT_TUNNELD_HOST,
    tunneld_port: int = DEFAULT_TUNNELD_PORT,
    timeout_s: float = 2.0,
) -> RsdEndpoint | None:
    """Resolve a UDID to its RSD endpoint by querying tunneld's HTTP API.

    Tunneld serves a JSON blob at `http://<host>:<port>/` keyed by UDID:
        {"<UDID>": [{"tunnel-address": "...", "tunnel-port": N, ...}]}

    Returns None if tunneld is unreachable, the UDID isn't in the
    advertised set, or the response is malformed. Caller is expected to
    fall back to the `--tunnel UDID` shortcut and surface the upstream
    failure if that doesn't work either.
    """
    url = f"http://{tunneld_host}:{tunneld_port}/"
    try:
        body = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, _http_get, url),
            timeout=timeout_s,
        )
    except (TimeoutError, OSError, ValueError):
        return None
    try:
        data = json.loads(body)
        tunnels = data.get(udid) or []
        if not tunnels:
            return None
        first = tunnels[0]
        host = first.get("tunnel-address")
        port = first.get("tunnel-port")
        if not host or not isinstance(port, int):
            return None
        return RsdEndpoint(host=host, port=port)
    except (json.JSONDecodeError, AttributeError, TypeError):
        return None


def _http_get(url: str) -> str:
    with urllib.request.urlopen(url, timeout=1.5) as r:
        return r.read().decode("utf-8", errors="replace")


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
    except (TimeoutError, OSError) as e:
        return TunneldStatus(
            running=False, host=host, port=port, detail=f"{type(e).__name__}: {e}"
        )


def _connect(host: str, port: int) -> None:
    with socket.create_connection((host, port), timeout=1.0):
        return

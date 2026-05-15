"""Lazy facebook-wda Client factory, dual-mode (physical device vs simulator).

Why dual-mode: `wda.USBClient(udid)` connects over **usbmux**, which is the
right transport for a physical iPhone — but simulators have no usbmux. Calling
`USBClient(<sim-udid>)` returns a stub whose first method call attribute-errors
with `'NoneType' object has no attribute 'make_http_connection'`. That broke
every UI-control tool against the iPhone 17 simulator in production
(backlog item K1, May 2026).

The split:

  - Physical device (UDID is NOT in `xcrun simctl list devices`): keep
    `wda.USBClient(udid)`. Transport: usbmux. Auth: none beyond the host
    being paired/trusted with the device.
  - Simulator (UDID IS in `simctl list devices`): use
    `wda.Client(f"http://127.0.0.1:{port}")`. Transport: TCP. The WDA
    server must already be running — typically via `xcodebuild
    test-without-building` against the WebDriverAgent project. The port
    defaults to 8100; override with `MCP_IOS_SIM_WDA_PORT`.

If the simulator branch can't reach WDA on the configured port, the factory
raises a clear `WdaUnreachable` with a `next_action`-friendly hint instead of
the cryptic `NoneType` attribute error.

Sessions are cached per UDID and reused — WDA session creation costs ~2s.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
from typing import Any, Protocol


class WdaFactory(Protocol):
    async def get(self, udid: str) -> Any: ...


class WdaUnreachable(RuntimeError):
    """The WDA server isn't reachable. Carries a structured hint so the
    repository layer can surface a useful `next_action` to agents."""

    def __init__(self, message: str, next_action: str, fix_command: str) -> None:
        super().__init__(message)
        self.next_action = next_action
        self.fix_command = fix_command


# ---- target-type detection ---------------------------------------------


# Cached: `xcrun simctl list -j` is slow (~200 ms) and the device set
# barely changes within a session. The list_simulators tool invalidates
# this cache when a new sim boots.
_simctl_cache: set[str] | None = None
_simctl_cache_lock = asyncio.Lock()


async def _booted_sim_udids() -> set[str]:
    """Return the set of currently-booted simulator UDIDs, cached.

    Robust to `xcrun simctl` being absent (non-mac) — returns an empty set
    so every UDID is treated as physical. That's a safe default: the
    USBClient path is more conservative and will fail with a clearer
    error if it really is the wrong transport.
    """
    global _simctl_cache
    async with _simctl_cache_lock:
        if _simctl_cache is not None:
            return _simctl_cache
        try:
            proc = await asyncio.create_subprocess_exec(
                "xcrun", "simctl", "list", "devices", "-j",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            out, _ = await proc.communicate()
            if proc.returncode != 0 or not out:
                _simctl_cache = set()
                return _simctl_cache
            data = json.loads(out)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            _simctl_cache = set()
            return _simctl_cache

        booted: set[str] = set()
        for _runtime, devices in (data.get("devices") or {}).items():
            for d in devices or []:
                if (d.get("state") or "").lower() == "booted" and d.get("udid"):
                    booted.add(d["udid"])
        _simctl_cache = booted
        return _simctl_cache


def invalidate_simctl_cache() -> None:
    """Call after booting/shutting a simulator so the next lookup re-reads."""
    global _simctl_cache
    _simctl_cache = None


# ---- port reachability -------------------------------------------------


def _wda_port() -> int:
    raw = os.environ.get("MCP_IOS_SIM_WDA_PORT", "")
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return 8100


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    """Best-effort TCP connect probe. Cheap; safe to call before every session."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# ---- the factory -------------------------------------------------------


class CachingWdaFactory:
    """Caches one WDA session per UDID. Routes by target type.

    Inject a custom `is_simulator` callable in tests instead of monkey-patching
    `xcrun simctl`. Inject a `wda_module` in tests to swap out facebook-wda for
    a fake.
    """

    def __init__(
        self,
        is_simulator=None,
        wda_module=None,
        port: int | None = None,
    ) -> None:
        self._clients: dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._is_simulator = is_simulator  # async callable or None
        self._wda_module = wda_module      # injected module or None (real wda)
        self._port_override = port

    async def get(self, udid: str) -> Any:
        async with self._lock:
            if udid in self._clients:
                return self._clients[udid]

            if self._wda_module is not None:
                wda = self._wda_module
            else:
                import wda as _wda  # local import — heavy + optional at test time

                wda = _wda

            is_sim = await self._classify(udid)
            if is_sim:
                client = await self._connect_simulator(wda, udid)
            else:
                client = await asyncio.to_thread(wda.USBClient, udid)

            session = await asyncio.to_thread(client.session)
            self._clients[udid] = session
            return session

    async def _classify(self, udid: str) -> bool:
        if self._is_simulator is not None:
            return bool(await self._is_simulator(udid))
        return udid in await _booted_sim_udids()

    async def _connect_simulator(self, wda, udid: str) -> Any:
        port = self._port_override or _wda_port()
        # Probe before constructing — if WDA isn't listening we want to fail
        # NOW with a clear message, not later with NoneType.
        if not _port_open("127.0.0.1", port):
            raise WdaUnreachable(
                message=(
                    f"WebDriverAgent isn't listening on 127.0.0.1:{port} for "
                    f"simulator {udid}. Launch WDA against the simulator first "
                    "(see fix_command), then retry."
                ),
                next_action="start_wda_on_simulator",
                fix_command=(
                    "# from the WebDriverAgent repo (clone if needed: "
                    "https://github.com/appium/WebDriverAgent):\n"
                    "xcodebuild test-without-building "
                    "-project WebDriverAgent.xcodeproj "
                    "-scheme WebDriverAgentRunner "
                    f"-destination 'platform=iOS Simulator,id={udid}' "
                    "USE_PORT=" + str(port) + "\n"
                    "# leave running in a separate terminal; it serves WDA on "
                    f"http://127.0.0.1:{port}\n"
                    "# override the port with the MCP_IOS_SIM_WDA_PORT env var "
                    "if 8100 is taken."
                ),
            )
        # TCP-based client. facebook-wda's `Client(url)` is the right
        # constructor for sims; `USBClient` is usbmux-only.
        return await asyncio.to_thread(wda.Client, f"http://127.0.0.1:{port}")

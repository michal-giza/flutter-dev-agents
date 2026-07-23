"""wda_factory — dual-mode WDA client construction (physical vs simulator).

Pins the K1 contract from docs/next-session-enhancements.md: the factory MUST
route by target type. Historically it always used `USBClient`, which crashed
the iPhone 17 simulator with `'NoneType' has no attribute 'make_http_connection'`.

Hermetic — no `xcrun`, no real `wda`. We inject:
- a fake `is_simulator` async callable so we don't need `xcrun simctl`
- a fake `wda` module with `USBClient` + `Client` constructors that just record
  what was called

The port-reachability probe is the one piece we can't fake easily; we test
both branches (port open / port closed) by binding a real localhost socket.
"""

from __future__ import annotations

import asyncio
import socket
from types import SimpleNamespace

import pytest

from mcp_phone_controll.infrastructure.wda_factory import (
    CachingWdaFactory,
    WdaUnreachable,
)

# ---- helpers -----------------------------------------------------------


class _FakeSession:
    def __init__(self) -> None:
        self.settings: list[dict] = []

    def appium_settings(self, value):
        self.settings.append(value)
        return value


class _FakeClient:
    """Records the kind of client constructed + any positional arg."""

    def __init__(self, kind: str, arg, status_raises: bool = False) -> None:
        self.kind = kind
        self.arg = arg
        self._status_raises = status_raises

    def status(self):
        # The physical (USBClient) branch probes /status before session()
        # so a device with no running WDA runner fails fast with
        # next_action=start_wda_on_device. Raise to simulate that.
        if self._status_raises:
            raise ConnectionError("usbmux: connection refused")
        return {"ready": True}

    def session(self) -> _FakeSession:
        return _FakeSession()


def _fake_wda_module(
    record: list[tuple[str, object]], usb_status_raises: bool = False
):
    def usb_client(udid):
        record.append(("USBClient", udid))
        return _FakeClient("USBClient", udid, status_raises=usb_status_raises)

    def tcp_client(url):
        record.append(("Client", url))
        return _FakeClient("Client", url)

    return SimpleNamespace(USBClient=usb_client, Client=tcp_client)


def _listening_port() -> tuple[int, socket.socket]:
    """Bind a real localhost TCP socket so the factory's reachability probe
    sees it as open. Returns (port, sock) — caller must close the sock."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    return s.getsockname()[1], s


# ---- tests -------------------------------------------------------------


@pytest.mark.asyncio
async def test_physical_device_uses_usbclient():
    record: list[tuple[str, object]] = []

    async def is_sim(_udid):
        return False

    factory = CachingWdaFactory(
        is_simulator=is_sim,
        wda_module=_fake_wda_module(record),
    )
    session = await factory.get("PHY-IPHONE-15-UDID")
    assert isinstance(session, _FakeSession)
    assert record == [("USBClient", "PHY-IPHONE-15-UDID")]


@pytest.mark.asyncio
async def test_physical_device_unreachable_routes_to_start_wda_on_device():
    """A physical device whose WDA runner isn't running must raise
    WdaUnreachable(next_action='start_wda_on_device') — the physical
    analogue of the simulator's port-probe guard. Without this, a tap
    before the runner is up dies with a raw usbmux error and the agent
    has no recovery path. This closes the iOS-26.5 field-report loop."""
    record: list[tuple[str, object]] = []

    async def is_sim(_udid):
        return False

    factory = CachingWdaFactory(
        is_simulator=is_sim,
        wda_module=_fake_wda_module(record, usb_status_raises=True),
    )
    with pytest.raises(WdaUnreachable) as ei:
        await factory.get("PHY-IPHONE-UDID")
    assert ei.value.next_action == "start_wda_on_device"
    assert "start_wda_on_device" in ei.value.fix_command
    # It still constructed the USBClient (right transport) before probing.
    assert record == [("USBClient", "PHY-IPHONE-UDID")]


@pytest.mark.asyncio
async def test_simulator_uses_tcp_client_when_wda_reachable():
    record: list[tuple[str, object]] = []

    async def is_sim(_udid):
        return True

    port, sock = _listening_port()
    try:
        factory = CachingWdaFactory(
            is_simulator=is_sim,
            wda_module=_fake_wda_module(record),
            port=port,
        )
        session = await factory.get("SIM-IPHONE-17-UDID")
        assert isinstance(session, _FakeSession)
        assert record == [("Client", f"http://127.0.0.1:{port}")]
    finally:
        sock.close()


@pytest.mark.asyncio
async def test_simulator_raises_wda_unreachable_when_port_closed():
    record: list[tuple[str, object]] = []

    async def is_sim(_udid):
        return True

    # Pick an almost-certainly-closed port.
    closed_port = 59999
    factory = CachingWdaFactory(
        is_simulator=is_sim,
        wda_module=_fake_wda_module(record),
        port=closed_port,
    )
    with pytest.raises(WdaUnreachable) as excinfo:
        await factory.get("SIM-IPHONE-17-UDID")
    # The error carries the structured next_action + fix command the
    # repository layer surfaces to agents.
    assert excinfo.value.next_action == "start_wda_on_simulator"
    assert "xcodebuild test-without-building" in excinfo.value.fix_command
    assert "WebDriverAgentRunner" in excinfo.value.fix_command
    # The fake module was NOT called — we short-circuited before constructing.
    assert record == []


@pytest.mark.asyncio
async def test_sessions_are_cached_per_udid():
    record: list[tuple[str, object]] = []

    async def is_sim(_udid):
        return False

    factory = CachingWdaFactory(
        is_simulator=is_sim,
        wda_module=_fake_wda_module(record),
    )
    s1 = await factory.get("UDID-A")
    s2 = await factory.get("UDID-A")
    s3 = await factory.get("UDID-B")
    assert s1 is s2
    assert s1 is not s3
    # Only two constructions: A once, B once.
    assert record == [("USBClient", "UDID-A"), ("USBClient", "UDID-B")]


@pytest.mark.asyncio
async def test_repository_translates_unreachable_to_structured_failure():
    """The repository layer's contract: WdaUnreachable from the factory
    becomes a UiFailure with `next_action="start_wda_on_simulator"`, never
    a raw exception bubbling to the agent."""
    from mcp_phone_controll.data.repositories.wda_ui_repository import (
        WdaUiRepository,
    )
    from mcp_phone_controll.infrastructure.wda_factory import WdaUnreachable

    class _RaisingFactory:
        async def get(self, _udid):
            raise WdaUnreachable(
                message="not listening on 127.0.0.1:8100",
                next_action="start_wda_on_simulator",
                fix_command="xcodebuild test-without-building ...",
            )

    repo = WdaUiRepository(_RaisingFactory())
    res = await repo.tap("SIM-UDID", 100, 200)
    assert res.is_err
    assert res.failure.next_action == "start_wda_on_simulator"
    assert "fix_command" in res.failure.details
    assert "xcodebuild" in res.failure.details["fix_command"]


@pytest.mark.asyncio
async def test_invalidate_forces_fresh_handshake():
    """v0.14.0 #1: invalidate(udid) drops the cached session so the next
    get() rebuilds — the hook the repo uses to recover a dead session."""
    record: list[tuple[str, object]] = []

    async def is_sim(_udid):
        return False

    factory = CachingWdaFactory(
        is_simulator=is_sim, wda_module=_fake_wda_module(record)
    )
    s1 = await factory.get("UDID-A")
    await factory.invalidate("UDID-A")
    s2 = await factory.get("UDID-A")
    assert s1 is not s2                       # rebuilt, not the cached one
    assert record == [("USBClient", "UDID-A"), ("USBClient", "UDID-A")]
    await factory.invalidate("UNKNOWN")       # no-op, must not raise


@pytest.mark.asyncio
async def test_snapshot_max_depth_applied_at_session_init():
    """v0.14.0 #3: raise WDA snapshot depth so deep trees don't abort
    actions with `call depth exceed N`."""
    record: list[tuple[str, object]] = []

    async def is_sim(_udid):
        return False

    factory = CachingWdaFactory(
        is_simulator=is_sim, wda_module=_fake_wda_module(record)
    )
    session = await factory.get("UDID-A")
    assert session.settings, "snapshotMaxDepth should be set at init"
    assert session.settings[0].get("snapshotMaxDepth", 0) >= 10


def test_port_override_via_env_var(monkeypatch):
    """`MCP_IOS_SIM_WDA_PORT` overrides the default 8100, in case Xcode
    auto-picks a different port."""
    from mcp_phone_controll.infrastructure.wda_factory import _wda_port

    monkeypatch.setenv("MCP_IOS_SIM_WDA_PORT", "9001")
    assert _wda_port() == 9001
    monkeypatch.setenv("MCP_IOS_SIM_WDA_PORT", "not-a-number")
    assert _wda_port() == 8100
    monkeypatch.delenv("MCP_IOS_SIM_WDA_PORT", raising=False)
    assert _wda_port() == 8100


def _drain():
    """Helper for the event loop when stacking awaits."""
    asyncio.get_event_loop()

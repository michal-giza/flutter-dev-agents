"""WDA session auto-refresh + snapshot depth (v0.14.0 #1/#3).

Field bug: `tap` stayed pinned to a dead WDA session id forever — even
after WDA restart, reselect, and a full sim reboot — because the factory
cached the session and nothing forced a re-handshake. These tests pin the
self-healing contract: a recoverable session error invalidates the cached
session and retries once with a fresh one.
"""

from __future__ import annotations

import pytest

from mcp_phone_controll.data.repositories.wda_ui_repository import (
    WdaUiRepository,
    _is_absent_error,
    _is_recoverable_session_error,
)
from mcp_phone_controll.domain.result import Err, Ok


class _StaleSession(Exception):
    """Mimics facebook-wda's dead-session error message."""

    def __init__(self) -> None:
        super().__init__("Unhandled endpoint: /session/DEAD-1234/wda/tap/0")


class _FakeSession:
    """A WDA session that fails with a stale error until 'refreshed'."""

    def __init__(self, alive: bool) -> None:
        self.alive = alive
        self.taps: list[tuple[int, int]] = []
        self.settings: list[dict] = []

    def appium_settings(self, value):
        self.settings.append(value)
        return value

    def tap(self, x, y):
        if not self.alive:
            raise _StaleSession()
        self.taps.append((x, y))

    # element selector for tap_text
    def __call__(self, **kwargs):
        return _FakeElement(self)


class _FakeElement:
    def __init__(self, session: _FakeSession) -> None:
        self._s = session

    @property
    def exists(self):
        if not self._s.alive:
            raise _StaleSession()
        return True

    def tap(self):
        if not self._s.alive:
            raise _StaleSession()
        self._s.taps.append((-1, -1))


class _FakeFactory:
    """Hands out a dead session first, a live one after invalidate()."""

    def __init__(self) -> None:
        self.dead = _FakeSession(alive=False)
        self.live = _FakeSession(alive=True)
        self._invalidated = False
        self.get_calls = 0
        self.invalidate_calls = 0

    async def get(self, udid):
        self.get_calls += 1
        return self.live if self._invalidated else self.dead

    async def invalidate(self, udid):
        self.invalidate_calls += 1
        self._invalidated = True


_S = "UDID-1"


@pytest.mark.asyncio
async def test_tap_recovers_from_stale_session():
    factory = _FakeFactory()
    repo = WdaUiRepository(factory)
    res = await repo.tap(_S, 100, 200)
    assert isinstance(res, Ok), res
    assert factory.invalidate_calls == 1          # dropped the dead session
    assert factory.live.taps == [(100, 200)]      # retried on the fresh one


@pytest.mark.asyncio
async def test_tap_text_recovers_from_stale_session():
    factory = _FakeFactory()
    repo = WdaUiRepository(factory)
    res = await repo.tap_text(_S, "Continue")
    assert isinstance(res, Ok), res
    assert factory.invalidate_calls == 1
    assert factory.live.taps == [(-1, -1)]


@pytest.mark.asyncio
async def test_non_recoverable_error_is_not_retried():
    """A genuine app error must surface, not trigger a session refresh."""

    class _BoomSession:
        def tap(self, x, y):
            raise ValueError("element obscured by overlay")

    class _Factory:
        def __init__(self):
            self.invalidate_calls = 0

        async def get(self, udid):
            return _BoomSession()

        async def invalidate(self, udid):
            self.invalidate_calls += 1

    factory = _Factory()
    repo = WdaUiRepository(factory)
    res = await repo.tap(_S, 1, 2)
    assert isinstance(res, Err)
    assert factory.invalidate_calls == 0           # no pointless re-handshake


@pytest.mark.asyncio
async def test_retry_failing_again_surfaces_error():
    """If the fresh session also fails, surface the failure (don't loop)."""

    class _AlwaysDead:
        async def get(self, udid):
            return _StaleSessionAlways()

        async def invalidate(self, udid):
            pass

    class _StaleSessionAlways:
        def tap(self, x, y):
            raise _StaleSession()

    repo = WdaUiRepository(_AlwaysDead())
    res = await repo.tap(_S, 1, 2)
    assert isinstance(res, Err)


def test_recoverable_error_detection():
    assert _is_recoverable_session_error(_StaleSession())
    assert _is_recoverable_session_error(Exception("invalid session id"))
    assert _is_recoverable_session_error(Exception("Session does not exist"))
    assert not _is_recoverable_session_error(ValueError("element not visible"))
    assert not _is_recoverable_session_error(Exception("timeout waiting for app"))


def test_exc_name_detection():
    class WDAInvalidSessionIdError(Exception):
        pass

    assert _is_recoverable_session_error(WDAInvalidSessionIdError("x"))


# --- v0.15.1: stale-element-reference means ABSENT (live-caught on sim) ---


class _StaleElement(Exception):
    """WDA's status-110 error when a previously-located element vanished."""

    def __init__(self) -> None:
        super().__init__(
            'stale element reference: The previously found element "Accept '
            'personalised ads" Button is not present in the current view anymore.'
        )


def test_is_absent_error_classifies_stale_and_not_found():
    assert _is_absent_error(_StaleElement())
    assert _is_absent_error(Exception("no matches found for predicate"))
    assert not _is_absent_error(Exception("invalid session id"))  # that's a session error


class _ElemDisappeared:
    """uiautomator-style element whose .wait() raises a stale-element error,
    mimicking WDA when the element disappeared between locate and re-check."""

    def wait(self, timeout_s):
        raise _StaleElement()


class _DisappearedSession:
    def __call__(self, **kwargs):
        return _ElemDisappeared()


class _StableFactory:
    def __init__(self):
        self._s = _DisappearedSession()

    async def get(self, udid):
        return self._s

    async def invalidate(self, udid):
        # Must NOT be called — a stale ELEMENT is not a dead SESSION.
        raise AssertionError("stale element wrongly triggered a session refresh")


@pytest.mark.asyncio
async def test_find_treats_stale_element_as_absent():
    """find() returns ok(None) — not an error — when the element is stale,
    so wait_until(gone) on a vanished element concludes 'met', and no
    session re-handshake is triggered."""
    repo = WdaUiRepository(_StableFactory())
    res = await repo.find(_S, text="Accept personalised ads")
    assert isinstance(res, Ok), res
    assert res.value is None

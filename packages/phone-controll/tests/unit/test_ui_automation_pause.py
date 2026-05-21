"""Tests for the v0.3.0 phase-8.5 pause/resume_ui_automation
paired tools.

What we validate:

- pause disables both helper packages when both are enabled
- pause is a no-op when the helper isn't installed (absent)
- pause is a no-op when the helper is already disabled
- pause records the prior package_states so resume can no-op
  if both were already off when pause was called
- resume re-enables previously-disabled helpers
- resume sleeps for settle_ms after pm enable (mocked)
- bracket invariant: pause -> resume returns the device to the
  same state it started in
- AdbFailure is returned when pm disable-user / pm enable / pm
  list packages fail
- serial threads through resolve_serial correctly
"""

from __future__ import annotations

import asyncio

import pytest

from mcp_phone_controll.domain.result import Err, Ok, ok
from mcp_phone_controll.domain.usecases.ui_automation_pause import (
    PauseUiAutomation,
    PauseUiAutomationParams,
    ResumeUiAutomation,
    ResumeUiAutomationParams,
)
from mcp_phone_controll.infrastructure.process_runner import ProcessResult

# ============================================================
# Test doubles
# ============================================================


class _FakeAdb:
    """AdbClient stub.

    Configure responses keyed by command pattern. The fake
    matches the *suffix* of the shell call (e.g. ('pm', 'list',
    'packages', 'com.github.uiautomator') for the list call).

    By default, returns ok=True with empty stdout. Override with
    `responses` dict for command-specific outputs.
    """

    def __init__(
        self,
        responses: dict[tuple[str, ...], ProcessResult] | None = None,
        default: ProcessResult | None = None,
    ):
        self.responses = responses or {}
        self.default = default or ProcessResult(
            stdout="", stderr="", returncode=0
        )
        self.calls: list[tuple[str, ...]] = []

    async def shell(self, serial: str, *args: str, timeout_s: float = 30.0):
        self.calls.append((serial, *args))
        # Try to match by the full args tuple (without serial)
        return self.responses.get(args, self.default)


class _FakeState:
    """SessionStateRepository stub. Always returns the same
    selected serial so resolve_serial succeeds."""

    def __init__(self, serial: str = "emulator-5554"):
        self._serial = serial

    async def get_selected_serial(self):
        return ok(self._serial)

    # protocol completeness (not exercised here)
    async def set_selected_serial(self, _: str):  # pragma: no cover
        return ok(None)

    async def clear_selected_serial(self):  # pragma: no cover
        return ok(None)


# ============================================================
# Helpers for canned ProcessResults
# ============================================================


PKG_DRIVER = "com.github.uiautomator"
PKG_TEST = "com.github.uiautomator.test"


def _list_pkg(installed: bool, package: str) -> ProcessResult:
    """Mock `pm list packages <pkg>`."""
    return ProcessResult(
        stdout=f"package:{package}\n" if installed else "",
        stderr="",
        returncode=0,
    )


def _list_pkg_enabled(enabled: bool, package: str) -> ProcessResult:
    """Mock `pm list packages -e <pkg>`."""
    return ProcessResult(
        stdout=f"package:{package}\n" if enabled else "",
        stderr="",
        returncode=0,
    )


def _both_installed_enabled() -> dict[tuple[str, ...], ProcessResult]:
    return {
        ("pm", "list", "packages", PKG_DRIVER): _list_pkg(True, PKG_DRIVER),
        ("pm", "list", "packages", "-e", PKG_DRIVER): _list_pkg_enabled(True, PKG_DRIVER),
        ("pm", "list", "packages", PKG_TEST): _list_pkg(True, PKG_TEST),
        ("pm", "list", "packages", "-e", PKG_TEST): _list_pkg_enabled(True, PKG_TEST),
        ("pm", "disable-user", "--user", "0", PKG_DRIVER):
            ProcessResult(stdout="", stderr="", returncode=0),
        ("pm", "disable-user", "--user", "0", PKG_TEST):
            ProcessResult(stdout="", stderr="", returncode=0),
        ("pm", "enable", PKG_DRIVER): ProcessResult(stdout="", stderr="", returncode=0),
        ("pm", "enable", PKG_TEST): ProcessResult(stdout="", stderr="", returncode=0),
    }


def _both_absent() -> dict[tuple[str, ...], ProcessResult]:
    return {
        ("pm", "list", "packages", PKG_DRIVER): _list_pkg(False, PKG_DRIVER),
        ("pm", "list", "packages", PKG_TEST): _list_pkg(False, PKG_TEST),
    }


def _both_installed_disabled() -> dict[tuple[str, ...], ProcessResult]:
    return {
        ("pm", "list", "packages", PKG_DRIVER): _list_pkg(True, PKG_DRIVER),
        ("pm", "list", "packages", "-e", PKG_DRIVER): _list_pkg_enabled(False, PKG_DRIVER),
        ("pm", "list", "packages", PKG_TEST): _list_pkg(True, PKG_TEST),
        ("pm", "list", "packages", "-e", PKG_TEST): _list_pkg_enabled(False, PKG_TEST),
        ("pm", "enable", PKG_DRIVER): ProcessResult(stdout="", stderr="", returncode=0),
        ("pm", "enable", PKG_TEST): ProcessResult(stdout="", stderr="", returncode=0),
    }


# ============================================================
# Pause tests
# ============================================================


@pytest.mark.asyncio
async def test_pause_disables_both_helpers_when_enabled():
    adb = _FakeAdb(responses=_both_installed_enabled())
    state = _FakeState()
    res = await PauseUiAutomation(state, adb)(
        PauseUiAutomationParams()
    )
    assert isinstance(res, Ok)
    v = res.value
    assert v.serial == "emulator-5554"
    assert set(v.paused) == {PKG_DRIVER, PKG_TEST}
    assert v.already_disabled == ()
    assert v.not_installed == ()
    assert v.package_states == {PKG_DRIVER: True, PKG_TEST: True}
    # Verify the disable command was actually issued for each
    issued = [c for c in adb.calls if "disable-user" in c]
    assert len(issued) == 2


@pytest.mark.asyncio
async def test_pause_is_noop_when_helper_absent():
    adb = _FakeAdb(responses=_both_absent())
    state = _FakeState()
    res = await PauseUiAutomation(state, adb)(
        PauseUiAutomationParams()
    )
    assert isinstance(res, Ok)
    v = res.value
    assert v.paused == ()
    assert set(v.not_installed) == {PKG_DRIVER, PKG_TEST}
    # No disable-user calls expected
    assert not any("disable-user" in c for c in adb.calls)
    # Advice should say 'not installed' / 'no helper present'
    assert "not installed" in v.advice.lower() or "no" in v.advice.lower()


@pytest.mark.asyncio
async def test_pause_is_noop_when_already_disabled():
    adb = _FakeAdb(responses=_both_installed_disabled())
    state = _FakeState()
    res = await PauseUiAutomation(state, adb)(
        PauseUiAutomationParams()
    )
    assert isinstance(res, Ok)
    v = res.value
    assert v.paused == ()
    assert set(v.already_disabled) == {PKG_DRIVER, PKG_TEST}
    assert v.package_states == {PKG_DRIVER: False, PKG_TEST: False}
    # No disable command was issued
    assert not any("disable-user" in c for c in adb.calls)


@pytest.mark.asyncio
async def test_pause_returns_adb_failure_when_disable_fails():
    responses = _both_installed_enabled()
    responses[("pm", "disable-user", "--user", "0", PKG_DRIVER)] = ProcessResult(
        stdout="", stderr="permission denied", returncode=1,
    )
    adb = _FakeAdb(responses=responses)
    state = _FakeState()
    res = await PauseUiAutomation(state, adb)(
        PauseUiAutomationParams()
    )
    assert isinstance(res, Err)
    # Failure message should mention the package
    assert PKG_DRIVER in res.failure.message
    assert res.failure.details["stderr"] == "permission denied"


@pytest.mark.asyncio
async def test_pause_returns_adb_failure_when_list_fails():
    responses = {
        ("pm", "list", "packages", PKG_DRIVER): ProcessResult(
            stdout="", stderr="device offline", returncode=1,
        ),
    }
    adb = _FakeAdb(responses=responses)
    state = _FakeState()
    res = await PauseUiAutomation(state, adb)(
        PauseUiAutomationParams()
    )
    assert isinstance(res, Err)
    assert "pm list packages" in res.failure.message


# ============================================================
# Resume tests
# ============================================================


@pytest.mark.asyncio
async def test_resume_enables_disabled_helpers():
    adb = _FakeAdb(responses=_both_installed_disabled())
    state = _FakeState()
    res = await ResumeUiAutomation(state, adb)(
        ResumeUiAutomationParams(settle_ms=0)
    )
    assert isinstance(res, Ok)
    v = res.value
    assert set(v.resumed) == {PKG_DRIVER, PKG_TEST}
    assert v.already_enabled == ()
    # Verify enable calls issued: (serial, 'pm', 'enable', pkg)
    enables = [c for c in adb.calls if len(c) >= 3 and c[1:3] == ("pm", "enable")]
    assert len(enables) == 2


@pytest.mark.asyncio
async def test_resume_is_noop_when_already_enabled():
    adb = _FakeAdb(responses=_both_installed_enabled())
    state = _FakeState()
    res = await ResumeUiAutomation(state, adb)(
        ResumeUiAutomationParams(settle_ms=0)
    )
    assert isinstance(res, Ok)
    v = res.value
    assert v.resumed == ()
    assert set(v.already_enabled) == {PKG_DRIVER, PKG_TEST}
    # No enable calls: (serial, 'pm', 'enable', pkg)
    assert not any(len(c) >= 3 and c[1:3] == ("pm", "enable") for c in adb.calls)
    assert v.latency_ms == 0


@pytest.mark.asyncio
async def test_resume_is_noop_when_helper_absent():
    adb = _FakeAdb(responses=_both_absent())
    state = _FakeState()
    res = await ResumeUiAutomation(state, adb)(
        ResumeUiAutomationParams(settle_ms=0)
    )
    assert isinstance(res, Ok)
    v = res.value
    assert v.resumed == ()
    assert set(v.not_installed) == {PKG_DRIVER, PKG_TEST}


@pytest.mark.asyncio
async def test_resume_settles_after_enable(monkeypatch):
    adb = _FakeAdb(responses=_both_installed_disabled())
    state = _FakeState()

    sleep_calls: list[float] = []

    async def _fake_sleep(s: float):
        sleep_calls.append(s)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    res = await ResumeUiAutomation(state, adb)(
        ResumeUiAutomationParams(settle_ms=500)
    )
    assert isinstance(res, Ok)
    # Sleep was called with 0.5s
    assert sleep_calls == [0.5]
    assert res.value.latency_ms == 500


@pytest.mark.asyncio
async def test_resume_no_sleep_when_nothing_resumed(monkeypatch):
    adb = _FakeAdb(responses=_both_installed_enabled())  # already enabled
    state = _FakeState()
    sleep_calls: list[float] = []

    async def _fake_sleep(s: float):
        sleep_calls.append(s)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    res = await ResumeUiAutomation(state, adb)(
        ResumeUiAutomationParams(settle_ms=500)
    )
    assert isinstance(res, Ok)
    # No sleep — nothing was resumed
    assert sleep_calls == []


@pytest.mark.asyncio
async def test_resume_returns_adb_failure_when_enable_fails():
    responses = _both_installed_disabled()
    responses[("pm", "enable", PKG_TEST)] = ProcessResult(
        stdout="", stderr="permission denied", returncode=1,
    )
    adb = _FakeAdb(responses=responses)
    state = _FakeState()
    res = await ResumeUiAutomation(state, adb)(
        ResumeUiAutomationParams(settle_ms=0)
    )
    assert isinstance(res, Err)
    assert PKG_TEST in res.failure.message


# ============================================================
# Bracket invariant
# ============================================================


@pytest.mark.asyncio
async def test_pause_resume_round_trip_restores_state():
    """Pause then resume — both helpers should end up enabled
    again."""
    # Start: enabled. After pause: disabled. After resume: enabled.
    # We model this with a stateful fake that tracks current state.
    state_pkgs = {PKG_DRIVER: True, PKG_TEST: True}

    class _StatefulAdb:
        def __init__(self):
            self.calls: list[tuple[str, ...]] = []

        async def shell(self, serial: str, *args: str, timeout_s: float = 30.0):
            self.calls.append(args)
            if args[:3] == ("pm", "list", "packages"):
                # `pm list packages <pkg>` or `pm list packages -e <pkg>`
                if args[3] == "-e":
                    pkg = args[4]
                    return ProcessResult(
                        stdout=(
                            f"package:{pkg}\n" if state_pkgs.get(pkg) else ""
                        ),
                        stderr="", returncode=0,
                    )
                else:
                    pkg = args[3]
                    return ProcessResult(
                        stdout=(
                            f"package:{pkg}\n" if pkg in state_pkgs else ""
                        ),
                        stderr="", returncode=0,
                    )
            if args[:2] == ("pm", "disable-user"):
                pkg = args[-1]
                state_pkgs[pkg] = False
                return ProcessResult(stdout="", stderr="", returncode=0)
            if args[:2] == ("pm", "enable"):
                pkg = args[-1]
                state_pkgs[pkg] = True
                return ProcessResult(stdout="", stderr="", returncode=0)
            return ProcessResult(stdout="", stderr="", returncode=0)

    adb = _StatefulAdb()
    sess = _FakeState()

    pause_res = await PauseUiAutomation(sess, adb)(
        PauseUiAutomationParams()
    )
    assert isinstance(pause_res, Ok)
    assert state_pkgs == {PKG_DRIVER: False, PKG_TEST: False}

    resume_res = await ResumeUiAutomation(sess, adb)(
        ResumeUiAutomationParams(settle_ms=0)
    )
    assert isinstance(resume_res, Ok)
    assert state_pkgs == {PKG_DRIVER: True, PKG_TEST: True}


# ============================================================
# Serial threading
# ============================================================


@pytest.mark.asyncio
async def test_explicit_serial_overrides_session():
    adb = _FakeAdb(responses=_both_absent())
    state = _FakeState(serial="session-default")
    res = await PauseUiAutomation(state, adb)(
        PauseUiAutomationParams(serial="explicit-1234")
    )
    assert isinstance(res, Ok)
    # First call's serial arg
    assert adb.calls[0][0] == "explicit-1234"

"""Unit tests for tap_and_verify and assert_no_errors_since."""

from __future__ import annotations

import pytest

from mcp_phone_controll.domain.entities import LogEntry, LogLevel, UiElement
from mcp_phone_controll.domain.usecases.ui_verify import (
    AssertNoErrorsSince,
    AssertNoErrorsSinceParams,
    TapAndVerify,
    TapAndVerifyParams,
)
from mcp_phone_controll.domain.result import Err, ok

from tests.fakes.fake_repositories import (
    FakeObservationRepository,
    FakeSessionStateRepository,
    FakeUiRepository,
)


@pytest.mark.asyncio
async def test_tap_and_verify_succeeds_when_expected_appears():
    elem = UiElement(
        text="Welcome",
        resource_id=None,
        class_name=None,
        content_description=None,
        bounds=(0, 0, 1, 1),
        enabled=True,
        clickable=True,
    )
    state = FakeSessionStateRepository(serial="EMU01")
    ui = FakeUiRepository(found=elem)
    uc = TapAndVerify(ui, state)
    res = await uc.execute(
        TapAndVerifyParams(text="Sign in", expect_text="Welcome", timeout_s=1.0)
    )
    assert res.is_ok and res.value.text == "Welcome"


@pytest.mark.asyncio
async def test_tap_and_verify_fails_when_expected_missing():
    state = FakeSessionStateRepository(serial="EMU01")
    ui = FakeUiRepository(found=None)  # wait_for returns Err
    uc = TapAndVerify(ui, state)
    res = await uc.execute(
        TapAndVerifyParams(text="Sign in", expect_text="Welcome", timeout_s=0.1)
    )
    assert isinstance(res, Err)
    assert res.failure.next_action == "capture_diagnostics"


@pytest.mark.asyncio
async def test_tap_and_verify_requires_expectation():
    state = FakeSessionStateRepository(serial="EMU01")
    ui = FakeUiRepository(found=None)
    uc = TapAndVerify(ui, state)
    res = await uc.execute(TapAndVerifyParams(text="Sign in"))
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"
    assert "corrected_example" in res.failure.details


@pytest.mark.asyncio
async def test_assert_no_errors_since_passes_when_clean():
    state = FakeSessionStateRepository(serial="EMU01")
    obs = FakeObservationRepository(name="clean")  # default returns WARN
    uc = AssertNoErrorsSince(obs, state)
    res = await uc.execute(AssertNoErrorsSinceParams(since_s=10))
    assert res.is_ok
    assert res.value == []


class _ErrorSpewingObservation(FakeObservationRepository):
    async def read_logs(self, serial, since_s=30, tag=None, min_level=LogLevel.WARN, max_lines=500):
        return ok(
            [
                LogEntry(
                    timestamp="01-01 00:00:00.000",
                    level=LogLevel.ERROR,
                    tag="boom",
                    pid=1,
                    message="NullPointerException at MainActivity.onCreate",
                )
            ]
        )


@pytest.mark.asyncio
async def test_assert_no_errors_since_fails_with_error_log():
    state = FakeSessionStateRepository(serial="EMU01")
    obs = _ErrorSpewingObservation(name="boom")
    uc = AssertNoErrorsSince(obs, state)
    res = await uc.execute(AssertNoErrorsSinceParams(since_s=10))
    assert isinstance(res, Err)
    assert res.failure.next_action == "capture_diagnostics"
    assert res.failure.details["count"] == 1

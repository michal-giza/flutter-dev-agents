"""UI query use cases — find, wait, dump, assert."""

from __future__ import annotations

from dataclasses import dataclass

from ..entities import UiElement
from ..failures import UiElementNotFoundFailure
from ..repositories import SessionStateRepository, UiRepository
from ..result import Err, Result, err, ok
from ._helpers import resolve_serial
from .base import BaseUseCase


@dataclass(frozen=True, slots=True)
class FindElementParams:
    text: str | None = None
    resource_id: str | None = None
    class_name: str | None = None
    timeout_s: float = 5.0
    serial: str | None = None


class FindElement(BaseUseCase[FindElementParams, UiElement | None]):
    def __init__(self, ui: UiRepository, state: SessionStateRepository) -> None:
        self._ui = ui
        self._state = state

    async def execute(self, params: FindElementParams) -> Result[UiElement | None]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        return await self._ui.find(
            serial_res.value,
            text=params.text,
            resource_id=params.resource_id,
            class_name=params.class_name,
            timeout_s=params.timeout_s,
        )


@dataclass(frozen=True, slots=True)
class WaitForElementParams:
    text: str | None = None
    resource_id: str | None = None
    timeout_s: float = 10.0
    serial: str | None = None


class WaitForElement(BaseUseCase[WaitForElementParams, UiElement]):
    def __init__(self, ui: UiRepository, state: SessionStateRepository) -> None:
        self._ui = ui
        self._state = state

    async def execute(self, params: WaitForElementParams) -> Result[UiElement]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        return await self._ui.wait_for(
            serial_res.value,
            text=params.text,
            resource_id=params.resource_id,
            timeout_s=params.timeout_s,
        )


@dataclass(frozen=True, slots=True)
class DumpUiParams:
    serial: str | None = None


class DumpUi(BaseUseCase[DumpUiParams, str]):
    def __init__(self, ui: UiRepository, state: SessionStateRepository) -> None:
        self._ui = ui
        self._state = state

    async def execute(self, params: DumpUiParams) -> Result[str]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        return await self._ui.dump_ui(serial_res.value)


@dataclass(frozen=True, slots=True)
class AssertVisibleParams:
    text: str | None = None
    resource_id: str | None = None
    timeout_s: float = 5.0
    serial: str | None = None


class AssertVisible(BaseUseCase[AssertVisibleParams, UiElement]):
    def __init__(self, ui: UiRepository, state: SessionStateRepository) -> None:
        self._ui = ui
        self._state = state

    async def execute(self, params: AssertVisibleParams) -> Result[UiElement]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        find_res = await self._ui.find(
            serial_res.value,
            text=params.text,
            resource_id=params.resource_id,
            timeout_s=params.timeout_s,
        )
        if isinstance(find_res, Err):
            return find_res
        if find_res.value is None:
            return err(
                UiElementNotFoundFailure(
                    message="Expected element not visible",
                    details={
                        "text": params.text,
                        "resource_id": params.resource_id,
                        "timeout_s": params.timeout_s,
                    },
                )
            )
        return ok(find_res.value)

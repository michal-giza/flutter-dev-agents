"""UI input use cases — tap, swipe, type, key."""

from __future__ import annotations

from dataclasses import dataclass

from ..repositories import SessionStateRepository, UiRepository
from ..result import Err, Result
from .base import BaseUseCase
from ._helpers import resolve_serial


@dataclass(frozen=True, slots=True)
class TapParams:
    x: int
    y: int
    serial: str | None = None


class Tap(BaseUseCase[TapParams, None]):
    def __init__(self, ui: UiRepository, state: SessionStateRepository) -> None:
        self._ui = ui
        self._state = state

    async def execute(self, params: TapParams) -> Result[None]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        return await self._ui.tap(serial_res.value, params.x, params.y)


@dataclass(frozen=True, slots=True)
class TapTextParams:
    text: str
    exact: bool = False
    serial: str | None = None


class TapText(BaseUseCase[TapTextParams, None]):
    def __init__(self, ui: UiRepository, state: SessionStateRepository) -> None:
        self._ui = ui
        self._state = state

    async def execute(self, params: TapTextParams) -> Result[None]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        return await self._ui.tap_text(serial_res.value, params.text, params.exact)


@dataclass(frozen=True, slots=True)
class SwipeParams:
    x1: int
    y1: int
    x2: int
    y2: int
    duration_ms: int = 300
    serial: str | None = None


class Swipe(BaseUseCase[SwipeParams, None]):
    def __init__(self, ui: UiRepository, state: SessionStateRepository) -> None:
        self._ui = ui
        self._state = state

    async def execute(self, params: SwipeParams) -> Result[None]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        return await self._ui.swipe(
            serial_res.value, params.x1, params.y1, params.x2, params.y2, params.duration_ms
        )


@dataclass(frozen=True, slots=True)
class TypeTextParams:
    text: str
    serial: str | None = None


class TypeText(BaseUseCase[TypeTextParams, None]):
    def __init__(self, ui: UiRepository, state: SessionStateRepository) -> None:
        self._ui = ui
        self._state = state

    async def execute(self, params: TypeTextParams) -> Result[None]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        return await self._ui.type_text(serial_res.value, params.text)


@dataclass(frozen=True, slots=True)
class PressKeyParams:
    keycode: str
    serial: str | None = None


class PressKey(BaseUseCase[PressKeyParams, None]):
    def __init__(self, ui: UiRepository, state: SessionStateRepository) -> None:
        self._ui = ui
        self._state = state

    async def execute(self, params: PressKeyParams) -> Result[None]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        return await self._ui.press_key(serial_res.value, params.keycode)

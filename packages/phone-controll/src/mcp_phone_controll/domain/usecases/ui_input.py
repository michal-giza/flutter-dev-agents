"""UI input use cases — tap, swipe, type, key."""

from __future__ import annotations

from dataclasses import dataclass

from ..failures import InvalidArgumentFailure, UiElementNotFoundFailure
from ..repositories import SessionStateRepository, UiRepository
from ..result import Err, Result, err
from ._helpers import resolve_serial
from .base import BaseUseCase


@dataclass(frozen=True, slots=True)
class TapParams:
    # Coordinate tap (x AND y) OR a semantic selector (text / resource_id /
    # class_name). At least one path must be supplied. Selectors are
    # resolved + tapped server-side in ONE call — the agent never needs to
    # screenshot, reason over pixels, or compute coordinates. This is the
    # fast, deterministic path; x/y is the fallback for the rare element a
    # selector can't address (a custom-drawn canvas hit-target, etc).
    x: int | None = None
    y: int | None = None
    text: str | None = None
    resource_id: str | None = None
    class_name: str | None = None
    exact: bool = False
    timeout_s: float = 5.0
    serial: str | None = None


class Tap(BaseUseCase[TapParams, None]):
    """Tap by coordinates OR by semantic selector (resolved server-side).

    Resolution order: explicit (x, y) → `text` (via the hardened
    `tap_text` path) → `resource_id`/`class_name` (find → tap the
    element's center). Reuses the existing repository primitives so the
    Polish-diacritic / Samsung-adb-fallback hardening in `tap_text`/`tap`
    applies on every path.
    """

    def __init__(self, ui: UiRepository, state: SessionStateRepository) -> None:
        self._ui = ui
        self._state = state

    async def execute(self, params: TapParams) -> Result[None]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        serial = serial_res.value

        # 1) Explicit coordinates win — the unambiguous fallback path.
        if params.x is not None and params.y is not None:
            return await self._ui.tap(serial, params.x, params.y)

        # 2) Text selector → the hardened tap_text path (NFC / NBSP /
        #    dump-scan fallback / Samsung adb-tap all live there).
        if params.text is not None:
            return await self._ui.tap_text(serial, params.text, params.exact)

        # 3) resource_id / class_name → resolve to an element, tap centre.
        if params.resource_id is not None or params.class_name is not None:
            find_res = await self._ui.find(
                serial,
                resource_id=params.resource_id,
                class_name=params.class_name,
                timeout_s=params.timeout_s,
            )
            if isinstance(find_res, Err):
                return find_res
            element = find_res.value
            if element is None:
                return err(
                    UiElementNotFoundFailure(
                        message=(
                            "no element matched the selector within "
                            f"{params.timeout_s}s"
                        ),
                        next_action="capture_diagnostics",
                        details={
                            "resource_id": params.resource_id,
                            "class_name": params.class_name,
                            "timeout_s": params.timeout_s,
                        },
                    )
                )
            b = element.bounds
            return await self._ui.tap(
                serial, b.x + b.width // 2, b.y + b.height // 2
            )

        # 4) Nothing actionable supplied.
        return err(
            InvalidArgumentFailure(
                message=(
                    "tap requires either (x, y) coordinates or a selector "
                    "(text / resource_id / class_name)."
                ),
                next_action="fix_arguments",
                details={
                    "corrected_example": {"resource_id": "com.example:id/btn_signin"},
                    "hint": (
                        "Prefer a selector over coordinates — it's faster and "
                        "needs no screenshot. Get selectors from extract_ui_graph."
                    ),
                },
            )
        )


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

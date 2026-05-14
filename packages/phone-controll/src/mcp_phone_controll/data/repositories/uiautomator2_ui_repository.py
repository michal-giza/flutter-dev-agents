"""UiRepository implementation backed by uiautomator2."""

from __future__ import annotations

import asyncio
import re

from ...domain.entities import Bounds, UiElement
from ...domain.failures import TimeoutFailure, UiElementNotFoundFailure, UiFailure
from ...domain.repositories import UiRepository
from ...domain.result import Result, err, ok
from ...infrastructure.uiautomator2_factory import UiAutomator2Factory

_BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")


def _bounds_from_string(raw: str | None) -> Bounds:
    if not raw:
        return Bounds(0, 0, 0, 0)
    match = _BOUNDS_RE.search(raw)
    if not match:
        return Bounds(0, 0, 0, 0)
    x1, y1, x2, y2 = (int(g) for g in match.groups())
    return Bounds(x=x1, y=y1, width=max(0, x2 - x1), height=max(0, y2 - y1))


def _element_from_info(info: dict) -> UiElement:
    bounds_field = info.get("bounds") or info.get("visibleBounds")
    if isinstance(bounds_field, dict):
        bounds = Bounds(
            x=int(bounds_field.get("left", 0)),
            y=int(bounds_field.get("top", 0)),
            width=int(bounds_field.get("right", 0)) - int(bounds_field.get("left", 0)),
            height=int(bounds_field.get("bottom", 0)) - int(bounds_field.get("top", 0)),
        )
    else:
        bounds = _bounds_from_string(bounds_field if isinstance(bounds_field, str) else None)
    return UiElement(
        text=info.get("text") or None,
        resource_id=info.get("resourceName") or None,
        class_name=info.get("className") or None,
        content_description=info.get("contentDescription") or None,
        bounds=bounds,
        enabled=bool(info.get("enabled", True)),
        clickable=bool(info.get("clickable", False)),
    )


class UiAutomator2UiRepository(UiRepository):
    def __init__(self, factory: UiAutomator2Factory) -> None:
        self._factory = factory

    async def _device(self, serial: str):
        return await self._factory.get(serial)

    async def tap(self, serial: str, x: int, y: int) -> Result[None]:
        try:
            d = await self._device(serial)
            await asyncio.to_thread(d.click, x, y)
            return ok(None)
        except Exception as e:
            return err(UiFailure(message=f"tap failed: {e}"))

    async def tap_text(self, serial: str, text: str, exact: bool = False) -> Result[None]:
        try:
            d = await self._device(serial)
            selector = d(text=text) if exact else d(textContains=text)
            exists = await asyncio.to_thread(lambda: selector.exists)
            if not exists:
                return err(UiElementNotFoundFailure(message=f"Text not found: {text!r}"))
            await asyncio.to_thread(selector.click)
            return ok(None)
        except Exception as e:
            return err(UiFailure(message=f"tap_text failed: {e}"))

    async def swipe(
        self, serial: str, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300
    ) -> Result[None]:
        try:
            d = await self._device(serial)
            await asyncio.to_thread(d.swipe, x1, y1, x2, y2, duration_ms / 1000.0)
            return ok(None)
        except Exception as e:
            return err(UiFailure(message=f"swipe failed: {e}"))

    async def type_text(self, serial: str, text: str) -> Result[None]:
        try:
            d = await self._device(serial)
            await asyncio.to_thread(d.send_keys, text)
            return ok(None)
        except Exception as e:
            return err(UiFailure(message=f"type_text failed: {e}"))

    async def press_key(self, serial: str, keycode: str) -> Result[None]:
        try:
            d = await self._device(serial)
            await asyncio.to_thread(d.press, keycode.lower())
            return ok(None)
        except Exception as e:
            return err(UiFailure(message=f"press_key failed: {e}"))

    async def find(
        self,
        serial: str,
        text: str | None = None,
        resource_id: str | None = None,
        class_name: str | None = None,
        timeout_s: float = 5.0,
    ) -> Result[UiElement | None]:
        try:
            d = await self._device(serial)
            kwargs: dict = {}
            if text is not None:
                kwargs["text"] = text
            if resource_id is not None:
                kwargs["resourceId"] = resource_id
            if class_name is not None:
                kwargs["className"] = class_name
            if not kwargs:
                return err(UiFailure(message="find requires at least one selector"))
            selector = d(**kwargs)
            exists = await asyncio.to_thread(selector.wait, timeout_s)
            if not exists:
                return ok(None)
            # `selector.info` is a property in uiautomator2 v3+, so wrap in a
            # lambda to defer evaluation onto the worker thread.
            info = await asyncio.to_thread(lambda: selector.info)
            return ok(_element_from_info(info))
        except Exception as e:
            return err(UiFailure(message=f"find failed: {e}"))

    async def wait_for(
        self,
        serial: str,
        text: str | None = None,
        resource_id: str | None = None,
        timeout_s: float = 10.0,
    ) -> Result[UiElement]:
        find_res = await self.find(
            serial, text=text, resource_id=resource_id, timeout_s=timeout_s
        )
        if find_res.is_err:
            return find_res  # type: ignore[return-value]
        if find_res.value is None:  # type: ignore[union-attr]
            return err(
                TimeoutFailure(
                    message="wait_for timed out",
                    details={"text": text, "resource_id": resource_id, "timeout_s": timeout_s},
                )
            )
        return ok(find_res.value)  # type: ignore[union-attr]

    async def dump_ui(self, serial: str) -> Result[str]:
        try:
            d = await self._device(serial)
            xml = await asyncio.to_thread(d.dump_hierarchy)
            return ok(xml)
        except Exception as e:
            return err(UiFailure(message=f"dump_ui failed: {e}"))

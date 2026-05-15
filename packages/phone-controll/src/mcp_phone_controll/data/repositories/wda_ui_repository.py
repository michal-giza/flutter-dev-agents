"""UiRepository implementation backed by facebook-wda (WebDriverAgent)."""

from __future__ import annotations

import asyncio

from ...domain.entities import Bounds, UiElement
from ...domain.failures import TimeoutFailure, UiElementNotFoundFailure, UiFailure
from ...domain.repositories import UiRepository
from ...domain.result import Result, err, ok
from ...infrastructure.wda_factory import WdaFactory, WdaUnreachable


def _bounds_from_rect(rect: dict | None) -> Bounds:
    if not rect:
        return Bounds(0, 0, 0, 0)
    return Bounds(
        x=int(rect.get("x", 0)),
        y=int(rect.get("y", 0)),
        width=int(rect.get("width", 0)),
        height=int(rect.get("height", 0)),
    )


def _element_from_wda(elem) -> UiElement:
    info = elem.info if hasattr(elem, "info") else {}
    return UiElement(
        text=info.get("label") or info.get("value") or info.get("name"),
        resource_id=info.get("name"),
        class_name=info.get("type"),
        content_description=info.get("label"),
        bounds=_bounds_from_rect(info.get("rect")),
        enabled=bool(info.get("enabled", True)),
        clickable=True,
    )


class _WdaUnreachableSentinel(Exception):
    """Wraps `WdaUnreachable` so the action wrappers below can recognise it
    distinctly from a generic exception. Carries the original for structured
    error reporting."""

    def __init__(self, original: WdaUnreachable) -> None:
        super().__init__(str(original))
        self.original = original


def _wda_unreachable_err(e: _WdaUnreachableSentinel, action: str) -> Result[None]:
    """Build a structured Err for the `WdaUnreachable` case so every action
    surfaces the same `next_action` + `fix_command` to the agent. Replaces
    the historical NoneType-attribute crash with something an autonomous
    agent can actually switch on."""
    orig = e.original
    return err(
        UiFailure(
            message=f"{action} failed: {orig}",
            next_action=orig.next_action,
            details={"fix_command": orig.fix_command},
        )
    )


class WdaUiRepository(UiRepository):
    """iOS UI driver. Requires WebDriverAgent built and installed on the device."""

    def __init__(self, factory: WdaFactory) -> None:
        self._factory = factory

    async def _session(self, serial: str):
        try:
            return await self._factory.get(serial)
        except WdaUnreachable as e:
            # Translate the typed transport error to a structured failure
            # so agents see `next_action: "start_wda_on_simulator"` instead
            # of the historical NoneType crash. Raised back as a sentinel
            # exception so every action wrapper below catches uniformly.
            raise _WdaUnreachableSentinel(e) from e

    async def tap(self, serial: str, x: int, y: int) -> Result[None]:
        try:
            s = await self._session(serial)
            await asyncio.to_thread(s.tap, x, y)
            return ok(None)
        except _WdaUnreachableSentinel as e:
            return _wda_unreachable_err(e, "tap")
        except Exception as e:
            return err(UiFailure(message=f"tap failed: {e}"))

    async def tap_text(self, serial: str, text: str, exact: bool = False) -> Result[None]:
        try:
            s = await self._session(serial)
            elem = s(label=text) if exact else s(labelContains=text)
            exists = await asyncio.to_thread(lambda: elem.exists)
            if not exists:
                return err(UiElementNotFoundFailure(message=f"label not found: {text!r}"))
            await asyncio.to_thread(elem.tap)
            return ok(None)
        except _WdaUnreachableSentinel as e:
            return _wda_unreachable_err(e, "tap_text")
        except Exception as e:
            return err(UiFailure(message=f"tap_text failed: {e}"))

    async def swipe(
        self, serial: str, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300
    ) -> Result[None]:
        try:
            s = await self._session(serial)
            await asyncio.to_thread(s.swipe, x1, y1, x2, y2, duration_ms / 1000.0)
            return ok(None)
        except _WdaUnreachableSentinel as e:
            return _wda_unreachable_err(e, "swipe")
        except Exception as e:
            return err(UiFailure(message=f"swipe failed: {e}"))

    async def type_text(self, serial: str, text: str) -> Result[None]:
        try:
            s = await self._session(serial)
            await asyncio.to_thread(s.send_keys, text)
            return ok(None)
        except _WdaUnreachableSentinel as e:
            return _wda_unreachable_err(e, "type_text")
        except Exception as e:
            return err(UiFailure(message=f"type_text failed: {e}"))

    async def press_key(self, serial: str, keycode: str) -> Result[None]:
        try:
            s = await self._session(serial)
            mapping = {"home": "home", "volumeup": "volumeUp", "volumedown": "volumeDown"}
            key = mapping.get(keycode.lower(), keycode.lower())
            await asyncio.to_thread(s.press, key)
            return ok(None)
        except _WdaUnreachableSentinel as e:
            return _wda_unreachable_err(e, "press_key")
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
            s = await self._session(serial)
            kwargs: dict = {}
            if text is not None:
                kwargs["labelContains"] = text
            if resource_id is not None:
                kwargs["name"] = resource_id
            if class_name is not None:
                kwargs["className"] = class_name
            if not kwargs:
                return err(UiFailure(message="find requires at least one selector"))
            elem = s(**kwargs)
            exists = await asyncio.to_thread(elem.wait, timeout_s)
            if not exists:
                return ok(None)
            return ok(_element_from_wda(elem))
        except _WdaUnreachableSentinel as e:
            return _wda_unreachable_err(e, "find")
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
            s = await self._session(serial)
            xml = await asyncio.to_thread(lambda: s.source(format="xml"))
            return ok(str(xml))
        except _WdaUnreachableSentinel as e:
            return _wda_unreachable_err(e, "dump_ui")
        except Exception as e:
            return err(UiFailure(message=f"dump_ui failed: {e}"))

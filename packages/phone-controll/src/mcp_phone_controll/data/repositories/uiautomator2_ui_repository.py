"""UiRepository implementation backed by uiautomator2.

Two real-user bug-driven hardening passes baked into this file:

1. **Polish-character `tap_text` failure** (and any non-ASCII text with
   diacritics): `tap_text("Rozumiem")` or `tap_text("Podczas używania
   aplikacji")` was failing because uiautomator2's selector matcher
   does byte-equality, not Unicode-normalised equality. Python's
   `unicodedata.normalize("NFC", s)` produces canonical composition;
   Android UI text is almost always NFC at source, but user-supplied
   strings often arrive as NFD (e.g. when copied from a font that
   uses combining accents). Fix: NFC-normalise the input, try the
   selector, fall back to a UI-dump scan + Python-side regex match
   + coordinate tap if that fails.

2. **Galaxy S25 / Samsung One UI `tap(x,y)` occasionally drops the
   tap**: uiautomator2 injects taps via the on-device Accessibility
   service, which on Samsung One UI sometimes loses the event to
   edge-swipe gesture overlays or Bixby intercepts. `adb shell input
   tap X Y` bypasses Accessibility entirely and goes through the
   kernel input layer — reliable on Samsung. Fix: tap via adb when
   `MCP_ANDROID_PREFER_ADB_TAP=1` OR when the device manufacturer is
   Samsung. Fall back automatically if uiautomator2 raises.
"""

from __future__ import annotations

import asyncio
import os
import re
import unicodedata

from ...domain.entities import Bounds, UiElement
from ...domain.failures import TimeoutFailure, UiElementNotFoundFailure, UiFailure
from ...domain.repositories import UiRepository
from ...domain.result import Result, err, ok
from ...infrastructure.adb_client import AdbClient
from ...infrastructure.uiautomator2_factory import UiAutomator2Factory
from ...observability import emit

_BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")


def _normalise(text: str) -> str:
    """NFC-normalise + strip — canonical composition matches what
    Android stores in node text. Stripping is defensive: agents
    occasionally pass `"Rozumiem "` with a trailing space."""
    return unicodedata.normalize("NFC", text).strip()


def _prefer_adb_tap_via_env() -> bool:
    val = os.environ.get("MCP_ANDROID_PREFER_ADB_TAP", "").strip().lower()
    return val in ("1", "true", "yes", "on")


def _bounds_from_string(raw: str | None) -> Bounds:
    if not raw:
        return Bounds(0, 0, 0, 0)
    match = _BOUNDS_RE.search(raw)
    if not match:
        return Bounds(0, 0, 0, 0)
    x1, y1, x2, y2 = (int(g) for g in match.groups())
    return Bounds(x=x1, y=y1, width=max(0, x2 - x1), height=max(0, y2 - y1))


def _find_bounds_for_text(
    xml: str, target: str, exact: bool = False
) -> Bounds | None:
    """Scan a uiautomator XML dump for a node whose `text` or
    `content-desc` matches `target` after NFC normalisation.

    Heuristic but bounded: parses attribute pairs via regex so we
    don't add an XML-library dep. Returns the bounds of the FIRST
    match (closest to the top of the tree usually = the visible
    one). None if nothing matches — caller surfaces the structured
    UiElementNotFoundFailure.

    The fallback path tap_text uses when uiautomator2's selector
    machinery loses to encoding edge cases on diacritics.
    """
    target = _normalise(target)
    if not target:
        return None
    # The XML attribute order on Android is stable enough that
    # `text="...."` and `content-desc="..."` are easy to extract.
    # Same for bounds="[x1,y1][x2,y2]". We scan node-by-node.
    node_re = re.compile(r"<node\s+([^>]+?)\s*/?>")
    text_attr = re.compile(r'\btext="([^"]*)"')
    desc_attr = re.compile(r'\bcontent-desc="([^"]*)"')
    bounds_attr = re.compile(r'\bbounds="(\[[^"]+\])"')

    for match in node_re.finditer(xml):
        attrs = match.group(1)
        candidates: list[str] = []
        if (m := text_attr.search(attrs)) is not None:
            candidates.append(_normalise(m.group(1)))
        if (m := desc_attr.search(attrs)) is not None:
            candidates.append(_normalise(m.group(1)))
        if not candidates:
            continue
        hit = (
            any(c == target for c in candidates)
            if exact
            else any(target in c for c in candidates if c)
        )
        if not hit:
            continue
        bm = bounds_attr.search(attrs)
        if not bm:
            continue
        bounds = _bounds_from_string(bm.group(1))
        if bounds.width <= 0 or bounds.height <= 0:
            continue
        return bounds
    return None


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
    """Android UI driver. Accepts an optional `adb_client` so taps can
    fall back to `adb shell input tap` when the on-device accessibility
    path drops events (Samsung One UI's biggest reliability issue)."""

    def __init__(
        self,
        factory: UiAutomator2Factory,
        adb_client: AdbClient | None = None,
    ) -> None:
        self._factory = factory
        self._adb = adb_client
        # Cache the per-serial manufacturer lookup — `getprop` is cheap
        # but we'd otherwise call it on every tap. Cleared by
        # `release_device` / `select_device` at the session boundary.
        self._manufacturer_cache: dict[str, str] = {}

    async def _device(self, serial: str):
        return await self._factory.get(serial)

    async def _manufacturer(self, serial: str) -> str:
        """Return the device's `ro.product.manufacturer` (lowercase),
        cached. Empty string if adb client isn't available — falls
        back to "no preference" so the auto-prefer-adb policy never
        kicks in unexpectedly."""
        if self._adb is None:
            return ""
        if serial in self._manufacturer_cache:
            return self._manufacturer_cache[serial]
        try:
            res = await self._adb.get_prop(serial, "ro.product.manufacturer")
            value = (res.stdout or "").strip().lower() if res.ok else ""
        except Exception:
            value = ""
        self._manufacturer_cache[serial] = value
        return value

    async def _should_prefer_adb_tap(self, serial: str) -> bool:
        """True when env opts in OR the device is a known
        accessibility-flaky manufacturer. Today only Samsung is listed;
        extend the set if other vendors show similar issues."""
        if _prefer_adb_tap_via_env():
            return True
        mfr = await self._manufacturer(serial)
        return mfr == "samsung"

    async def _tap_via_adb(self, serial: str, x: int, y: int) -> bool:
        """Direct adb-input-injection tap. Returns True on success.
        Goes through the kernel input layer, bypassing Accessibility —
        which is exactly why it works on Samsung when uiautomator2
        doesn't."""
        if self._adb is None:
            return False
        try:
            res = await self._adb.shell(serial, "input", "tap", str(x), str(y))
            return res.ok
        except Exception:
            return False

    async def tap(self, serial: str, x: int, y: int) -> Result[None]:
        # Two-step: prefer adb when policy says so; otherwise try
        # uiautomator2 first and fall back to adb on exception. Log
        # which path won via observability.emit so production drift is
        # diagnosable.
        prefer_adb = await self._should_prefer_adb_tap(serial)
        if (
            prefer_adb
            and self._adb is not None
            and await self._tap_via_adb(serial, x, y)
        ):
            emit("tap_via_adb", level="info", serial=serial, x=x, y=y, reason="preferred")
            return ok(None)
            # If preferred-adb failed (e.g. no adb on PATH), still
            # try uiautomator2 below — better than nothing.

        try:
            d = await self._device(serial)
            await asyncio.to_thread(d.click, x, y)
            emit("tap_via_uiautomator2", level="info", serial=serial, x=x, y=y)
            return ok(None)
        except Exception as e:
            # uiautomator2 raised. If adb is available, try it as a
            # second-chance. This is the One UI workaround in the
            # field — agents reported the failure pattern explicitly.
            if self._adb is not None and await self._tap_via_adb(serial, x, y):
                emit(
                    "tap_via_adb",
                    level="warn",
                    serial=serial,
                    x=x, y=y,
                    reason=f"u2_failed: {type(e).__name__}",
                )
                return ok(None)
            return err(UiFailure(message=f"tap failed: {e}"))

    async def tap_text(self, serial: str, text: str, exact: bool = False) -> Result[None]:
        # NFC-normalise the input so Polish (or any) diacritics match
        # what's stored in the UI tree. uiautomator2 does byte-eq
        # comparison; we cannot rely on it normalising for us.
        original = text
        normalised = _normalise(text)
        try:
            d = await self._device(serial)
            # First attempt: the standard uiautomator2 selector path
            # with NFC text.
            selector = (
                d(text=normalised) if exact else d(textContains=normalised)
            )
            exists = await asyncio.to_thread(lambda: selector.exists)
            if exists:
                await asyncio.to_thread(selector.click)
                emit(
                    "tap_text_via_selector",
                    level="info",
                    serial=serial,
                    text=normalised[:60],
                    normalised=(normalised != original),
                )
                return ok(None)

            # Fallback: dump the UI tree, find the node whose `text` or
            # `content-desc` attribute matches `normalised` under NFC,
            # extract its bounds, tap by coordinates. Works for the
            # cases where uiautomator2's selector machinery loses to
            # encoding edge cases (NFD on the device side, font
            # rendering with combining chars, etc.).
            xml = await asyncio.to_thread(d.dump_hierarchy)
            bounds = _find_bounds_for_text(xml, normalised, exact=exact)
            if bounds is None:
                return err(
                    UiElementNotFoundFailure(
                        message=f"Text not found via selector or UI scan: {original!r}",
                        next_action="check_text_or_use_dump_ui",
                        details={
                            "requested": original,
                            "normalised": normalised,
                            "exact": exact,
                        },
                    )
                )
            cx = bounds.x + bounds.width // 2
            cy = bounds.y + bounds.height // 2
            emit(
                "tap_text_via_dump_ui_fallback",
                level="info",
                serial=serial,
                text=normalised[:60],
                cx=cx, cy=cy,
            )
            # Use the same tap() entry-point so Samsung's adb-fallback
            # policy still applies here.
            return await self.tap(serial, cx, cy)
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

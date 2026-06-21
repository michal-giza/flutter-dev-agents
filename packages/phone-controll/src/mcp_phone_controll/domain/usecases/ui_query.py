"""UI query use cases — find, wait, dump, assert."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ..entities import UiElement
from ..failures import UiElementNotFoundFailure
from ..repositories import ArtifactRepository, SessionStateRepository, UiRepository
from ..result import Err, Result, err, ok
from ._helpers import resolve_serial
from .base import BaseUseCase

# When the hierarchy XML exceeds this, the inline copy would be truncated
# by the output-truncation middleware (~8 KB cap). So we ALSO spill the
# full XML to an artifact and return its path — making the truncation's
# "fetch the full artifact" next_action actually actionable. (Matches
# output_truncation.DEFAULT_MAX_STRING_BYTES; kept as a local constant to
# avoid a domain→presentation import.)
_DUMP_SPILL_THRESHOLD_BYTES = 8_000


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


@dataclass(frozen=True, slots=True)
class DumpUiResult:
    xml: str               # full tree; the output middleware truncates the
                           # INLINE copy when large — the artifact has it whole
    byte_size: int         # full size, so the agent can decide how to consume it
    node_count: int        # quick structural size signal (count of <node/<XCUI)
    artifact_path: str | None  # full XML on disk when large; fetch via fetch_artifact
    advice: str


class DumpUi(BaseUseCase[DumpUiParams, DumpUiResult]):
    """Dump the UI hierarchy. When the tree is large, the inline XML is
    capped by the output middleware — so we also spill the FULL XML to an
    artifact and return its path, and point the agent at the server-side
    full-tree searchers (`find_element` / `extract_ui_graph`) which never
    truncate. Fixes the "dump_ui truncates at ~56 KB and there's no
    fetch-full follow-through" dead-end."""

    def __init__(
        self,
        ui: UiRepository,
        state: SessionStateRepository,
        artifacts: ArtifactRepository | None = None,
    ) -> None:
        self._ui = ui
        self._state = state
        self._artifacts = artifacts

    async def execute(self, params: DumpUiParams) -> Result[DumpUiResult]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        dump_res = await self._ui.dump_ui(serial_res.value)
        if isinstance(dump_res, Err):
            return dump_res
        xml = dump_res.value or ""
        byte_size = len(xml.encode("utf-8", errors="replace"))
        node_count = xml.count("<node") + xml.count("<XCUIElement")

        artifact_path: str | None = None
        if byte_size > _DUMP_SPILL_THRESHOLD_BYTES and self._artifacts is not None:
            artifact_path = await self._spill(xml)

        if byte_size <= _DUMP_SPILL_THRESHOLD_BYTES:
            advice = f"{node_count} nodes, {byte_size} bytes — full tree inline."
        elif artifact_path is not None:
            advice = (
                f"{node_count} nodes, {byte_size} bytes — inline XML is "
                f"truncated; full tree at {artifact_path} (fetch_artifact). "
                "To target an element, prefer find_element / extract_ui_graph "
                "(they search the full tree server-side, no truncation)."
            )
        else:
            advice = (
                f"{node_count} nodes, {byte_size} bytes — inline XML is "
                "truncated and no artifact session is active. Use "
                "find_element / extract_ui_graph to search the full tree "
                "server-side, or new_session first to capture the full dump."
            )
        return ok(
            DumpUiResult(
                xml=xml,
                byte_size=byte_size,
                node_count=node_count,
                artifact_path=artifact_path,
                advice=advice,
            )
        )

    async def _spill(self, xml: str) -> str | None:
        """Write the full XML to an artifact; return its path (None on
        failure — a spill failure must never fail the dump itself)."""
        try:
            path_res = await self._artifacts.allocate_path("uidump", ".xml")
            if isinstance(path_res, Err):
                return None
            path = path_res.value
            await asyncio.to_thread(path.write_text, xml, encoding="utf-8")
            return str(path)
        except Exception:
            return None


@dataclass(frozen=True, slots=True)
class WaitUntilParams:
    text: str | None = None
    resource_id: str | None = None
    # gone=False → block until the element is VISIBLE; gone=True → block
    # until it's ABSENT (the new capability: wait for a spinner / dialog /
    # overlay to disappear, which previously forced an agent poll-loop).
    gone: bool = False
    timeout_s: float = 10.0
    poll_interval_s: float = 0.5
    serial: str | None = None


@dataclass(frozen=True, slots=True)
class WaitUntilResult:
    condition: str       # "visible" | "gone"
    met: bool            # always True on Ok (timeout returns Err)
    waited_s: float
    element: UiElement | None  # the element, when waiting for visible


class WaitUntil(BaseUseCase[WaitUntilParams, WaitUntilResult]):
    """Block server-side until a UI condition holds — one call instead of
    an agent poll-loop (each poll was a round-trip). `gone=True` waits for
    an element to DISAPPEAR (spinner/dialog/overlay); `gone=False` waits
    for it to appear. Times out into a structured TimeoutFailure."""

    def __init__(self, ui: UiRepository, state: SessionStateRepository) -> None:
        self._ui = ui
        self._state = state

    async def execute(self, params: WaitUntilParams) -> Result[WaitUntilResult]:
        import asyncio
        import time

        if params.text is None and params.resource_id is None:
            from ..failures import InvalidArgumentFailure

            return err(
                InvalidArgumentFailure(
                    message="wait_until needs `text` or `resource_id`.",
                    next_action="fix_arguments",
                )
            )
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        serial = serial_res.value
        condition = "gone" if params.gone else "visible"
        poll = max(0.05, params.poll_interval_s)
        start = time.monotonic()
        deadline = start + max(0.0, params.timeout_s)

        while True:
            find_res = await self._ui.find(
                serial,
                text=params.text,
                resource_id=params.resource_id,
                timeout_s=poll,
            )
            if isinstance(find_res, Err):
                return find_res
            present = find_res.value is not None
            waited = round(time.monotonic() - start, 2)
            if params.gone and not present:
                return ok(WaitUntilResult("gone", True, waited, None))
            if not params.gone and present:
                return ok(WaitUntilResult("visible", True, waited, find_res.value))
            if time.monotonic() >= deadline:
                from ..failures import TimeoutFailure

                return err(
                    TimeoutFailure(
                        message=(
                            f"condition '{condition}' not met within "
                            f"{params.timeout_s}s"
                        ),
                        next_action="capture_diagnostics",
                        details={
                            "condition": condition,
                            "text": params.text,
                            "resource_id": params.resource_id,
                            "waited_s": waited,
                        },
                    )
                )
            await asyncio.sleep(poll)


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

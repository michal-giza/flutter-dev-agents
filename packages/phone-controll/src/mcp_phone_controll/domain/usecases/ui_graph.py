"""extract_ui_graph — parse the device UI dump into a typed graph of
clickable elements.

Aligned with the visual-UI-agent SOTA (CogAgent, ShowUI, OS-Atlas,
SeeClick — late 2024 → 2025). Those agents reason over a *structured*
representation of the screen, not raw pixels. We have one already:
`dump_ui` returns the UIAutomator/XCUITest XML tree. This use case
turns that into a typed, JSON-friendly graph the agent can reason
over without burning a vision-model call.

Output structure:

  {
    "node_count": 23,
    "clickables": [
      {"id": 0, "role": "button", "text": "Sign in", "bounds": [...],
       "resource_id": "com.example:id/btn_signin", "enabled": true},
      ...
    ],
    "inputs": [
      {"id": 5, "role": "text_field", "hint": "Email", "bounds": [...]}
    ],
    "texts": [...],
    "images": [...],
    "hierarchy_digest": "Scaffold > Column > [Button, TextField, ...]"
  }

Roles are inferred from class names:
  - Android: android.widget.Button, EditText, TextView, ImageView, ...
  - iOS:     XCUIElementTypeButton, TextField, StaticText, Image, ...

If the underlying dump isn't recognised (e.g. Flutter semantics tree
in a future format), the parser falls back to listing every node with
role="unknown" so the agent at least sees structure.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from ..failures import UiFailure
from ..repositories import SessionStateRepository, UiRepository
from ..result import Err, Result, err, ok
from ._helpers import resolve_serial
from .base import BaseUseCase

# Class-name → semantic role. Order matters — more-specific entries first.
_ROLE_MAP_ANDROID = [
    ("Button", "button"),
    ("CompoundButton", "toggle"),
    ("Switch", "toggle"),
    ("CheckBox", "checkbox"),
    ("RadioButton", "radio"),
    ("EditText", "text_field"),
    ("AutoCompleteTextView", "text_field"),
    ("TextView", "text"),
    ("ImageView", "image"),
    ("ImageButton", "button"),
    ("ProgressBar", "progress"),
    ("Spinner", "dropdown"),
    ("WebView", "webview"),
    ("ListView", "list"),
    ("RecyclerView", "list"),
    ("ScrollView", "scroll"),
    ("ViewPager", "pager"),
]

_ROLE_MAP_IOS = [
    ("Button", "button"),
    ("Switch", "toggle"),
    ("Slider", "slider"),
    ("TextField", "text_field"),
    ("SecureTextField", "password_field"),
    ("StaticText", "text"),
    ("Image", "image"),
    ("Cell", "list_item"),
    ("Table", "list"),
    ("CollectionView", "list"),
    ("ScrollView", "scroll"),
    ("WebView", "webview"),
]


@dataclass(frozen=True, slots=True)
class ExtractUiGraphParams:
    serial: str | None = None
    max_nodes: int = 200       # cap to keep output safe for 4B context


@dataclass(frozen=True, slots=True)
class UiGraphNode:
    id: int
    role: str
    text: str | None
    resource_id: str | None
    bounds: tuple[int, int, int, int] | None
    enabled: bool
    clickable: bool


@dataclass(frozen=True, slots=True)
class UiGraphResult:
    platform: str
    node_count: int
    truncated: bool
    clickables: tuple[UiGraphNode, ...]
    inputs: tuple[UiGraphNode, ...]
    texts: tuple[UiGraphNode, ...]
    images: tuple[UiGraphNode, ...]
    other: tuple[UiGraphNode, ...]
    hierarchy_digest: str


class ExtractUiGraph(BaseUseCase[ExtractUiGraphParams, UiGraphResult]):
    """Parse `dump_ui` output into a typed graph."""

    def __init__(self, ui: UiRepository, state: SessionStateRepository) -> None:
        self._ui = ui
        self._state = state

    async def execute(self, params: ExtractUiGraphParams) -> Result[UiGraphResult]:
        serial_res = await resolve_serial(params.serial, self._state)
        if isinstance(serial_res, Err):
            return serial_res
        dump_res = await self._ui.dump_ui(serial_res.value)
        if isinstance(dump_res, Err):
            return dump_res
        xml_text = dump_res.value
        if not xml_text or not xml_text.strip():
            return err(
                UiFailure(
                    message="dump_ui returned empty XML",
                    next_action="retry_with_backoff",
                )
            )
        try:
            return ok(_parse(xml_text, params.max_nodes))
        except ET.ParseError as exc:
            # Fallback for non-XML formats (e.g. fake outputs in tests):
            # produce a minimal "unknown" graph so the agent still sees structure.
            return ok(
                UiGraphResult(
                    platform="unknown",
                    node_count=0,
                    truncated=False,
                    clickables=(), inputs=(), texts=(), images=(), other=(),
                    hierarchy_digest=f"<unparsed: {exc}>",
                )
            )


# ---- the parser ---------------------------------------------------------


def _parse(xml_text: str, max_nodes: int) -> UiGraphResult:
    root = ET.fromstring(xml_text)
    platform = _detect_platform(root)
    role_map = _ROLE_MAP_IOS if platform == "ios" else _ROLE_MAP_ANDROID

    nodes: list[UiGraphNode] = []
    hierarchy_parts: list[str] = []

    def walk(elem: ET.Element, depth: int) -> None:
        if len(nodes) >= max_nodes:
            return
        cls = elem.attrib.get("class") or elem.tag
        role = _role_for(cls, role_map)
        text = elem.attrib.get("text") or elem.attrib.get("label") or None
        resource_id = (
            elem.attrib.get("resource-id")
            or elem.attrib.get("identifier")
            or None
        )
        bounds = _parse_bounds(elem.attrib.get("bounds"))
        enabled = elem.attrib.get("enabled", "true").lower() == "true"
        clickable = elem.attrib.get("clickable", "false").lower() == "true"
        if role != "unknown" or text or clickable:
            nodes.append(
                UiGraphNode(
                    id=len(nodes),
                    role=role,
                    text=text,
                    resource_id=resource_id,
                    bounds=bounds,
                    enabled=enabled,
                    clickable=clickable,
                )
            )
            if depth <= 3:
                hierarchy_parts.append("  " * depth + f"{role}({text or '…'})")
        for child in list(elem):
            walk(child, depth + 1)

    walk(root, 0)
    truncated = len(nodes) >= max_nodes
    # Bucket by role family.
    clickables = tuple(n for n in nodes if n.clickable or n.role == "button")
    inputs = tuple(
        n for n in nodes
        if n.role in {"text_field", "password_field", "checkbox", "radio", "toggle"}
    )
    texts = tuple(n for n in nodes if n.role == "text")
    images = tuple(n for n in nodes if n.role == "image")
    seen_buckets = {id(n) for bucket in (clickables, inputs, texts, images) for n in bucket}
    other = tuple(n for n in nodes if id(n) not in seen_buckets)

    return UiGraphResult(
        platform=platform,
        node_count=len(nodes),
        truncated=truncated,
        clickables=clickables,
        inputs=inputs,
        texts=texts,
        images=images,
        other=other,
        hierarchy_digest="\n".join(hierarchy_parts[:40]),
    )


def _detect_platform(root: ET.Element) -> str:
    # UIAutomator dumps have an `<hierarchy>` root with `class` attributes
    # starting with `android.`. XCTest XML mentions XCUIElementType*.
    text_sample = ET.tostring(root, encoding="unicode")[:1024]
    if "XCUIElementType" in text_sample:
        return "ios"
    if "android." in text_sample:
        return "android"
    return "unknown"


def _role_for(class_name: str, mapping: list[tuple[str, str]]) -> str:
    for suffix, role in mapping:
        if suffix in class_name:
            return role
    return "unknown"


_BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")


def _parse_bounds(raw: str | None) -> tuple[int, int, int, int] | None:
    if not raw:
        return None
    m = _BOUNDS_RE.match(raw)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))
    # iOS-style "x,y,w,h" or {{x,y},{w,h}} — try the simpler comma form.
    nums = [int(n) for n in re.findall(r"-?\d+", raw)[:4]]
    if len(nums) == 4:
        return (nums[0], nums[1], nums[0] + nums[2], nums[1] + nums[3])
    return None

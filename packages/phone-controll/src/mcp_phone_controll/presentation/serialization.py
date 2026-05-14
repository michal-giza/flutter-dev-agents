"""Domain entity → JSON-serialisable dict. The MCP layer's only contact with entities."""

from __future__ import annotations

from dataclasses import is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from ..domain.entities import (
    AppBundle,
    Artifact,
    Bounds,
    Device,
    LogEntry,
    Session,
    TestCase,
    TestRun,
    UiElement,
)


def to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if is_dataclass(value):
        return {f: to_jsonable(getattr(value, f)) for f in _dataclass_fields(value)}
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _dataclass_fields(value: Any) -> list[str]:
    if hasattr(value, "__dataclass_fields__"):
        return list(value.__dataclass_fields__.keys())
    return []


# Convenience aliases — every public entity goes through to_jsonable.
serialize_device = to_jsonable
serialize_bundle = to_jsonable
serialize_bounds = to_jsonable
serialize_ui_element = to_jsonable
serialize_log_entry = to_jsonable
serialize_test_run = to_jsonable
serialize_test_case = to_jsonable
serialize_artifact = to_jsonable
serialize_session = to_jsonable

__all__ = [
    "AppBundle",
    "Artifact",
    "Bounds",
    "Device",
    "LogEntry",
    "Session",
    "TestCase",
    "TestRun",
    "UiElement",
    "serialize_artifact",
    "serialize_bounds",
    "serialize_bundle",
    "serialize_device",
    "serialize_log_entry",
    "serialize_session",
    "serialize_test_case",
    "serialize_test_run",
    "serialize_ui_element",
    "to_jsonable",
]

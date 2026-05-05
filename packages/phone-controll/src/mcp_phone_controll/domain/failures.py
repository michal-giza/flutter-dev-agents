"""Failure hierarchy — typed errors returned by repositories and use cases.

Every Failure carries a canonical `next_action` hint that an autonomous agent
can switch on without parsing the message. Examples:
- "run_check_environment"   — env preflight should fix it
- "ask_user"                — needs human decision
- "retry_with_backoff"      — transient
- "fix_arguments"           — schema/argument problem
- "calibrate_stand"         — AR / vision specific
- "review_diff"             — visual-diff failure with diff path in details
- None                      — unknown / no canonical hint
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Failure:
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    next_action: str | None = None

    @property
    def code(self) -> str:
        return type(self).__name__


@dataclass(frozen=True, slots=True)
class InvalidArgumentFailure(Failure):
    pass


@dataclass(frozen=True, slots=True)
class DeviceNotFoundFailure(Failure):
    pass


@dataclass(frozen=True, slots=True)
class DeviceOfflineFailure(Failure):
    pass


@dataclass(frozen=True, slots=True)
class NoDeviceSelectedFailure(Failure):
    pass


@dataclass(frozen=True, slots=True)
class AdbFailure(Failure):
    pass


@dataclass(frozen=True, slots=True)
class FlutterCliFailure(Failure):
    pass


@dataclass(frozen=True, slots=True)
class BuildFailure(Failure):
    pass


@dataclass(frozen=True, slots=True)
class InstallFailure(Failure):
    pass


@dataclass(frozen=True, slots=True)
class LaunchFailure(Failure):
    pass


@dataclass(frozen=True, slots=True)
class UiFailure(Failure):
    pass


@dataclass(frozen=True, slots=True)
class UiElementNotFoundFailure(Failure):
    pass


@dataclass(frozen=True, slots=True)
class TimeoutFailure(Failure):
    pass


@dataclass(frozen=True, slots=True)
class TestExecutionFailure(Failure):
    pass


@dataclass(frozen=True, slots=True)
class FilesystemFailure(Failure):
    pass


@dataclass(frozen=True, slots=True)
class VisionFailure(Failure):
    """AR / image processing failure (marker not seen, golden mismatch, etc.)."""

    pass


@dataclass(frozen=True, slots=True)
class PlanExecutionFailure(Failure):
    """A YAML plan failed at a specific phase."""

    pass


@dataclass(frozen=True, slots=True)
class DeviceBusyFailure(Failure):
    """Another session holds the lock on the requested device."""

    pass


@dataclass(frozen=True, slots=True)
class LockNotHeldFailure(Failure):
    """This session doesn't hold the lock on this serial."""

    pass


@dataclass(frozen=True, slots=True)
class DebugSessionFailure(Failure):
    """The `flutter run --machine` process failed or returned an error."""

    pass


@dataclass(frozen=True, slots=True)
class HotReloadFailure(Failure):
    """Hot reload / hot restart returned an error from the daemon."""

    pass


@dataclass(frozen=True, slots=True)
class ServiceExtensionFailure(Failure):
    """A `ext.flutter.*` service extension call failed."""

    pass


@dataclass(frozen=True, slots=True)
class IdeNotFoundFailure(Failure):
    """The IDE binary (e.g. `code`) wasn't on PATH and no fallback found it."""

    pass


@dataclass(frozen=True, slots=True)
class IdeWindowNotFoundFailure(Failure):
    """No IDE window matches the requested project_path or window_id."""

    pass


@dataclass(frozen=True, slots=True)
class UnexpectedFailure(Failure):
    pass

"""Repository protocols — the boundary use cases depend on. Implemented in `data/`."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from .entities import (
    AppBundle,
    Artifact,
    BuildMode,
    Device,
    CapabilityReport,
    DeviceLock,
    EnvironmentReport,
    ImageDiff,
    LogEntry,
    LogLevel,
    MarkerDetection,
    PatrolTestFile,
    PlanRun,
    Platform,
    Pose,
    ProjectInfo,
    Session,
    SessionTrace,
    TestPlan,
    TestRun,
    TraceEntry,
    UiElement,
)
from .result import Result


@runtime_checkable
class DeviceRepository(Protocol):
    async def list_devices(self) -> Result[list[Device]]: ...
    async def get_device(self, serial: str) -> Result[Device]: ...


@runtime_checkable
class LifecycleRepository(Protocol):
    async def install(
        self, serial: str, bundle_path: Path, replace: bool = True
    ) -> Result[None]: ...
    async def uninstall(self, serial: str, package_id: str) -> Result[None]: ...
    async def launch(
        self, serial: str, package_id: str, activity: str | None = None
    ) -> Result[None]: ...
    async def stop(self, serial: str, package_id: str) -> Result[None]: ...
    async def clear_data(self, serial: str, package_id: str) -> Result[None]: ...
    async def grant_permission(
        self, serial: str, package_id: str, permission: str
    ) -> Result[None]: ...


@runtime_checkable
class BuildRepository(Protocol):
    async def build_bundle(
        self,
        project_path: Path,
        mode: BuildMode,
        platform: Platform = Platform.ANDROID,
        flavor: str | None = None,
    ) -> Result[AppBundle]: ...


@runtime_checkable
class UiRepository(Protocol):
    async def tap(self, serial: str, x: int, y: int) -> Result[None]: ...
    async def tap_text(self, serial: str, text: str, exact: bool = False) -> Result[None]: ...
    async def swipe(
        self, serial: str, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300
    ) -> Result[None]: ...
    async def type_text(self, serial: str, text: str) -> Result[None]: ...
    async def press_key(self, serial: str, keycode: str) -> Result[None]: ...
    async def find(
        self,
        serial: str,
        text: str | None = None,
        resource_id: str | None = None,
        class_name: str | None = None,
        timeout_s: float = 5.0,
    ) -> Result[UiElement | None]: ...
    async def wait_for(
        self,
        serial: str,
        text: str | None = None,
        resource_id: str | None = None,
        timeout_s: float = 10.0,
    ) -> Result[UiElement]: ...
    async def dump_ui(self, serial: str) -> Result[str]: ...


@runtime_checkable
class ObservationRepository(Protocol):
    async def screenshot(self, serial: str, output_path: Path) -> Result[Path]: ...
    async def start_recording(self, serial: str, output_path: Path) -> Result[None]: ...
    async def stop_recording(self, serial: str) -> Result[Path]: ...
    async def read_logs(
        self,
        serial: str,
        since_s: int = 30,
        tag: str | None = None,
        min_level: LogLevel = LogLevel.WARN,
        max_lines: int = 500,
    ) -> Result[list[LogEntry]]: ...
    async def tail_logs_until(
        self,
        serial: str,
        until_pattern: str,
        tag: str | None = None,
        timeout_s: float = 30.0,
    ) -> Result[list[LogEntry]]: ...


@runtime_checkable
class TestRepository(Protocol):
    async def run_unit_tests(self, project_path: Path) -> Result[TestRun]: ...
    async def run_integration_tests(
        self,
        project_path: Path,
        device_serial: str,
        test_path: str = "integration_test/",
    ) -> Result[TestRun]: ...


@runtime_checkable
class ArtifactRepository(Protocol):
    async def new_session(self, label: str | None = None) -> Result[Session]: ...
    async def current_session(self) -> Result[Session]: ...
    async def allocate_path(
        self, kind: str, suffix: str, label: str | None = None
    ) -> Result[Path]: ...
    async def register(self, artifact: Artifact) -> Result[None]: ...


@runtime_checkable
class SessionStateRepository(Protocol):
    """Holds the currently selected device serial across MCP tool calls."""

    async def set_selected_serial(self, serial: str | None) -> Result[None]: ...
    async def get_selected_serial(self) -> Result[str | None]: ...


@runtime_checkable
class PatrolRepository(Protocol):
    """Patrol-driven Flutter integration test orchestration.

    Patrol replaces raw UI driving for Flutter app screens — tests are written in
    Dart against widget Keys, locale-independent, and run on real devices.
    """

    async def list_tests(self, project_path: Path) -> Result[list[PatrolTestFile]]: ...

    async def run_test(
        self,
        project_path: Path,
        test_path: Path,
        device_serial: str,
        flavor: str | None = None,
        build_mode: BuildMode = BuildMode.DEBUG,
    ) -> Result[TestRun]: ...

    async def run_suite(
        self,
        project_path: Path,
        test_dir: Path,
        device_serial: str,
        flavor: str | None = None,
        build_mode: BuildMode = BuildMode.DEBUG,
    ) -> Result[TestRun]: ...


@runtime_checkable
class EnvironmentRepository(Protocol):
    """Inspects toolchain and device readiness — the 'doctor' surface."""

    async def check(self) -> Result[EnvironmentReport]: ...


@runtime_checkable
class ProjectInspector(Protocol):
    """Detects project type and available test frameworks at a path.

    The composite registry lets us add inspectors for new stacks (RN, native iOS,
    web) without changing any other layer.
    """

    async def inspect(self, project_path: Path) -> Result[ProjectInfo]: ...


@runtime_checkable
class CapabilitiesProvider(Protocol):
    """Returns a structured roll-up of what this MCP can do — for autonomous
    agents to introspect before planning."""

    async def describe(self) -> Result[CapabilityReport]: ...


@runtime_checkable
class SessionTraceRepository(Protocol):
    """Records every dispatcher call so an agent can reflect on its own session."""

    async def record(self, entry: TraceEntry) -> Result[None]: ...
    async def summary(self, session_id: str | None = None) -> Result[SessionTrace]: ...
    async def reset(self) -> Result[None]: ...


@runtime_checkable
class VisionRepository(Protocol):
    """Computer-vision ops for AR / Vision feature regression testing."""

    async def compare(
        self,
        actual_path: Path,
        golden_path: Path,
        tolerance: float = 0.98,
        diff_output_path: Path | None = None,
    ) -> Result[ImageDiff]: ...

    async def detect_markers(
        self, image_path: Path, dictionary: str = "DICT_4X4_50"
    ) -> Result[list[MarkerDetection]]: ...

    async def infer_pose(
        self,
        image_path: Path,
        marker_id: int,
        marker_size_m: float,
        camera_matrix: tuple[tuple[float, ...], ...] | None = None,
    ) -> Result[Pose]: ...


@runtime_checkable
class PlanExecutor(Protocol):
    """Interprets a TestPlan: walks phases, enforces entry/exit, captures artifacts."""

    async def run(self, plan: TestPlan) -> Result[PlanRun]: ...


@runtime_checkable
class DeviceLockRepository(Protocol):
    """Coordinates exclusive access to a device serial across MCP sessions.

    Backed either by the filesystem (cross-process) or by memory (single-process,
    e.g. when the HTTP adapter serves multiple Claude clients).
    """

    async def acquire(
        self, serial: str, session_id: str, force: bool = False, note: str | None = None
    ) -> Result[DeviceLock]: ...
    async def release(self, serial: str, session_id: str) -> Result[None]: ...
    async def list_locks(self) -> Result[list[DeviceLock]]: ...
    async def force_release(self, serial: str) -> Result[None]: ...
    async def lock_for(self, serial: str) -> Result[DeviceLock | None]: ...


@runtime_checkable
class VirtualDeviceManager(Protocol):
    """Lifecycle for emulators / simulators (the host-side virtual-device stack)."""

    async def list_avds(self) -> Result[list[str]]: ...
    async def start_emulator(self, avd_name: str, headless: bool = False) -> Result[str]: ...
    async def stop_virtual_device(self, serial: str) -> Result[None]: ...
    async def list_simulators(self, include_shutdown: bool = True) -> Result[list[Device]]: ...
    async def boot_simulator(self, name_or_udid: str) -> Result[Device]: ...

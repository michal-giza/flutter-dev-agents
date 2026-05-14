"""Repository protocols — the boundary use cases depend on. Implemented in `data/`."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from .entities import (
    AnalyzerReport,
    AppBundle,
    Artifact,
    BuildMode,
    CapabilityReport,
    DebugLogEntry,
    DebugSession,
    Device,
    DeviceLock,
    EnvironmentReport,
    FixReport,
    FormatReport,
    IdeKind,
    IdeWindow,
    ImageDiff,
    IndexStats,
    LogEntry,
    LogLevel,
    MarkerDetection,
    PatrolTestFile,
    PlanRun,
    Platform,
    Pose,
    ProjectInfo,
    PubOutdatedEntry,
    RecallChunk,
    ServiceExtensionResult,
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


@runtime_checkable
class DebugSessionRepository(Protocol):
    """Long-lived `flutter run --machine` sessions, one per (project, device).

    Sessions are owned by the MCP process that started them; the device-lock
    layer prevents two sessions thrashing the same phone.
    """

    async def start(
        self,
        project_path: Path,
        device_serial: str,
        mode: BuildMode = BuildMode.DEBUG,
        flavor: str | None = None,
        target: str | None = None,
    ) -> Result[DebugSession]: ...
    async def stop(self, session_id: str | None = None) -> Result[None]: ...
    async def restart(
        self, session_id: str | None = None, full_restart: bool = False
    ) -> Result[DebugSession]: ...
    async def attach(
        self, vm_service_uri: str, project_path: Path
    ) -> Result[DebugSession]: ...
    async def list_sessions(self) -> Result[list[DebugSession]]: ...
    async def read_log(
        self,
        session_id: str | None = None,
        since_s: int = 30,
        level: str = "all",
        max_lines: int = 500,
    ) -> Result[list[DebugLogEntry]]: ...
    async def tail_log(
        self,
        session_id: str | None,
        until_pattern: str,
        timeout_s: float = 30.0,
    ) -> Result[list[DebugLogEntry]]: ...
    async def call_service_extension(
        self,
        session_id: str | None,
        method: str,
        args: dict | None = None,
    ) -> Result[ServiceExtensionResult]: ...


@runtime_checkable
class CodeQualityRepository(Protocol):
    """Static analysis, formatting, automated fixes, dependency hygiene."""

    async def analyze(self, project_path: Path) -> Result[AnalyzerReport]: ...
    async def format(
        self, target_path: Path, dry_run: bool = False
    ) -> Result[FormatReport]: ...
    async def fix(
        self, project_path: Path, apply: bool = False
    ) -> Result[FixReport]: ...
    async def pub_get(self, project_path: Path) -> Result[None]: ...
    async def pub_outdated(
        self, project_path: Path
    ) -> Result[list[PubOutdatedEntry]]: ...


@runtime_checkable
class IdeRepository(Protocol):
    """Per-project IDE windows opened by this MCP process.

    `open` always spawns a new window (`code -n <path>`) so multiple projects
    can be open simultaneously. Tracking is per process — restarting the MCP
    forgets earlier windows (they remain open in the user's IDE).
    """

    async def open_project(
        self,
        project_path: Path,
        ide: IdeKind = IdeKind.VSCODE,
        new_window: bool = True,
    ) -> Result[IdeWindow]: ...
    async def list_windows(self) -> Result[list[IdeWindow]]: ...
    async def close_window(
        self,
        project_path: Path | None = None,
        window_id: str | None = None,
    ) -> Result[None]: ...
    async def focus_window(self, project_path: Path) -> Result[None]: ...
    async def is_available(self, ide: IdeKind = IdeKind.VSCODE) -> Result[str]: ...


@runtime_checkable
class RagRepository(Protocol):
    """Vector-search backed retrieval over indexed text.

    `recall(query, k, scope)` returns up to k chunks ranked by relevance to
    the query. `scope` is a logical filter — e.g. "skill" surfaces only
    chunks tagged as belonging to the SKILL doc collection, "trace" surfaces
    session-trace chunks, "all" returns the union.

    `index_collection` writes a batch of (text, source, metadata) triples
    into a named collection, computing embeddings on the way in. Idempotent
    on `source`: re-indexing the same source replaces its chunks.

    Implementations must NOT raise — return RagUnavailableFailure when the
    backend isn't reachable. The use case decides whether to surface that
    or to fail open.
    """

    async def recall(
        self,
        query: str,
        k: int = 3,
        scope: str = "all",
    ) -> Result[list[RecallChunk]]: ...

    async def index_collection(
        self,
        collection: str,
        items: list[tuple[str, str, dict]],
    ) -> Result[IndexStats]: ...

    async def is_available(self) -> Result[str]: ...


@runtime_checkable
class SkillLibraryRepository(Protocol):
    """Persistent named-macro library — see ADR-0004 (Voyager-style).

    Skills are JSON-encodeable sequences keyed by name. `promote`
    stores or replaces; `fetch` reads back; `record_use` updates
    success/use counters. Implementations: SQLite-backed (default),
    in-memory (tests).
    """

    async def promote(
        self, name: str, description: str, sequence: list[dict]
    ) -> Result[None]: ...

    async def list_skills(self) -> Result[list[dict]]: ...

    async def fetch(self, name: str) -> Result[dict | None]: ...

    async def record_use(self, name: str, success: bool) -> Result[None]: ...

    async def delete(self, name: str) -> Result[None]: ...

"""Domain entities — pure data shapes. No I/O, no third-party types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class Platform(str, Enum):
    ANDROID = "android"
    IOS = "ios"


class DeviceClass(str, Enum):
    """Distinguishes physical hardware from virtual devices.

    PHYSICAL  — real hardware (USB-attached phone)
    EMULATOR  — Android AVD running on the host
    SIMULATOR — iOS Simulator running on the host
    UNKNOWN   — class wasn't determined yet
    """

    PHYSICAL = "physical"
    EMULATOR = "emulator"
    SIMULATOR = "simulator"
    UNKNOWN = "unknown"


class DeviceState(str, Enum):
    DEVICE = "device"
    OFFLINE = "offline"
    UNAUTHORIZED = "unauthorized"
    UNKNOWN = "unknown"


class BuildMode(str, Enum):
    DEBUG = "debug"
    PROFILE = "profile"
    RELEASE = "release"


class LogLevel(str, Enum):
    VERBOSE = "V"
    DEBUG = "D"
    INFO = "I"
    WARN = "W"
    ERROR = "E"
    FATAL = "F"


class TestStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    ERRORED = "errored"
    SKIPPED = "skipped"


class ArtifactKind(str, Enum):
    SCREENSHOT = "screenshot"
    RECORDING = "recording"
    LOG = "log"
    UI_DUMP = "ui_dump"
    REPORT = "report"


@dataclass(frozen=True, slots=True)
class Device:
    serial: str
    state: DeviceState
    model: str | None = None
    os_version: str | None = None
    platform: Platform | None = None
    device_class: DeviceClass = DeviceClass.UNKNOWN


@dataclass(frozen=True, slots=True)
class AppBundle:
    """A built application artifact — APK on Android, IPA/.app on iOS."""

    path: Path
    mode: BuildMode
    platform: Platform = Platform.ANDROID
    flavor: str | None = None


@dataclass(frozen=True, slots=True)
class Bounds:
    x: int
    y: int
    width: int
    height: int

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)


@dataclass(frozen=True, slots=True)
class UiElement:
    text: str | None
    resource_id: str | None
    class_name: str | None
    content_description: str | None
    bounds: Bounds
    enabled: bool
    clickable: bool


@dataclass(frozen=True, slots=True)
class LogEntry:
    timestamp: str
    level: LogLevel
    tag: str
    pid: int | None
    message: str


@dataclass(frozen=True, slots=True)
class TestCase:
    name: str
    status: TestStatus
    duration_ms: int
    error_message: str | None = None
    stack_trace: str | None = None


@dataclass(frozen=True, slots=True)
class TestRun:
    total: int
    passed: int
    failed: int
    errored: int
    skipped: int
    duration_ms: int
    cases: list[TestCase] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        return self.failed == 0 and self.errored == 0


@dataclass(frozen=True, slots=True)
class Artifact:
    path: Path
    kind: ArtifactKind
    label: str | None = None


@dataclass(frozen=True, slots=True)
class Session:
    id: str
    root: Path
    started_at: datetime
    label: str | None = None


# --- Autonomy primitives --------------------------------------------------


@dataclass(frozen=True, slots=True)
class DeviceLock:
    """Records that one MCP session has exclusive access to a device serial."""

    serial: str
    session_id: str
    pid: int
    started_at: datetime
    note: str | None = None


@dataclass(frozen=True, slots=True)
class Capability:
    """One capability of the MCP server, exposed via describe_capabilities."""

    name: str
    available: bool
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class CapabilityReport:
    platforms: tuple[str, ...]
    test_frameworks: tuple[str, ...]
    gates_handled: tuple[str, ...]
    vision_ops: tuple[str, ...]
    capabilities: tuple[Capability, ...]
    known_limits: tuple[str, ...] = ()
    # Self-describing schema for run_test_plan — agents can author plans
    # without trial-and-error against error messages.
    plan_schema: dict | None = None
    # Tool ladder for small-LLM agents: which tools to expose at this level.
    # Empty tuple = "all tools" (the default at level=expert / unspecified).
    tool_subset: tuple[str, ...] = ()
    level: str = "expert"
    # Recommended ordered sequence of tool calls for the most common task at
    # this level. Empty when unspecified. Grounded in the ReAct pattern
    # (Yao et al., 2022, arXiv 2210.03629): the model needs a strong prior on
    # *what* to call first, not just *which* tools exist.
    recommended_sequence: tuple[str, ...] = ()
    # Version handshake — surfaced so an agent observing a missing
    # feature can detect a stale MCP subprocess without a second tool call.
    # Compare with the on-disk repo's `git rev-parse --short HEAD`; if
    # they differ, the agent should ask the user to restart Claude Code.
    mcp_version: str = "unknown"
    mcp_git_sha: str = "unknown"


@dataclass(frozen=True, slots=True)
class TraceEntry:
    """A single tool invocation in a session — the unit of audit."""

    sequence: int
    tool_name: str
    args: dict
    ok: bool
    error_code: str | None
    summary: str
    artifact_paths: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SessionTrace:
    session_id: str
    started_at: datetime
    entries: tuple[TraceEntry, ...]


# --- Test plans -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PhaseDriver:
    kind: str                       # "patrol_test" | "tap_text" | "noop" | ...
    target: str | None = None       # e.g. test path, or display text for tap
    args: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PlanPhase:
    # PRE_FLIGHT | CLEAN | LAUNCHED | <GATE> | UNDER_TEST | VERDICT_* |
    # OPEN_IDE | DEV_SESSION_* | HOT_RELOAD | AR_SCENE_READY | REFLECTION
    phase: str
    driver: PhaseDriver | None = None
    planned_outcome: str | None = None     # "accept" | "decline" | "pass" | "decided"
    package_id: str | None = None
    project_path: str | None = None
    wait_for_key: str | None = None
    wait_for_text: str | None = None
    timeout_s: float | None = None
    capture: tuple[str, ...] = ()         # ("screenshot", "logs", "ui_dump", "debug_log")
    notes: str | None = None
    extras: dict = field(default_factory=dict)   # phase-specific config (mode, ide, new_window, full_restart, ...)


@dataclass(frozen=True, slots=True)
class TestPlan:
    api_version: str
    kind: str
    name: str
    device_platform: str | None
    device_pool: str | None
    project_path: Path | None
    phases: tuple[PlanPhase, ...]
    report_format: str | None = None       # "junit" | "json" | None


@dataclass(frozen=True, slots=True)
class PhaseOutcome:
    phase: str
    ok: bool
    planned_outcome: str | None
    actual_outcome: str | None
    artifacts: tuple[str, ...] = ()
    error_code: str | None = None
    error_message: str | None = None
    notes: str | None = None
    duration_ms: int = 0


@dataclass(frozen=True, slots=True)
class PlanRun:
    plan_name: str
    started_at: datetime
    finished_at: datetime
    overall_ok: bool
    phases: tuple[PhaseOutcome, ...]
    junit_path: Path | None = None
    duration_ms: int = 0


# --- Vision ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MarkerDetection:
    id: int
    corners: tuple[tuple[int, int], ...]   # 4 corner points in image coords
    center: tuple[int, int]


@dataclass(frozen=True, slots=True)
class Pose:
    rvec: tuple[float, float, float]
    tvec: tuple[float, float, float]
    marker_id: int


@dataclass(frozen=True, slots=True)
class ImageDiff:
    similarity: float                       # 0..1; 1 = identical
    threshold: float
    passed: bool
    diff_image_path: Path | None = None
    masked_pixels: int = 0


@dataclass(frozen=True, slots=True)
class CameraIntrinsics:
    """Camera matrix + distortion from a chessboard calibration."""

    fx: float
    fy: float
    cx: float
    cy: float
    distortion: tuple[float, ...]   # k1, k2, p1, p2, k3
    reprojection_error: float
    sample_count: int


@dataclass(frozen=True, slots=True)
class PoseStabilityReport:
    marker_id: int
    samples: int
    translation_max_delta_m: float
    rotation_max_delta_deg: float
    passed: bool


@dataclass(frozen=True, slots=True)
class GoldenImage:
    label: str
    path: Path
    image_size_bytes: int


class ProjectType(str, Enum):
    FLUTTER = "flutter"
    NATIVE_ANDROID = "native_android"
    NATIVE_IOS = "native_ios"
    REACT_NATIVE = "react_native"
    WEB = "web"
    UNKNOWN = "unknown"


class TestFramework(str, Enum):
    """Test frameworks the MCP knows how to drive. Extend by adding a new enum
    member, a TestRepository implementation, and registering it in the composite."""

    PATROL = "patrol"
    FLUTTER = "flutter"            # plain `flutter test` (no Patrol)
    XCUITEST = "xcuitest"          # native iOS, future
    ESPRESSO = "espresso"          # native Android, future
    DETOX = "detox"                # React Native, future
    PLAYWRIGHT = "playwright"      # web, future
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ProjectInfo:
    """Result of inspecting a project directory."""

    path: Path
    type: ProjectType
    test_frameworks: tuple[TestFramework, ...]
    package_id: str | None = None
    flavors: tuple[str, ...] = ()
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class PatrolTestFile:
    """A discovered Patrol-style integration test file."""

    path: Path             # absolute path on disk
    relative: Path         # relative to project_path/integration_test
    name: str              # human label, e.g. "auth_smoke_test"


@dataclass(frozen=True, slots=True)
class EnvironmentCheck:
    name: str
    ok: bool
    detail: str | None = None
    fix: str | None = None


@dataclass(frozen=True, slots=True)
class EnvironmentReport:
    ok: bool
    checks: list[EnvironmentCheck] = field(default_factory=list)


# --- Dev session (flutter run --machine) ---------------------------------


class DebugSessionState(str, Enum):
    STARTING = "starting"
    RUNNING = "running"
    RELOADING = "reloading"
    STOPPED = "stopped"
    ERRORED = "errored"


@dataclass(frozen=True, slots=True)
class DebugSession:
    """A long-lived `flutter run --machine` process attached to one device."""

    id: str
    project_path: Path
    device_serial: str
    mode: BuildMode
    started_at: datetime
    state: DebugSessionState
    app_id: str | None = None
    vm_service_uri: str | None = None
    flavor: str | None = None
    target: str | None = None
    pid: int | None = None


@dataclass(frozen=True, slots=True)
class DebugLogEntry:
    """One line of output from a debug session."""

    timestamp: datetime
    level: str                  # "info" | "warning" | "error" | "stdout" | "stderr" | "progress"
    source: str                 # "app" | "daemon" | "stdout" | "stderr"
    message: str
    isolate_id: str | None = None


@dataclass(frozen=True, slots=True)
class ServiceExtensionResult:
    method: str
    result: dict
    elapsed_ms: int


# --- IDE windows ---------------------------------------------------------


class IdeKind(str, Enum):
    VSCODE = "vscode"


@dataclass(frozen=True, slots=True)
class IdeWindow:
    """An IDE window this MCP process opened. Tracked per project."""

    window_id: str
    project_path: Path
    ide: IdeKind
    pid: int
    opened_at: datetime


# --- Code quality --------------------------------------------------------


class AnalyzerSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class AnalyzerIssue:
    severity: AnalyzerSeverity
    code: str
    message: str
    file: Path | None
    line: int | None
    column: int | None


@dataclass(frozen=True, slots=True)
class AnalyzerReport:
    project_path: Path
    issues: tuple[AnalyzerIssue, ...]

    @property
    def errors(self) -> int:
        return sum(1 for i in self.issues if i.severity is AnalyzerSeverity.ERROR)

    @property
    def warnings(self) -> int:
        return sum(1 for i in self.issues if i.severity is AnalyzerSeverity.WARNING)


@dataclass(frozen=True, slots=True)
class FormatReport:
    target_path: Path
    files_changed: int
    files_unchanged: int
    diff: str | None = None


@dataclass(frozen=True, slots=True)
class FixReport:
    project_path: Path
    fixes_applied: int
    files_changed: int


@dataclass(frozen=True, slots=True)
class PubOutdatedEntry:
    package: str
    current: str | None
    upgradable: str | None
    latest: str | None


@dataclass(frozen=True, slots=True)
class QualityGateReport:
    project_path: Path
    analyzer_errors: int
    analyzer_warnings: int
    format_clean: bool
    unit_tests_passed: int
    unit_tests_failed: int
    overall_ok: bool


# --- RAG retrieval --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RecallChunk:
    """A single chunk surfaced by the RAG backend.

    `score` is implementation-specific (cosine similarity for dense, BM25
    score for sparse). `source` is a logical identifier (file path, doc
    section, trace entry id) — the agent can ask `fetch_artifact` for the
    full content if the chunk is enough to know "where to look next."
    """

    text: str
    source: str
    score: float
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class IndexStats:
    collection: str
    files_indexed: int
    chunks_indexed: int
    skipped: tuple[str, ...] = ()
    duration_ms: int = 0

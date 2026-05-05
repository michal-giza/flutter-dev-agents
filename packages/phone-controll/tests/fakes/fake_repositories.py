"""In-memory fakes for every domain repository protocol."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from mcp_phone_controll.domain.entities import (
    AppBundle,
    Artifact,
    BuildMode,
    Device,
    DeviceState,
    LogEntry,
    LogLevel,
    Platform,
    Session,
    TestRun,
    UiElement,
)
from mcp_phone_controll.domain.failures import (
    DeviceNotFoundFailure,
    UiElementNotFoundFailure,
)
from mcp_phone_controll.domain.result import Result, err, ok


class FakeDeviceRepository:
    def __init__(self, devices: list[Device] | None = None) -> None:
        if devices is None:
            devices = [
                Device(
                    serial="EMU01",
                    state=DeviceState.DEVICE,
                    model="Pixel",
                    os_version="14",
                    platform=Platform.ANDROID,
                ),
            ]
        self.devices = devices

    async def list_devices(self) -> Result[list[Device]]:
        return ok(list(self.devices))

    async def get_device(self, serial: str) -> Result[Device]:
        for d in self.devices:
            if d.serial == serial:
                return ok(d)
        return err(DeviceNotFoundFailure(message=f"no device {serial}"))


class FakeLifecycleRepository:
    def __init__(self, name: str = "fake") -> None:
        self.name = name
        self.calls: list[tuple] = []

    async def install(self, serial, bundle_path, replace=True):
        self.calls.append((self.name, "install", serial, str(bundle_path)))
        return ok(None)

    async def uninstall(self, serial, package_id):
        self.calls.append((self.name, "uninstall", serial, package_id))
        return ok(None)

    async def launch(self, serial, package_id, activity=None):
        self.calls.append((self.name, "launch", serial, package_id, activity or ""))
        return ok(None)

    async def stop(self, serial, package_id):
        self.calls.append((self.name, "stop", serial, package_id))
        return ok(None)

    async def clear_data(self, serial, package_id):
        self.calls.append((self.name, "clear_data", serial, package_id))
        return ok(None)

    async def grant_permission(self, serial, package_id, permission):
        self.calls.append((self.name, "grant", serial, package_id, permission))
        return ok(None)


class FakeBuildRepository:
    def __init__(self, bundle_path: Path | None = None) -> None:
        self.bundle_path = bundle_path or Path("/tmp/fake.apk")

    async def build_bundle(
        self, project_path, mode, platform=Platform.ANDROID, flavor=None
    ):
        return ok(
            AppBundle(path=self.bundle_path, mode=mode, platform=platform, flavor=flavor)
        )


class FakeUiRepository:
    def __init__(self, found: UiElement | None = None, name: str = "fake") -> None:
        self.found = found
        self.name = name
        self.taps: list[tuple] = []

    async def tap(self, serial, x, y):
        self.taps.append((self.name, "tap", serial, x, y))
        return ok(None)

    async def tap_text(self, serial, text, exact=False):
        self.taps.append((self.name, "tap_text", serial, text, exact))
        return ok(None)

    async def swipe(self, serial, x1, y1, x2, y2, duration_ms=300):
        self.taps.append((self.name, "swipe", serial, x1, y1, x2, y2))
        return ok(None)

    async def type_text(self, serial, text):
        self.taps.append((self.name, "type", serial, text))
        return ok(None)

    async def press_key(self, serial, keycode):
        self.taps.append((self.name, "key", serial, keycode))
        return ok(None)

    async def find(self, serial, text=None, resource_id=None, class_name=None, timeout_s=5.0):
        return ok(self.found)

    async def wait_for(self, serial, text=None, resource_id=None, timeout_s=10.0):
        if self.found is None:
            return err(UiElementNotFoundFailure(message="not found"))
        return ok(self.found)

    async def dump_ui(self, serial):
        return ok(f"<{self.name}-hierarchy/>")


class FakeObservationRepository:
    def __init__(self, name: str = "fake") -> None:
        self.name = name

    async def screenshot(self, serial, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(self.name.encode())
        return ok(output_path)

    async def start_recording(self, serial, output_path):
        return ok(None)

    async def stop_recording(self, serial):
        path = Path("/tmp/fake-recording.mp4")
        return ok(path)

    async def read_logs(self, serial, since_s=30, tag=None, min_level=LogLevel.WARN, max_lines=500):
        return ok(
            [
                LogEntry(
                    timestamp="01-01 00:00:00.000",
                    level=LogLevel.WARN,
                    tag=self.name,
                    pid=1,
                    message="hi",
                )
            ]
        )

    async def tail_logs_until(self, serial, until_pattern, tag=None, timeout_s=30.0):
        return ok([])


class FakeTestRepository:
    def __init__(self, run: TestRun | None = None) -> None:
        self.run = run or TestRun(
            total=1, passed=1, failed=0, errored=0, skipped=0, duration_ms=10
        )

    async def run_unit_tests(self, project_path):
        return ok(self.run)

    async def run_integration_tests(self, project_path, device_serial, test_path="integration_test/"):
        return ok(self.run)


class FakeArtifactRepository:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.session: Session | None = None
        self.registered: list[Artifact] = []

    async def new_session(self, label=None):
        sid = "test-session"
        self.session = Session(id=sid, root=self.root / sid, started_at=datetime.now(), label=label)
        self.session.root.mkdir(parents=True, exist_ok=True)
        return ok(self.session)

    async def current_session(self):
        if self.session is None:
            return await self.new_session()
        return ok(self.session)

    async def allocate_path(self, kind, suffix, label=None):
        sess = await self.current_session()
        return ok(sess.value.root / f"{kind}-{label or 'x'}{suffix}")

    async def register(self, artifact):
        self.registered.append(artifact)
        return ok(None)


class FakeSessionStateRepository:
    def __init__(self, serial: str | None = None) -> None:
        self.serial = serial

    async def set_selected_serial(self, serial):
        self.serial = serial
        return ok(None)

    async def get_selected_serial(self):
        return ok(self.serial)


# --- new framework + project layer fakes ----------------------------------

from datetime import datetime as _dt

from mcp_phone_controll.domain.entities import (
    Capability,
    CapabilityReport,
    EnvironmentCheck,
    EnvironmentReport,
    PatrolTestFile,
    PhaseOutcome,
    PlanRun,
    ProjectInfo,
    ProjectType,
    SessionTrace,
    TestFramework,
    TestPlan,
    TraceEntry,
)


class FakePatrolRepository:
    def __init__(self, run: TestRun | None = None, files: list[PatrolTestFile] | None = None) -> None:
        self.run = run or TestRun(total=2, passed=2, failed=0, errored=0, skipped=0, duration_ms=42)
        self.files = files or []
        self.calls: list[tuple] = []

    async def list_tests(self, project_path):
        self.calls.append(("list_tests", str(project_path)))
        return ok(self.files)

    async def run_test(self, project_path, test_path, device_serial, flavor=None, build_mode=None):
        self.calls.append(("run_test", str(project_path), str(test_path), device_serial))
        return ok(self.run)

    async def run_suite(self, project_path, test_dir, device_serial, flavor=None, build_mode=None):
        self.calls.append(("run_suite", str(project_path), str(test_dir), device_serial))
        return ok(self.run)

    # Also acts as a TestRepository for composite routing tests.
    async def run_unit_tests(self, project_path):
        self.calls.append(("run_unit_tests", str(project_path)))
        return ok(self.run)

    async def run_integration_tests(self, project_path, device_serial, test_path="integration_test/"):
        self.calls.append(("run_integration_tests", str(project_path), device_serial))
        return ok(self.run)


class FakeProjectInspector:
    def __init__(self, info: ProjectInfo | None = None) -> None:
        self.info = info

    async def inspect(self, project_path):
        if self.info is not None:
            return ok(self.info)
        return ok(
            ProjectInfo(
                path=project_path,
                type=ProjectType.FLUTTER,
                test_frameworks=(TestFramework.PATROL, TestFramework.FLUTTER),
                package_id="fake_app",
            )
        )


class FakeEnvironmentRepository:
    async def check(self):
        return ok(
            EnvironmentReport(
                ok=True,
                checks=[
                    EnvironmentCheck(name="adb", ok=True, detail="/usr/local/bin/adb"),
                    EnvironmentCheck(name="flutter", ok=True),
                    EnvironmentCheck(name="patrol", ok=True),
                    EnvironmentCheck(name="pymobiledevice3", ok=True),
                ],
            )
        )


class FakeCapabilitiesProvider:
    async def describe(self):
        return ok(
            CapabilityReport(
                platforms=("android", "ios"),
                test_frameworks=("patrol", "flutter"),
                gates_handled=("UMP", "ATT", "runtime_permission"),
                vision_ops=("compare_screenshot", "detect_markers"),
                capabilities=(
                    Capability(name="patrol", available=True),
                    Capability(name="adb", available=True),
                ),
            )
        )


class FakeSessionTraceRepository:
    def __init__(self) -> None:
        self.entries: list[TraceEntry] = []
        self._seq = 0

    def next_sequence(self) -> int:
        self._seq += 1
        return self._seq

    async def record(self, entry):
        self.entries.append(entry)
        return ok(None)

    async def summary(self, session_id=None):
        return ok(
            SessionTrace(
                session_id=session_id or "current",
                started_at=_dt.now(),
                entries=tuple(self.entries),
            )
        )

    async def reset(self):
        self.entries.clear()
        return ok(None)


class FakePlanLoader:
    def __init__(self, plan: TestPlan | None = None) -> None:
        self._plan = plan

    def load_path(self, path):
        return ok(self._plan) if self._plan is not None else err(
            __import__(
                "mcp_phone_controll.domain.failures", fromlist=["InvalidArgumentFailure"]
            ).InvalidArgumentFailure(message="no plan configured")
        )

    def load_str(self, source):
        return self.load_path(source)


class FakeVirtualDeviceManager:
    def __init__(self) -> None:
        self.avds = ["Pixel_7_API_34"]
        self.calls: list[tuple] = []

    async def list_avds(self):
        return ok(list(self.avds))

    async def start_emulator(self, avd_name, headless=False):
        self.calls.append(("start_emulator", avd_name, headless))
        return ok("emulator-5554")

    async def stop_virtual_device(self, serial):
        self.calls.append(("stop", serial))
        return ok(None)

    async def list_simulators(self, include_shutdown=True):
        return ok([])

    async def boot_simulator(self, name_or_udid):
        self.calls.append(("boot", name_or_udid))
        from datetime import datetime as _dt2

        return ok(
            __import__(
                "mcp_phone_controll.domain.entities", fromlist=["Device"]
            ).Device(
                serial="UDID-FAKE",
                state=__import__(
                    "mcp_phone_controll.domain.entities", fromlist=["DeviceState"]
                ).DeviceState.DEVICE,
                platform=__import__(
                    "mcp_phone_controll.domain.entities", fromlist=["Platform"]
                ).Platform.IOS,
                device_class=__import__(
                    "mcp_phone_controll.domain.entities", fromlist=["DeviceClass"]
                ).DeviceClass.SIMULATOR,
            )
        )


class FakePlanExecutor:
    def __init__(self, run: PlanRun | None = None) -> None:
        self.run_value = run
        self.calls: list[TestPlan] = []

    async def run(self, plan):
        self.calls.append(plan)
        if self.run_value is not None:
            return ok(self.run_value)
        return ok(
            PlanRun(
                plan_name=plan.name,
                started_at=_dt.now(),
                finished_at=_dt.now(),
                overall_ok=True,
                phases=tuple(
                    PhaseOutcome(
                        phase=p.phase, ok=True,
                        planned_outcome=p.planned_outcome,
                        actual_outcome=p.planned_outcome or "passed",
                    )
                    for p in plan.phases
                ),
            )
        )

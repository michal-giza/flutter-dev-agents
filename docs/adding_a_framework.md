# Adding a new test framework

The architecture is built so that new test frameworks (XCUITest for native iOS, Espresso for native Android, Detox for React Native, Playwright for web, …) drop in with **zero changes** to use cases, presentation, or the MCP tool surface.

## The recipe (5 steps, ~half a day each)

Take XCUITest as the worked example.

### 1. Add an enum value

`packages/phone-controll/src/mcp_phone_controll/domain/entities.py`

```python
class TestFramework(str, Enum):
    PATROL = "patrol"
    FLUTTER = "flutter"
    XCUITEST = "xcuitest"          # <-- new
    ...
```

### 2. Implement `TestRepository` for the new framework

`packages/phone-controll/src/mcp_phone_controll/data/repositories/xcuitest_repository.py`

```python
class XcuiTestRepository(TestRepository):
    def __init__(self, xcodebuild: XcodebuildCli) -> None:
        self._xcodebuild = xcodebuild

    async def run_unit_tests(self, project_path):
        # `xcodebuild test -project ... -scheme ... -destination 'platform=iOS Simulator,...'`
        ...

    async def run_integration_tests(self, project_path, device_serial, test_path="..."):
        ...
```

### 3. Add a `ProjectInspector` that detects projects of that type

`packages/phone-controll/src/mcp_phone_controll/data/repositories/native_ios_project_inspector.py`

Detects `*.xcodeproj` / `*.xcworkspace` and a `Podfile`, returns `ProjectInfo(type=ProjectType.NATIVE_IOS, test_frameworks=(TestFramework.XCUITEST,))`.

### 4. Wire into the container

`packages/phone-controll/src/mcp_phone_controll/container.py`

```python
inspector = CompositeProjectInspector([
    FlutterProjectInspector(),
    NativeIosProjectInspector(),    # <-- new
])

xcuitest_repo = XcuiTestRepository(xcodebuild)

test_repo = CompositeTestRepository(
    android=flutter_tests,
    ios=flutter_tests,
    resolver=resolver,
    framework_runners={
        TestFramework.PATROL: patrol_tests,
        TestFramework.XCUITEST: xcuitest_repo,    # <-- new
    },
    inspector=inspector,
)
```

### 5. Update the plan schema

`packages/phone-controll/src/mcp_phone_controll/data/repositories/static_capabilities_provider.py` — add `xcuitest` to `valid_driver_kinds` if you want to invoke it directly from a YAML plan.

`packages/phone-controll/src/mcp_phone_controll/data/repositories/yaml_plan_executor.py` — add an `elif kind == "xcuitest":` branch in `_driver_phase`.

## What you get for free

- Existing `run_integration_tests` tool now auto-routes to your new framework when `inspect_project` reports it.
- Existing YAML plans transparently use the new framework — no plan rewrites.
- The HTTP adapter exposes everything; agents just call `run_integration_tests` and the right thing happens.
- Failure types, `next_action` hints, session tracing, JUnit output — all inherited.

## Tests to write

- Pure-function test for the new project inspector (fixture project structure → expected `ProjectInfo`).
- Use-case test for the new `TestRepository` against a fake CLI runner.
- Composite-routing test: `inspect_project` returns the new framework → `run_integration_tests` dispatches to the new repo.

That's typically ~half a day of work for a well-scoped framework.

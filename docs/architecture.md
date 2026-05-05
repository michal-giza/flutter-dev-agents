# Architecture

This document describes the cross-cutting design that every MCP in this monorepo follows.

## Clean Architecture, three rings + presentation shell

Every package under `packages/*` is structured the same way:

```
domain/         pure business logic — entities, Result, Failures, repository protocols, use cases
infrastructure/ outbound adapters — subprocess wrappers, library wrappers, no domain knowledge
data/           parsers + repository implementations + composites
presentation/   MCP server — tool registry maps tool names to use cases
adapters/       optional HTTP/REST/OpenAPI surfaces for autonomous-agent consumption
container.py    composition root — wires every concrete repo into every use case
```

**Dependency direction is inward.** Domain depends on nothing in the project. Data depends on domain + infrastructure. Presentation depends on domain. The composition root depends on everything.

## Errors as values, never exceptions

Every use case returns `Result[T] = Ok[T] | Err`. Every `Failure` carries a canonical `next_action` string so an agent (Claude or a local LLM) can switch on it without parsing the message:

| `next_action` | Meaning |
|---|---|
| `"run_check_environment"` | Env preflight should fix it |
| `"fix_arguments"` | Schema/argument problem |
| `"wait_or_force"` | A lock is held; wait or force |
| `"force_release_lock"` | Stale lock; admin action |
| `"calibrate_stand"` | AR/vision specific |
| `"review_diff"` | Visual-diff failure |
| `"ask_user"` | Needs human decision |
| `"retry_with_backoff"` | Transient |

The MCP layer translates `Result` into a uniform `{ok, data, error: {code, message, next_action, details}}` envelope on both stdio and HTTP transports.

## Composite routing

Two orthogonal composites in `phone-controll`:

- **Platform composite** — routes by `Platform` (Android / iOS) for device, lifecycle, UI, observation calls. Backed by `CachingPlatformResolver` that remembers `serial → (Platform, DeviceClass)`.
- **Framework composite** — routes by `TestFramework` (Patrol / Flutter / future XCUITest / Espresso / Detox / Playwright) for test execution. Backed by `ProjectInspector` that determines which frameworks apply to a project.

iOS has a third level: `MultiSourceIosDeviceRepository` unions physical (pymobiledevice3) and simulator (xcrun simctl) sources, routing each call by `DeviceClass`.

## Cross-session coordination

Every Claude conversation spawns its own MCP subprocess. Coordination across processes:

- **Filesystem device locks** — `~/.mcp_phone_controll/locks/<serial>.lock`, JSON contents (session_id, pid, started_at), `O_EXCL` creation, PID-aware stale reclaim. `select_device` acquires; `release_device` releases.
- **No shared state otherwise** — each MCP process has its own session trace, selected device, session id.

For an HTTP shared-server topology (one process serving N Claude clients), swap `FilesystemDeviceLockRepository` for `InMemoryDeviceLockRepository`; nothing else changes.

## Plan-walker (declarative YAML)

`run_test_plan` interprets `apiVersion: phone-controll/v1` plans:

```
phases: PRE_FLIGHT → CLEAN → LAUNCHED → <NAME>_GATE → UNDER_TEST → VERDICT_*
drivers: patrol_test | flutter_test | tap_text | noop
```

Phase failures auto-inject `VERDICT_BLOCKED`. Planned-decline branches stop the walker after the verdict phase. Schema is self-describing via `describe_capabilities.plan_schema` — agents author plans without trial-and-error.

## Two transports, one envelope

- **stdio MCP** (default) — `python -m mcp_phone_controll` registered via `claude mcp add`.
- **OpenAI-compat HTTP adapter** (optional) — `mcp-phone-controll-http`. Exposes `GET /tools` (OpenAI function-call schemas), `POST /tools/{name}` (dispatcher passthrough), `GET /openapi.json` (free FastAPI). Identical envelopes to stdio.

A future MCP can add its own sub-router (e.g. `/dev-session/*`) without forking the dispatcher.

## Container topology (deferred)

- **Native macOS** for human-developer machines: real USB devices, iOS Simulator, GUI VS Code, multi-Claude concurrency.
- **Linux container** for CI: headless Android emulator + Flutter + Patrol + MCP. iOS Simulator cannot be containerised (Apple-side restriction).

The container image is documented in `docs/adding_an_mcp.md` § "CI image" but not yet built.

## Why this design holds up

Adding a new test framework, a new platform's UI driver, a new fiducial-marker dictionary, or a new MCP package — none of these change use cases or tool definitions. Every extension is "implement the protocol, register in the container, add to the framework-runner map." The composite layer absorbs the routing.

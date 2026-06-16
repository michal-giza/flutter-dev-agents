# flutter-dev-agents

**Audit-grade Flutter testing for AI agents — drive real iPhones, Androids & the web, then grade what ships.**

[![tests](https://img.shields.io/badge/tests-1034_passing-A6E22E?style=flat-square)](packages/phone-controll/tests)
[![license](https://img.shields.io/badge/license-Apache_2.0-F76C28?style=flat-square)](LICENSE)
[![MCP spec](https://img.shields.io/badge/MCP-2025--06--18-F76C28?style=flat-square)](https://modelcontextprotocol.io)
[![python](https://img.shields.io/badge/python-3.11+-3B4252?style=flat-square)](pyproject.toml)
[![PyPI](https://img.shields.io/pypi/v/mcp-phone-controll?style=flat-square&color=3B4252)](https://pypi.org/project/mcp-phone-controll/)
[![CI](https://img.shields.io/github/actions/workflow/status/michal-giza/flutter-dev-agents/ci.yml?branch=main&style=flat-square)](https://github.com/michal-giza/flutter-dev-agents/actions)

`mcp-phone-controll` is an MCP server that gives agents safe, structured access to **real Android + iOS devices and Flutter web** — and, uniquely, an **opinionated audit suite** that *grades* the code, tests, and runtime an agent produces. **143 tools.** Works with Claude Desktop / Code, Cursor, or any MCP host — **including local/SLM models** via the OpenAI-compat HTTP adapter.

### What makes it different

- **An audit suite no other Flutter MCP has.** Pure-compute senior-engineer rubrics that grade what the agent ships — `audit_code_seniority`, `audit_security` (OWASP MASVS), **`audit_performance`** (animation / scroll / rebuild jank), `audit_accessibility`, `audit_localization`, `audit_dependencies`, `audit_test_quality`, `audit_web_app` — all gated by a 9-domain **`audit_release_readiness`** composite that returns a ship / hold / block verdict. No device needed; works for any model.
- **Composes, doesn't reinvent.** It *drives* devices (adb / WebDriverAgent / Patrol) and *grades* the result. For web *driving* it composes with the model-agnostic **Chrome DevTools MCP / Playwright MCP** rather than shipping its own browser driver, and defers SDK plumbing to Google's built-in `dart mcp-server` and mobile flows to Maestro. → [The Stack](docs/the-stack.md)
- **Runtime graders — you capture, we grade.** `run_lighthouse` (web vitals), `ingest_frame_timeline` (jank score from a VM-Timeline / Chrome trace), `ingest_har` (per-action network / Firestore cost), `ingest_maestro_report`.

### Quickstart

```bash
pip install mcp-phone-controll                # or: uvx mcp-phone-controll
claude mcp add phone-controll -- python -m mcp_phone_controll

# optional — model-agnostic web driving (compose, don't reinvent):
claude mcp add chrome-devtools --scope user -- npx -y chrome-devtools-mcp@latest
claude mcp add playwright      --scope user -- npx -y @playwright/mcp@latest
```

Then call `describe_capabilities` from your agent. Full setup (venv-pinned, device prereqs): **[First 15 minutes](docs/GETTING-STARTED.md)**.

→ **[The Stack](docs/the-stack.md)** · **[Performance rubric](docs/performance-rubric.md)** · **[SLM / local-model setup](docs/slm-setup.md)** · **[Senior-tester discipline](docs/senior-tester-discipline.md)** · **[Comparison vs other MCPs](docs/flutter-mcp-comparison.md)** · **[Web before/after playbook](docs/web-logged-in-flow.md)** · **[FAQ](docs/FAQ.md)** · **[Configuration](docs/CONFIGURATION.md)** · **[Tools by category](docs/tools-by-category.md)** · **[Architecture](docs/architecture.md)**

## What's new in v0.10.0 (June 2026)

The **performance + web** arc. Flutter web is now a first-class target, and the audit suite grows the jank/perf dimension that no first-party MCP covers.

- 🆕 **`audit_performance`** (v0.9.0) — static jank audit: animation anti-patterns (controller-in-build, setState-in-listener, animated Opacity), scroll/virtualization (`ListView(children:)` vs `.builder`), rebuild cost. → [rubric](docs/performance-rubric.md)
- 🆕 **`ingest_frame_timeline`** + **`ingest_har`** (v0.10.0) — runtime graders: jank score from a captured frame timeline; per-action network/Firestore cost from a HAR.
- 🆕 **Flutter web** (v0.5–0.8) — `audit_web_app`, `run_lighthouse`, web debug sessions (`start_debug_session(serial="chrome")` → `dump_widget_tree` via DWDS), `run_unit_tests(platform="chrome")`.
- 🔧 **Composition** — registers + documents **Chrome DevTools MCP** (debug/tooling) and **Playwright MCP** (visual/SLM) as the model-agnostic browser-driving layer; tracks Google's MCP now being built into the SDK (`dart mcp-server`).

**Previous milestones:** v0.4.0 Maestro composition (`audit_maestro_flow` + `ingest_maestro_report`) · v0.3.0 the audit suite + senior-tester loop (`design_test_plan` + `audit_test_quality`) · v0.2.x PyPI release, multi-device locking, Patrol, AR/vision. Full history: [`CHANGELOG.md`](CHANGELOG.md).

---

## Why it matters

Mobile QA still loses 30–50% of its engineering hours to flaky selector maintenance ([Drizz industry survey, 2026](https://drizz.dev)). Agents can close that loop — but until now there was no production-grade MCP that gave them safe, structured access to real phones. This is that MCP:

- **Cross-session device locking** so 4 concurrent Claude windows don't collide on the same Galaxy S25.
- **Tiered tool surface** (BASIC / INTERMEDIATE / EXPERT, **143 tools** total) so 4B-class local LLMs aren't overwhelmed and Claude Desktop's tool-count ceiling doesn't drop your server.
- **Defense-in-depth image cap** that survived three production "2000 px API limit" incidents — including the case where an overnight bot bypassed `take_screenshot` and used raw `adb screencap`.
- **Patrol-first Flutter integration** with `system=true` for OS dialogs, `tap_and_verify` for the verify-after-action discipline, and YAML test plans the agent can author and re-run.
- **Production-ready out of the gate**: CycloneDX SBOM, pip-audit gating, structured JSON logs, Prometheus `/metrics`, k8s `/health` + `/ready`, Docker image, GitHub Action wrapper, 7 ADRs documenting load-bearing decisions.

## What's here

| Path | What |
|---|---|
| [`packages/phone-controll/`](packages/phone-controll/) | The flagship MCP. **143 tools** spanning device control, build/install/launch, Patrol-driven Flutter UI tests, **Flutter web** (web debug sessions + `run_lighthouse` + `audit_web_app`), AR/Vision, declarative YAML test plans, cross-session device locking, the **audit suite** (seniority/security/**performance**/i18n/dependencies/a11y/test-quality/web + 9-domain composite), the **senior-tester loop** (`design_test_plan` + `audit_test_quality`), and **runtime graders** (`ingest_frame_timeline` / `ingest_har` / `ingest_maestro_report`). |
| `packages/<future>/` | Future MCPs slot in here using the same shape (see [`docs/adding_an_mcp.md`](docs/adding_an_mcp.md)). |
| [`examples/templates/`](examples/templates/) | Shared YAML test-plan templates (smoke, ump-decline, ar-anchor, flutter-test-smoke). |
| [`examples/agent_loop.py`](examples/agent_loop.py) | Reference autonomous Plan→Build→Test→Verify loop using any OpenAI-compat local LLM. |
| [`skills/`](skills/) | Symlinks to the Claude Code skills that ship with these MCPs. |
| [`scripts/`](scripts/) | Fresh-laptop installer, doctor, and ops scripts. |
| [`docs/`](docs/) | Architecture, framework-extension recipe, MCP-extension recipe. |

## Why a monorepo

- **Atomic cross-MCP refactors** — change shared types in one PR.
- **One venv, one CI, one set of pre-commit hooks** boots everything.
- The HTTP adapter's existing sub-router pattern (e.g. `/dev-session/*`) lets future packages register their own routers without coordinating across repos.
- Easy to extract later: `git filter-repo --subdirectory-filter packages/<name>` peels any package back into its own repo.

## Getting started (developer machine, macOS)

```bash
git clone <this repo> ~/Desktop/flutter-dev-agents
cd ~/Desktop/flutter-dev-agents/packages/phone-controll
uv venv --python 3.11
uv pip install -e ".[dev,ar,http]"
pytest                                    # full unit suite, no toolchain needed

# Register the MCP with Claude Code
claude mcp add phone-controll -- \
  /Users/$(whoami)/Desktop/flutter-dev-agents/packages/phone-controll/.venv/bin/python \
  -m mcp_phone_controll
```

For a step-by-step "open VS Code → drive a real phone" walkthrough that
exercises every Tier A–F tool, see
[`docs/walkthrough-vscode-test.md`](docs/walkthrough-vscode-test.md).

## External prerequisites

See [`packages/phone-controll/README.md`](packages/phone-controll/README.md) for the full list. Briefly:

- **Android:** `adb` (`brew install --cask android-platform-tools`)
- **iOS:** Xcode + CLT, `pymobiledevice3 remote tunneld` running for developer-tier services
- **Flutter:** `flutter` on PATH; for Patrol: `dart pub global activate patrol_cli`
- **AR (optional):** `[ar]` extra installs OpenCV
- **HTTP adapter (optional):** `[http]` extra installs FastAPI + uvicorn

Run `check_environment` from any Claude Code session — it returns a structured doctor report with concrete fix commands for any red items.

## Topologies

- **Native macOS** for the human factory: real devices via USB, iOS simulators, multiple VS Code windows, multi-Claude concurrent sessions. Each Claude session owns its devices via the MCP's filesystem-coordinated locks.
- **Linux container** (planned, deferred): headless Android emulator + Flutter + Patrol + the MCP, for CI runners. See [`docs/architecture.md`](docs/architecture.md#container-topology).

## Status

- **`packages/phone-controll/` v0.10.0** — **143 tools** live on PyPI, **1034 hermetic unit tests** + real-device tests (gated on `MCP_REAL_DEVICE=1`). Field-tested across real Flutter projects (`docs/v030-field-test.md`); web debug + WDA-simulator + `audit_performance` live-verified on bike_news_room.
- **First-real-device patch release shipped May 2026** — fixed iOS 17+ `--rsd` routing, WDA team_id signing, Polish NBSP `tap_text`, raw-`adb screencap` recovery loop. See [`CHANGELOG.md`](CHANGELOG.md).
- Multi-window VS Code orchestration + debug sessions + WDA setup + cross-session device locks all in place.

## Real-developer multi-project workflow

A typical day on the factory laptop:

```
Claude #1 in checkaiapp/
  → open_project_in_ide("checkaiapp")     # spawns its own VS Code window
  → select_device(R3CYA05CHXB)            # acquires the lock on the Galaxy
  → start_debug_session(project_path=...)  # `flutter run --machine`, returns vm_service_uri
  → ...edit code, restart_debug_session, read_debug_log, repeat...
  → run_patrol_test (or run_test_plan with dev_iteration.yaml)
  → stop_debug_session, release_device, close_ide_window

Claude #2 in another_app/                  → emulator-5554, its own VS Code, its own debug
Claude #3 in third_app/                    → iPhone simulator UDID, its own VS Code, its own debug
```

Three independent debug sessions, three IDE windows, three locked devices, no collisions. The HTTP adapter exposes both the unified `/tools/*` surface and a focused `/dev-session/*` sub-router for agents that only care about the dev-iteration loop.

See [`examples/templates/dev_iteration.yaml`](examples/templates/dev_iteration.yaml) for a runnable plan template; [`docs/ios_setup.md`](docs/ios_setup.md) for the iPhone prerequisites (Developer Mode, DDI, tunneld, WebDriverAgent).

## Contributing

See [`docs/adding_a_framework.md`](docs/adding_a_framework.md) and [`docs/adding_an_mcp.md`](docs/adding_an_mcp.md) for the extension recipes. Both stay small (a few new files each) thanks to the Clean Architecture boundaries.

### Pre-commit hooks

Mirrors CI exactly — install once, never push a red build again:

```bash
uv pip install pre-commit
pre-commit install
pre-commit run --all-files   # one-time baseline; CI parity check
```

Three gates: `ruff` (lint+autofix), `pytest -q` (fast suite, no `tests/agent`), `generate_tool_catalogue --check` (refuses if `docs/tools.md` drifts from the live registry). See [`.pre-commit-config.yaml`](.pre-commit-config.yaml).

## Design

A shippable visual-asset brief pack lives in [`docs/design/`](docs/design/README.md) — six self-contained briefs (logo, social preview, landing page, architecture diagram, demo video, pitch deck) each with concrete specs + a Claude-designer prompt. Total ~12 person-days of design work to ship the full pack; the first 3 briefs (~7 days) cover 80% of the launch surface.

## License

Apache License 2.0 — see [`LICENSE`](LICENSE). Inbound contributions follow the same license; no separate CLA.

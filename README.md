# flutter-dev-agents

**The first MCP server that lets autonomous agents build, deploy and test Flutter apps on real iPhones and Android devices.**

[![tests](https://img.shields.io/badge/tests-904_passing-A6E22E?style=flat-square)](packages/phone-controll/tests)
[![license](https://img.shields.io/badge/license-Apache_2.0-F76C28?style=flat-square)](LICENSE)
[![MCP spec](https://img.shields.io/badge/MCP-2025--06--18-F76C28?style=flat-square)](https://modelcontextprotocol.io)
[![python](https://img.shields.io/badge/python-3.11+-3B4252?style=flat-square)](pyproject.toml)
[![PyPI](https://img.shields.io/pypi/v/mcp-phone-controll?style=flat-square&color=3B4252)](https://pypi.org/project/mcp-phone-controll/)
[![CI](https://img.shields.io/github/actions/workflow/status/michal-giza/flutter-dev-agents/ci.yml?branch=main&style=flat-square)](https://github.com/michal-giza/flutter-dev-agents/actions)

**137 tools** across Android (uiautomator2 + adb), iOS (WebDriverAgent + pymobiledevice3), Flutter (Patrol + `flutter run --machine`), and a **7-vertical opinionated audit suite** for shipping with confidence. Works with Claude Desktop, Claude Code, Cursor, or any MCP-aware host. **Composes with** Google's official Dart/Flutter MCP and Maestro MCP — see [the stack](docs/the-stack.md).

→ **[First 15 minutes](docs/GETTING-STARTED.md)** · **[The Stack](docs/the-stack.md)** · **[Senior-tester discipline](docs/senior-tester-discipline.md)** · **[Comparison vs other MCPs](docs/flutter-mcp-comparison.md)** · **[FAQ](docs/FAQ.md)** · **[Configuration](docs/CONFIGURATION.md)** · **[Operational gotchas](docs/operational-gotchas.md)** · **[Tools by category](docs/tools-by-category.md)** · **[Architecture](docs/architecture.md)**

## What's new in v0.4.0 (May 2026)

The **Maestro composition** release. We now sit explicitly on top of [Maestro](https://maestro.dev/) (mobile.dev's flow-based mobile test framework, whose MCP launched Feb 2026) — auditing what their flows produce rather than competing with them. Same posture for Google's official Dart/Flutter MCP.

- 🆕 **`audit_maestro_flow`** — lint Maestro YAML flows against 12 senior-tester rules (hardcoded locale strings, vacuous assertions, sleep_in_flow, missing failure paths, …)
- 🆕 **`ingest_maestro_report`** — parse Maestro execution reports (JUnit XML + Maestro JSON), surface flake / regression signals
- 🔧 **`audit_release_readiness`** — extended with a 6th `test_execution` domain (opt-in via `maestro_report_path`); failed flows propagate to `verdict=block`

See [the stack](docs/the-stack.md) for how the 4 MCPs compose end-to-end, and the [comparison memo](docs/flutter-mcp-comparison.md) for the full landscape analysis.

**Previous milestones:**
- **v0.3.1** — calibration patches from 3-project field test, signal:noise ~96%
- **v0.3.0** — the 7-vertical audit suite (seniority + security + i18n + supply chain + a11y + test-quality + composite gate) + senior-tester loop (`design_test_plan` + `audit_test_quality`)
- **v0.2.x** — initial PyPI release, multi-device locking, Patrol integration, AR/vision

---

## Why it matters

Mobile QA still loses 30–50% of its engineering hours to flaky selector maintenance ([Drizz industry survey, 2026](https://drizz.dev)). Agents can close that loop — but until now there was no production-grade MCP that gave them safe, structured access to real phones. This is that MCP:

- **Cross-session device locking** so 4 concurrent Claude windows don't collide on the same Galaxy S25.
- **Tiered tool surface** (BASIC / INTERMEDIATE / EXPERT, **137 tools** total) so 4B-class local LLMs aren't overwhelmed and Claude Desktop's tool-count ceiling doesn't drop your server.
- **Defense-in-depth image cap** that survived three production "2000 px API limit" incidents — including the case where an overnight bot bypassed `take_screenshot` and used raw `adb screencap`.
- **Patrol-first Flutter integration** with `system=true` for OS dialogs, `tap_and_verify` for the verify-after-action discipline, and YAML test plans the agent can author and re-run.
- **Production-ready out of the gate**: CycloneDX SBOM, pip-audit gating, structured JSON logs, Prometheus `/metrics`, k8s `/health` + `/ready`, Docker image, GitHub Action wrapper, 7 ADRs documenting load-bearing decisions.

## What's here

| Path | What |
|---|---|
| [`packages/phone-controll/`](packages/phone-controll/) | The flagship MCP. **137 tools** spanning device control, build/install/launch, Patrol-driven Flutter UI tests, AR/Vision, declarative YAML test plans, cross-session device locking, the **7-vertical audit suite** (seniority/security/i18n/dependencies/a11y/test-quality + composite), the **senior-tester loop** (`design_test_plan` + `audit_test_quality`), and **Maestro composition** (`audit_maestro_flow` + `ingest_maestro_report`). |
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

- **`packages/phone-controll/` v0.4.0** — **137 tools** live on PyPI, **904 hermetic unit tests** + real-device tests (gated on `MCP_REAL_DEVICE=1`). Field-tested across 3 real Flutter projects (`docs/v030-field-test.md`); composite signal:noise ~96% after v0.3.1 calibration.
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

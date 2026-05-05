# flutter-dev-agents

Umbrella repository for **MCP servers and agent tooling** that drive the full Flutter dev-and-test workflow on real devices, emulators, simulators — for human-in-the-loop sessions in Claude Code AND for autonomous local-LLM agents.

## What's here

| Path | What |
|---|---|
| [`packages/phone-controll/`](packages/phone-controll/) | The flagship MCP. 50+ tools for device control, build/install/launch, Patrol-driven Flutter UI tests, AR/Vision, declarative YAML test plans, cross-session device locking, autonomous-agent surface. |
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

- `packages/phone-controll/`: 50+ tools live, 125+ tests passing, used in production-like factory workflow.
- Dev-session module (debug session control + multi-window VS Code orchestration): in progress per [the active plan](https://github.com/anthropics/claude-code).

## Contributing

See [`docs/adding_a_framework.md`](docs/adding_a_framework.md) and [`docs/adding_an_mcp.md`](docs/adding_an_mcp.md) for the extension recipes. Both stay small (a few new files each) thanks to the Clean Architecture boundaries.

## License

TBD.

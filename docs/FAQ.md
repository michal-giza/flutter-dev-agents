# FAQ

The questions that come up most often before someone installs.

## Will it work for me?

**Q: What hosts is this tested against?**
A: Claude Desktop, Claude Code, Cursor, and any HTTP client speaking the MCP protocol (n8n, custom agents). Also runs against any OpenAI-compat local LLM via the bundled HTTP adapter — Ollama, vLLM, LM Studio, OpenAI itself.

**Q: macOS only?**
A: For full functionality (iOS + Android), yes — iOS device control needs Xcode. For Android-only, Linux works fine. Windows runs the package itself but isn't tested end-to-end.

**Q: Which Flutter versions are supported?**
A: 3.13+ has been tested. Earlier 3.x versions probably work but aren't on the matrix. Dart 3 is required for Patrol.

**Q: Do I need Patrol installed in my app to use this?**
A: For UI-level testing (`run_patrol_test`, `run_patrol_suite`), yes — Patrol is the only Flutter UI driver that works through a real WebDriver runner on both iOS and Android. For device-level control (screenshots, taps, app lifecycle, logs), no — `uiautomator2` (Android) and `WebDriverAgent` (iOS) are bundled.

**Q: Does it work without a real device?**
A: Yes. Android emulators and iOS simulators are first-class. The 5 "real device" tests in `tests/integration_real/` are gated on `MCP_REAL_DEVICE=1` and only run when a physical phone is plugged in.

**Q: Multiple Flutter projects? Multiple Claude windows at once?**
A: Yes — that's the headline feature. The MCP uses filesystem-based per-device locks so N concurrent Claude sessions can drive N different phones without colliding. See the [`Real-developer multi-project workflow`](../README.md#real-developer-multi-project-workflow) section of the README.

**Q: Cost?**
A: Apache 2.0, free. The only cost is the LLM you choose to drive it — Claude (paid), or a local LLM (free).

---

## How does it compare to…?

**Q: …Maestro?**
A: Maestro is a YAML-driven mobile test runner — great for declarative scripted tests, no LLM in the loop. This MCP is the opposite: agent-driven, exploratory, conversational. You'd use Maestro for "every release, run this exact 40-step test on the staging build"; you'd use this MCP for "the auth flow broke yesterday, figure out why and propose a fix." They can coexist.

**Q: …Appium?**
A: Appium is a server protocol that several test runners speak. WebDriverAgent (the iOS driver this MCP uses) was originally an Appium component. The relationship is "this MCP uses the same underlying drivers Appium uses, but exposes them as MCP tools instead of a webdriver protocol." If your team already has Appium-based suites, this MCP doesn't replace them — it complements with agent control.

**Q: …Patrol on its own?**
A: Patrol is a Dart test framework that lets your tests interact with the OS layer (system dialogs, permissions, deep links). This MCP runs Patrol tests AND wraps them with: device locking, multi-project orchestration, hot-reload control, agent-readable structured failures, screenshot/log capture. Use Patrol alone for `flutter test` CI; use this MCP when you want an agent to drive Patrol.

**Q: …`computer-use` or browser MCPs?**
A: Different surfaces. `computer-use` drives macOS desktops. Browser MCPs drive Chrome / Safari. This MCP drives phones. You can run all three in the same Claude session — the BASIC-tier `inspect_image_safety` + `compress_png` tools in this MCP specifically handle screenshots produced by other MCPs.

**Q: …BrowserStack / Sauce Labs?**
A: Cloud farms run pre-recorded tests at $/minute. This MCP runs locally on your laptop or CI runner. Use a cloud farm when you need 50 OS-version combinations; use this MCP when you want one developer + one phone + one agent iterating fast.

---

## Practical concerns

**Q: What about security? My phone is on the same laptop the LLM is on.**
A: Three protections: (1) every tool that rewrites files has a path-traversal allowlist (`MCP_COMPRESS_ALLOWED_ROOTS` etc.) so a prompt-injection upstream can't write outside known-safe roots; (2) the only outbound network tool, `notify_webhook`, requires an explicit allowlist (`MCP_WEBHOOK_ALLOWLIST`) — off by default; (3) `patch_apply_safe` runs subprocess with `shell=False` and a 7-test injection audit. The full threat model is in [`SECURITY.md`](../SECURITY.md).

**Q: My local backend at localhost — how do I reach it from the device under test?**
A: iOS simulator: `http://127.0.0.1:N` works (sim shares host loopback). Android emulator: `http://10.0.2.2:N` (emulator's host-loopback alias). Physical Android with `adb reverse tcp:N tcp:N`: `127.0.0.1:N` again. See [`operational-gotchas.md`](operational-gotchas.md) for the canonical `--dart-define=BACKEND_BASE=…` pattern.

**Q: I see "2000px API limit exceeded" errors after a few screenshots.**
A: The MCP's `take_screenshot` caps at 1600 px by default. If you (or another MCP) wrote an oversized PNG some other way, call `inspect_image_safety(path="…")` to confirm and `compress_png(path="…", max_dim=1600)` to fix. Both are BASIC-tier so always available. Background: [`runbook.md` §1](runbook.md).

**Q: The Connectors panel in Claude Desktop shows "no tools available" — what now?**
A: Tool-count ceiling. Add `"env": { "MCP_TOOL_TIER": "basic" }` to your `phone-controll` entry in `claude_desktop_config.json`, fully quit Claude Desktop (cmd+Q on macOS — closing the window is not enough), relaunch.

**Q: How do I see logs from the MCP itself?**
A: Stdio mode logs to stderr; pipe to a file or your terminal. HTTP mode logs to stderr of the `mcp-phone-controll-http` process. Set `MCP_LOG_FORMAT=json` for structured one-event-per-line JSON suitable for Datadog / Honeycomb / Loki.

**Q: How do I clean up the artifacts dir?**
A: It accumulates `.orig.png` preservation copies. Run `prune_originals(older_than_days=14)` from any agent session, or `disk_usage` first to see what's there. Default retention is configurable via `MCP_ORIG_RETENTION_DAYS`.

**Q: Why does `setup_webdriveragent` take 10+ minutes the first time?**
A: It clones the Appium WDA repo (~300 MB) and runs `xcodebuild build-for-testing`, which compiles WebDriverAgent for your specific device. Subsequent runs short-circuit on a marker file (`.mcp-phone-controll-built` next to the WDA project). Per-UDID — adding a new device triggers a fresh build for that device only.

---

## Building on top of it

**Q: Can I write my own tool?**
A: Yes — see [`adding_a_framework.md`](adding_a_framework.md) for adding a new test framework (XCUITest, Espresso, Detox) and [`adding_an_mcp.md`](adding_an_mcp.md) for adding a sibling MCP under `packages/`. Both stay small (~5 files each) thanks to the Clean Architecture boundaries.

**Q: Can I run this in CI?**
A: Yes — the GitHub Action wrapper in `.github/actions/run-test-plan/` lets you run a YAML test plan as a single workflow step. Linux runners need an Android emulator container alongside; macOS runners can use iOS simulators directly. See [`docs/n8n-integration.md`](n8n-integration.md) for a non-GitHub example.

**Q: Can I drive it from a non-Claude agent?**
A: Yes. The HTTP adapter exposes every tool at `/tools/<name>` with OpenAI-compatible function-call schemas. Set `MCP_LLM_BASE_URL` to your LLM endpoint and the adapter forwards `/agent/chat` requests too. See [`INTEGRATIONS.md`](../INTEGRATIONS.md).

**Q: I'm building an agent loop. What's a good starting point?**
A: Three reference loops in `examples/`:
- `agent_loop.py` — Ollama / vLLM / LM Studio (general OpenAI-compat)
- `agent_loop_mlx.py` — Apple-Silicon MLX models (qwen, mistral)
- `agent_loop_small_llm.py` — 4B-class models with `MCP_TOOL_TIER=basic` for constrained surfaces

---

## Project meta

**Q: Where does this live?**
A: https://github.com/michal-giza/flutter-dev-agents (umbrella) · https://pypi.org/project/mcp-phone-controll/ (PyPI).

**Q: How do I report a bug?**
A: GitHub Issues. For suspected security vulnerabilities, follow [`SECURITY.md`](../SECURITY.md) — `msquaregiza@gmail.com` with `[flutter-dev-agents SECURITY]` in the subject line.

**Q: How do I contribute?**
A: See [`CONTRIBUTING.md`](../CONTRIBUTING.md). Short version: pre-commit hooks mirror CI exactly; pass `pytest -q` and `ruff check`; tools have a tier classification that gets pinned by `test_basic_tool_descriptions_within_word_limit`.

**Q: Is there a Slack / Discord?**
A: Not yet — for now, file issues on GitHub or DM the maintainer (`msquaregiza@gmail.com`).

**Q: Will there be a SaaS version / hosted offering?**
A: No plans. The product is the package; you run it on your machine or your CI runner. The MCP protocol's whole point is local-first.

**Q: What's the roadmap?**
A: `docs/master-plan.md` has the long-form roadmap. Top items: iOS-only-Linux container via remote tunneld, Detox + XCUITest framework recipes, hosted device-farm bridge for CI scale.

**Q: License?**
A: Apache 2.0. Inbound contributions follow the same license; no separate CLA.

# Examples

Copy-paste recipes covering the most common ways to drive
`mcp-phone-controll`. Each section is self-contained.

## Quick index

| You want to… | Section |
|---|---|
| Try it without writing code | [Prompt recipes](#prompt-recipes) |
| Run a declarative test plan | [YAML test plans](#yaml-test-plans) |
| Build an autonomous agent loop | [Agent loops](#agent-loops) |
| Drive it from a non-Claude tool | [HTTP adapter](#http-adapter) |
| See a complete end-to-end flow | [End-to-end walkthrough](#end-to-end-walkthrough) |
| Read fully-worked scenarios | [`scenarios/`](scenarios/) (5-min smoke, Polish-locale repro, multi-project debug loop) |

---

## Prompt recipes

Paste these directly into Claude Desktop / Claude Code after registering the MCP. No Python needed.

### Smoke test — does it work?

```
Using phone-controll, run mcp_ping, then list_devices, then take a
screenshot of the first device. Tell me where the file landed.
```

Expected: 3 tool calls returning `{ok: true, ...}` and a PNG path under `~/.mcp_phone_controll/sessions/`.

### Tap-and-verify a button

```
Using phone-controll:
- Select the connected Android device.
- Launch com.example.myapp.
- Wait for the "Sign in" button to appear (timeout 10s).
- Tap "Sign in" and verify the screen now shows "Welcome".
- If the verify failed, dump the UI tree so I can see what's on
  screen.
- Release the device.
```

Tools used: `select_device`, `launch_app`, `wait_for_element`, `tap_and_verify`, `dump_ui` (on failure), `release_device`.

### Run a Patrol test

```
Using phone-controll, run integration_test/auth_test.dart against
the connected device. Capture screenshots and logs. Tell me how
many tests passed and which (if any) failed.
```

Tools used: `select_device`, `run_patrol_test`, `release_device`. The MCP captures structured pass/fail per `testWidgets` block.

### Reproduce a Polish-locale bug

```
Using phone-controll on the Polish-locale device:
- Launch the app.
- Tap_text "Podczas używania aplikacji" (it's a system permission
  dialog — pass system=true).
- Take a screenshot.
- Read the last 30 seconds of logs and tell me if any errors
  appeared.
```

Tools used: `launch_app`, `tap_text` (with `system=true` for OS dialogs), `take_screenshot`, `read_logs`.

### Multi-project parallel work (4 concurrent Claude windows)

```
# Window 1 (in checkaiapp/)
Using phone-controll, work in /Users/me/Desktop/checkaiapp.
Select the Galaxy S25 (serial R3CYA05CHXB), start a debug session,
hot-reload, watch the debug log.

# Window 2 (in another_app/)
Using phone-controll, work in /Users/me/Desktop/another_app.
Select emulator-5554, start a debug session, run integration tests.

# Window 3 (orchestrator)
Using phone-controll, run list_locks and list_debug_sessions.
Give me a summary table of who's doing what.
```

The cross-session locks prevent collisions. Window 3 sees the union of state.

---

## YAML test plans

Declarative test plans run via `run_test_plan`. Six templates ship with the package:

| Template | What it does |
|---|---|
| `templates/smoke.yaml` | install + launch + screenshot |
| `templates/ump_decline.yaml` | UMP planned-decline flow with `VERDICT_DECLINED` capture |
| `templates/ar_anchor.yaml` | camera permission + AR anchor placement |
| `templates/flutter_test_smoke.yaml` | `flutter test` + Patrol-style capture |
| `templates/dev_iteration.yaml` | open IDE → debug-session → hot-reload → debug-log → stop |
| `templates/ar_dev_loop.yaml` | AR session validate → infer pose → screenshot loop |

### Run a plan from Python

```python
import asyncio
from mcp_phone_controll.container import build_runtime

async def main():
    _, dispatcher = build_runtime()
    res = await dispatcher.dispatch(
        "run_test_plan",
        {"plan_path": "examples/templates/ump_decline.yaml"},
    )
    print(res)

asyncio.run(main())
```

### Run a plan from a Claude prompt

```
Using phone-controll, run the test plan at
examples/templates/dev_iteration.yaml against my Flutter project at
/Users/me/Desktop/checkaiapp. Validate first, then run, then
summarize the session.
```

### Authoring your own plan

Plans are YAML, schema available via `describe_capabilities`:

```yaml
apiVersion: phone-controll/v1
kind: TestPlan
metadata:
  name: my-flow
spec:
  device: { platform: android, pool: any }
  project: { path: /Users/me/Desktop/checkaiapp }
  phases:
    - phase: PRE_FLIGHT
    - phase: CLEAN
      package_id: com.example.myapp
    - phase: UNDER_TEST
      driver: { kind: flutter_test, target: integration_test/auth_test.dart }
      capture: [screenshot, logs]
    - phase: VERDICT
  report: { format: junit }
```

Validate before running:

```
Using phone-controll, run validate_test_plan against my-flow.yaml.
Show me any warnings.
```

---

## Agent loops

Three reference loops, pick the one that matches your stack.

### `agent_loop.py` — Ollama / vLLM / LM Studio (most common)

```bash
ollama pull qwen2.5:7b      # 4.7 GB, handles tool-calling reliably

mcp-phone-controll-http --port 8765 &

OLLAMA_BASE_URL=http://localhost:11434/v1 \
MODEL=qwen2.5:7b \
PACKAGE_ID=com.example.myapp \
PROJECT_PATH=/Users/me/Desktop/myapp \
python examples/agent_loop.py
```

The loop:
1. Reads the prompt template.
2. Calls the LLM with the MCP's tool catalog.
3. Dispatches each tool the LLM picks.
4. Feeds the structured envelope back into the LLM.
5. Stops on `ok: false next_action: …` (HARD STOP rule from SKILL).

Transcripts persist to `~/.mcp_phone_controll/agent-runs/<sid>.json`.

### `agent_loop_mlx.py` — Apple-Silicon MLX (zero GPU setup)

```bash
pip install mlx-lm
python -m mlx_lm.server --model mistralai/Mistral-7B-Instruct-v0.3 --port 8080

LLM_BASE_URL=http://localhost:8080/v1 \
MODEL=mistralai/Mistral-7B-Instruct-v0.3 \
PACKAGE_ID=com.example.myapp \
python examples/agent_loop_mlx.py
```

Same logic as `agent_loop.py`, tuned defaults for MLX's tokenization.

### `agent_loop_small_llm.py` — 4B-class models with discipline

For models that can only handle ~30 tools and need explicit recommended sequences:

```bash
# Set the tier on the HTTP adapter side
MCP_TOOL_TIER=basic mcp-phone-controll-http --port 8765 &

LLM_BASE_URL=http://localhost:11434/v1 \
MODEL=qwen2.5:3b \
PACKAGE_ID=com.example.myapp \
python examples/agent_loop_small_llm.py
```

Adds: stronger system prompt with `recommended_sequence_for_level("basic")`, automatic refusal-recovery hints from `next_action`, periodic `summarize_session` checkpoints.

---

## HTTP adapter

Use this when you want to drive the MCP from anything that speaks HTTP — n8n, a custom dashboard, raw curl, a non-Claude AI agent.

### Start the server

```bash
# Local dev — defaults to 127.0.0.1:8765
mcp-phone-controll-http

# Production — bind 0.0.0.0 + require API key
MCP_HTTP_API_KEY=$(openssl rand -hex 32) \
MCP_HTTP_HOST=0.0.0.0 \
mcp-phone-controll-http
```

### List available tools

```bash
curl -fsS http://localhost:8765/tools | jq '.tools[].name' | head -10
```

### Call a tool

```bash
curl -fsS http://localhost:8765/tools/take_screenshot \
  -H 'Content-Type: application/json' \
  -H "X-Api-Key: ${MCP_HTTP_API_KEY:-}" \
  -d '{"label": "smoke-test"}'
```

Returns the standard envelope:

```json
{
  "ok": true,
  "data": {"path": "/Users/me/.mcp_phone_controll/sessions/abc/screenshot-smoke-test-001.png"},
  "tool": "take_screenshot",
  "elapsed_s": 0.42
}
```

### Endpoints summary

| Path | What |
|---|---|
| `GET /health` | Lightweight alive-check (k8s liveness) |
| `GET /ready` | Deeper ready-check including image-cap backend |
| `GET /metrics` | Prometheus exposition format |
| `GET /tools` | List tools with OpenAI-compat function-call schemas |
| `POST /tools/<name>` | Dispatch a single tool |
| `POST /dev-session/<name>` | Subset focused on dev-iteration loop |
| `POST /agent/chat` | OpenAI-compat chat endpoint (requires `MCP_LLM_BASE_URL`) |

Full reference in [`../INTEGRATIONS.md`](../INTEGRATIONS.md).

---

## End-to-end walkthrough

For a complete scripted session — open Claude Code in VS Code, build a Flutter app, install it on a real phone, drive it through hot-reload + Patrol tests, capture artifacts, summarize — read [`../docs/walkthrough-vscode-test.md`](../docs/walkthrough-vscode-test.md).

It's the canonical "I have an hour and want to see what's possible" doc.

---

## Got an example to share?

PRs welcome. Drop a new `.md` or `.py` here, link to it from the index table at the top, and update `examples/README.md` to mention it. See [`../CONTRIBUTING.md`](../CONTRIBUTING.md).

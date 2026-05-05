# mcp-phone-controll examples

## Plan templates

Ready-to-fill YAML test plans (apiVersion `phone-controll/v1`):

- `templates/smoke.yaml` — install + launch + screenshot
- `templates/ump_decline.yaml` — UMP planned-decline flow with VERDICT_DECLINED capture
- `templates/ar_anchor.yaml` — camera permission + AR anchor placement

Use them via:

```python
from mcp_phone_controll.container import build_runtime
import asyncio

async def main():
    _, dispatcher = build_runtime()
    res = await dispatcher.dispatch(
        "run_test_plan",
        {"plan_path": "examples/templates/ump_decline.yaml"},
    )
    print(res)

asyncio.run(main())
```

Or via the HTTP adapter:

```bash
curl -X POST http://localhost:8765/tools/run_test_plan \
  -H 'Content-Type: application/json' \
  -d '{"plan_path": "examples/templates/ump_decline.yaml"}'
```

## Reference autonomous agent loop

`agent_loop.py` is a minimal Plan → Build → Test → Verify loop using any
OpenAI-compat local LLM (Ollama, vLLM, LM Studio, ...).

### Quick start with Ollama

```bash
# 1. pull a small model that handles tool-calling
ollama pull qwen2.5:7b

# 2. start the MCP HTTP adapter
mcp-phone-controll-http --port 8765

# 3. run the loop
OLLAMA_BASE_URL=http://localhost:11434/v1 \
MODEL=qwen2.5:7b \
PACKAGE_ID=pl.openclaw.myapp \
PROJECT_PATH=/path/to/flutter/project \
python examples/agent_loop.py
```

The loop writes a JSON transcript to `~/.mcp_phone_controll/agent-runs/`.

### Other backends

The script reads `LLM_BASE_URL` as a generic alternative to `OLLAMA_BASE_URL`:

```bash
LLM_BASE_URL=http://localhost:8000/v1   MODEL=...   python examples/agent_loop.py   # vLLM
LLM_BASE_URL=http://localhost:1234/v1   MODEL=...   python examples/agent_loop.py   # LM Studio
```

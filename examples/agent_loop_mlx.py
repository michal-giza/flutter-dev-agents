"""Reference autonomous loop for Apple Silicon via MLX-LM + Qwen 2.5.

Differences from `agent_loop_small_llm.py`:
  - Uses MLX-LM's OpenAI-compatible server (built into MLX 0.20+) so the
    same OpenAI tool-calling contract works locally with zero changes.
  - Calls `mcp_ping` first to detect stale-subprocess, then
    `set_agent_profile(name="qwen2.5-7b")` to flip every per-agent knob
    to the recommended setting for the model in one tool call.
  - Stops after 15 turns regardless (small models drift on long traces).

Setup:

    # 1. Install MLX-LM + a tool-calling Qwen model
    pip install mlx-lm
    mlx_lm.server --model mlx-community/Qwen2.5-7B-Instruct-4bit --port 8080

    # 2. Run the MCP HTTP adapter
    mcp-phone-controll-http --port 8765

    # 3. Run this loop
    MLX_BASE_URL=http://localhost:8080/v1 \
    MODEL=mlx-community/Qwen2.5-7B-Instruct-4bit \
    PACKAGE_ID=pl.openclaw.myapp \
    PROJECT_PATH=/path/to/flutter/project \
    python examples/agent_loop_mlx.py

Why this exists separately from `agent_loop_small_llm.py`: MLX has
quirks around tool-call schema strictness that benefit from
`MCP_STRICT_TOOLS=1` (the set_agent_profile call below handles that).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx


SYSTEM_PROMPT = """You drive a Flutter dev environment via tool calls.
You're a 4B-class model running on MLX. Keep reasoning short.

ALWAYS follow this checklist, ONE TOOL CALL PER TURN:

1. mcp_ping                              — verify the MCP is current
2. set_agent_profile(name="qwen2.5-7b")  — apply MLX-friendly settings
3. describe_capabilities(level="basic")  — see your 18 BASIC tools
4. check_environment                     — halt on any red item
5. inspect_project(project_path=$PROJECT_PATH)
6. list_devices, select_device(serial=...)
7. new_session(label="run-<short_id>")
8. prepare_for_test(package_id=$PACKAGE_ID)
9. run_test_plan(plan_path=$PLAN_PATH)    — declarative path
10. summarize_session
11. release_device

When a tool returns ok=false, switch on error.next_action. NEVER guess.
- next_action="restart_mcp"             → STOP and report (you're stale)
- next_action="install_image_backend"   → STOP and report (env broken)
- next_action="fix_arguments"           → copy error.details.corrected_example
- next_action="capture_diagnostics"     → take_screenshot + read_logs
- empty / "ask_user"                    → STOP and report

Rules:
- Never call tap_text for app UI (use tap_and_verify or run_patrol_test)
- Never hardcode display text (assume Polish phone)
- Always end with release_device
- After 12 turns: write the report and stop

Final response: a single JSON object
{ "verdict": "PASS" | "FAIL" | "BLOCKED",
  "evidence": [list of artifact paths],
  "diagnosis": "<one paragraph>" }
"""


def main() -> int:
    base_url = os.environ.get("MLX_BASE_URL") or os.environ.get("LLM_BASE_URL")
    model = os.environ.get(
        "MODEL", "mlx-community/Qwen2.5-7B-Instruct-4bit"
    )
    if not base_url:
        print(
            "set MLX_BASE_URL (or LLM_BASE_URL). Example: "
            "http://localhost:8080/v1 (mlx_lm.server default)",
            file=sys.stderr,
        )
        return 2

    mcp_http = os.environ.get("MCP_HTTP_BASE_URL", "http://127.0.0.1:8765")
    project_path = os.environ.get("PROJECT_PATH", "/path/to/flutter/project")
    package_id = os.environ.get("PACKAGE_ID", "REPLACE_PACKAGE_ID")
    plan_path = os.environ.get(
        "PLAN_PATH", "examples/templates/flutter_test_smoke.yaml"
    )

    out_dir = Path.home() / ".mcp_phone_controll" / "agent-runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now()
    out_path = out_dir / started.strftime("%Y%m%d-%H%M%S-mlx-run.json")

    with httpx.Client(timeout=300) as client:
        # Pull the BASIC subset only — saves context for 4B models.
        cap = (
            client.post(
                f"{mcp_http}/tools/describe_capabilities",
                json={"level": "basic"},
            )
            .raise_for_status()
            .json()
        )
        allowed_names = set(cap["data"]["tool_subset"])
        # Strict-mode schemas — MLX models with proper tool-grammar
        # support do dramatically better with `strict: true`.
        all_tools = (
            client.get(f"{mcp_http}/tools?strict=true").raise_for_status().json()
        )
        tools = [t for t in all_tools if t["function"]["name"] in allowed_names]

        user = (
            f"PROJECT_PATH: {project_path}\n"
            f"PACKAGE_ID: {package_id}\n"
            f"PLAN_PATH: {plan_path}\n\n"
            "Run the checklist. Start with mcp_ping."
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ]

        for turn in range(15):
            resp = (
                client.post(
                    f"{base_url.rstrip('/')}/chat/completions",
                    json={
                        "model": model,
                        "messages": messages,
                        "tools": tools,
                        "tool_choice": "auto",
                        "parallel_tool_calls": False,
                    },
                )
                .raise_for_status()
                .json()
            )
            choice = (resp.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            messages.append(msg)

            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                final = msg.get("content") or "(no content)"
                _write_report(out_path, started, model, final, messages)
                print(f"agent run done → {out_path}")
                return 0

            for tc in tool_calls:
                fn = tc.get("function") or {}
                name = fn.get("name", "")
                raw = fn.get("arguments") or "{}"
                args = json.loads(raw) if isinstance(raw, str) else raw
                envelope = (
                    client.post(f"{mcp_http}/tools/{name}", json=args)
                    .raise_for_status()
                    .json()
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id"),
                        "name": name,
                        "content": json.dumps(envelope, ensure_ascii=False),
                    }
                )

        _write_report(out_path, started, model, "max turns reached", messages)
        print(f"agent ran out of turns → {out_path}", file=sys.stderr)
        return 1


def _write_report(path: Path, started, model: str, final, messages) -> None:
    path.write_text(
        json.dumps(
            {
                "started": started.isoformat(),
                "finished": datetime.now().isoformat(),
                "model": model,
                "final": final,
                "messages": messages,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    sys.exit(main())

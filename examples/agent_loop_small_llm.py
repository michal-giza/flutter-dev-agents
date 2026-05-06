"""Reference autonomous loop tuned for 4B-class local LLMs.

Differences from the general examples/agent_loop.py:
  - Pulls the BASIC tool subset only (≤ 18 tools) via describe_capabilities(level="basic")
  - One tool call per turn (no parallel)
  - Aggressive `next_action` switch instead of free-form reasoning
  - Stops after 12 turns regardless (small models drift)
  - Writes a structured JSON report at the end

Run:
    mcp-phone-controll-http --port 8765         # in another terminal
    OLLAMA_BASE_URL=http://localhost:11434/v1 \
    MODEL=qwen2.5:7b \
    PACKAGE_ID=pl.openclaw.myapp \
    PROJECT_PATH=/path/to/flutter/project \
    python examples/agent_loop_small_llm.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx


SYSTEM_PROMPT = """You drive a Flutter dev environment via tool calls. You are a
small (4B) model — keep your reasoning short and your tool calls precise.

ALWAYS follow this checklist, ONE TOOL CALL PER TURN:

1. describe_capabilities(level="basic")  — read the allowed tool list
2. check_environment                      — halt on any red item; cite the fix
3. inspect_project(project_path=$PROJECT_PATH)
4. list_devices, select_device(serial=...)
5. new_session(label="run-<short_id>")
6. prepare_for_test(package_id=$PACKAGE_ID)
7. validate_test_plan(plan_path=$PLAN_PATH)  — fix and retry if invalid
8. run_test_plan(plan_path=$PLAN_PATH)
9. session_summary
10. release_device

When a tool returns ok=false, switch on error.next_action. NEVER guess.
If next_action is "fix_arguments", copy error.details.corrected_example into
your next call exactly. If next_action is empty or "ask_user", STOP and report.

Never:
- call tap_text for app UI (only system UI)
- hardcode display text (assume Polish phone)
- skip release_device at the end
- author a YAML plan from scratch — use a template from examples/templates/

Final response: a single JSON object
{ "verdict": "PASS"|"FAIL"|"BLOCKED",
  "evidence": [list of artifact paths],
  "diagnosis": "<one paragraph>" }
"""


def main() -> int:
    base_url = os.environ.get("OLLAMA_BASE_URL") or os.environ.get("LLM_BASE_URL")
    model = os.environ.get("MODEL", "qwen2.5:7b")
    if not base_url:
        print(
            "set OLLAMA_BASE_URL (or LLM_BASE_URL) to a local OpenAI-compat endpoint",
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
    out_path = out_dir / started.strftime("%Y%m%d-%H%M%S-small-llm-run.json")

    with httpx.Client(timeout=300) as client:
        # Fetch only the BASIC tool subset — saves context for 4B models.
        cap = (
            client.post(
                f"{mcp_http}/tools/describe_capabilities",
                json={"level": "basic"},
            )
            .raise_for_status()
            .json()
        )
        allowed_names = set(cap["data"]["tool_subset"])
        all_tools = client.get(f"{mcp_http}/tools").raise_for_status().json()
        tools = [
            t for t in all_tools if t["function"]["name"] in allowed_names
        ]

        user = (
            f"PROJECT_PATH: {project_path}\n"
            f"PACKAGE_ID: {package_id}\n"
            f"PLAN_PATH: {plan_path}\n\n"
            "Run the checklist."
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ]

        for turn in range(12):
            resp = (
                client.post(
                    f"{base_url.rstrip('/')}/chat/completions",
                    json={
                        "model": model,
                        "messages": messages,
                        "tools": tools,
                        "tool_choice": "auto",
                        # Force one tool call per turn — small models do better
                        # with serialized actions than with parallel call lists.
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

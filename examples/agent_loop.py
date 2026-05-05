"""Reference autonomous agent loop using mcp-phone-controll's HTTP adapter.

Framework-agnostic: works with any OpenAI-compat endpoint (Ollama / vLLM /
LM Studio / llama.cpp). Bring-your-own-model.

Run:
    # 1. start the MCP HTTP adapter
    mcp-phone-controll-http --port 8765

    # 2. point this script at any local LLM
    OLLAMA_BASE_URL=http://localhost:11434/v1 \\
    MODEL=qwen2.5:7b \\
    PACKAGE_ID=pl.openclaw.myapp \\
    PROJECT_PATH=/path/to/flutter/project \\
    python examples/agent_loop.py

Loops Plan -> Build -> Test -> Verify -> Report and writes JSON output to
~/.mcp_phone_controll/agent-runs/.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx


SYSTEM_PROMPT = """You are a phone-testing agent driving the mcp-phone-controll MCP via tools.

ALWAYS follow this loop:
  1. Call check_environment first. If any check returns ok=false, surface its
     `next_action` and STOP. Do not retry blindly.
  2. Call describe_capabilities. Use the result to plan only what is supported.
  3. Call inspect_project to confirm the project type and frameworks.
  4. Call new_session with a meaningful label.
  5. Call list_devices, then select_device for the appropriate platform.
  6. Use prepare_for_test (a single composite call) for the CLEAN phase.
  7. Drive the test via run_patrol_test or run_test_plan when the project has
     Patrol; never hardcode display text in tap_text for app UI.
  8. On any decline-branch test, the test outcome is decided — capture ONE
     screenshot and ONE log slice, then call session_summary and return the
     report. Do NOT continue past the gate.
  9. If a tool returns ok=false, follow `next_action` from the error envelope.
     If `next_action` is "ask_user" or you genuinely don't know, return.

Return a final JSON object:
  { "verdict": "PASS" | "FAIL" | "BLOCKED" | "DECLINED",
    "session_summary_path": "<path>",
    "evidence": ["<screenshot>", ...],
    "diagnosis": "<one-paragraph human summary>" }
"""


def _default_user_prompt() -> str:
    package_id = os.environ.get("PACKAGE_ID", "REPLACE_PACKAGE_ID")
    project_path = os.environ.get("PROJECT_PATH", "/path/to/flutter/project")
    return f"""Run a smoke test against the connected Android device.

Project path: {project_path}
Package id:   {package_id}

Plan, execute, and report. Stop on first failure that has a clear next_action."""


def main() -> int:
    base_url = os.environ.get("OLLAMA_BASE_URL") or os.environ.get("LLM_BASE_URL")
    model = os.environ.get("MODEL", "qwen2.5:7b")
    if not base_url:
        print(
            "set OLLAMA_BASE_URL (or LLM_BASE_URL) to a local OpenAI-compat endpoint"
            " (e.g. http://localhost:11434/v1)",
            file=sys.stderr,
        )
        return 2

    mcp_http = os.environ.get("MCP_HTTP_BASE_URL", "http://127.0.0.1:8765")
    out_dir = Path.home() / ".mcp_phone_controll" / "agent-runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now()
    out_path = out_dir / started.strftime("%Y%m%d-%H%M%S-agent-run.json")

    with httpx.Client(timeout=300) as client:
        # 1. fetch tool schemas from the MCP HTTP adapter
        tools = client.get(f"{mcp_http}/tools").raise_for_status().json()

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _default_user_prompt()},
        ]

        for turn in range(20):
            resp = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                json={
                    "model": model,
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": "auto",
                },
            ).raise_for_status().json()
            choice = (resp.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            messages.append(msg)

            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                # final answer — write and exit
                final = msg.get("content") or "(no content)"
                out_path.write_text(
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
                print(f"agent run done → {out_path}")
                return 0

            for tc in tool_calls:
                fn = tc.get("function") or {}
                name = fn.get("name", "")
                raw = fn.get("arguments") or "{}"
                args = json.loads(raw) if isinstance(raw, str) else raw
                envelope = client.post(
                    f"{mcp_http}/tools/{name}", json=args
                ).raise_for_status().json()
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id"),
                        "name": name,
                        "content": json.dumps(envelope, ensure_ascii=False),
                    }
                )

        print("agent run hit max turns without final response", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""Framework-agnostic OpenAI function-calling adapter.

Exposes the MCP's ToolDispatcher as:
- GET  /tools                — list of OpenAI function-call schemas
- POST /tools/{name}         — dispatch a single tool, returns the MCP envelope
- GET  /openapi.json         — auto-generated OpenAPI 3.0 (free with FastAPI)
- POST /agent/chat           — optional: proxy a chat to a local LLM and loop
                               on tool_calls until completion (off by default)

Boots in seconds with `mcp-phone-controll-http`. Works with Ollama, vLLM,
LM Studio, llama.cpp server, or any OpenAI-compat endpoint via base_url.
"""

from __future__ import annotations

import os
from typing import Any

from .schemas import to_openai_functions


def create_app(dispatcher=None, *, allow_agent_proxy: bool = True):
    """Build the FastAPI app. Lazy imports so the core MCP runs without [http]."""
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware

    if dispatcher is None:
        from ..container import build_runtime

        _, dispatcher = build_runtime()

    app = FastAPI(
        title="mcp-phone-controll HTTP adapter",
        version="0.1.0",
        description=(
            "OpenAI-compat function-calling surface for the mcp-phone-controll "
            "MCP server. Use with any local LLM (Ollama, vLLM, LM Studio, "
            "llama.cpp) by pointing it at GET /tools and POSTing tool calls "
            "to /tools/{name}."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost", "http://127.0.0.1", "http://localhost:*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/tools")
    async def list_tools() -> list[dict[str, Any]]:
        return to_openai_functions(dispatcher.descriptors)

    @app.post("/tools/{name}")
    async def call_tool(name: str, args: dict[str, Any] | None = None):
        if not dispatcher.has(name):
            raise HTTPException(status_code=404, detail=f"unknown tool: {name}")
        return await dispatcher.dispatch(name, args or {})

    @app.get("/health")
    async def health():
        return {"ok": True, "tools": len(dispatcher.descriptors)}

    if allow_agent_proxy:
        _wire_agent_proxy(app, dispatcher)

    return app


def _wire_agent_proxy(app, dispatcher) -> None:
    """Optional /agent/chat endpoint that proxies to a local LLM and loops on
    tool_calls. Off by default unless MCP_LLM_BASE_URL env var is set."""
    from fastapi import HTTPException

    base_url = os.environ.get("MCP_LLM_BASE_URL")
    model_name = os.environ.get("MCP_LLM_MODEL", "qwen2.5:7b")

    @app.post("/agent/chat")
    async def chat(payload: dict[str, Any]):
        if not base_url:
            raise HTTPException(
                status_code=503,
                detail=(
                    "agent proxy is not configured. Set MCP_LLM_BASE_URL to a "
                    "local OpenAI-compat endpoint (e.g. http://localhost:11434/v1)."
                ),
            )
        try:
            import httpx
        except ImportError as e:
            raise HTTPException(status_code=500, detail=f"httpx not installed: {e}")

        messages: list[dict[str, Any]] = list(payload.get("messages") or [])
        max_turns = int(payload.get("max_turns", 8))
        tools = to_openai_functions(dispatcher.descriptors)

        async with httpx.AsyncClient(base_url=base_url, timeout=300) as client:
            for _ in range(max_turns):
                resp = await client.post(
                    "/chat/completions",
                    json={
                        "model": payload.get("model", model_name),
                        "messages": messages,
                        "tools": tools,
                        "tool_choice": "auto",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                choice = (data.get("choices") or [{}])[0]
                msg = choice.get("message") or {}
                tool_calls = msg.get("tool_calls") or []
                messages.append(msg)
                if not tool_calls:
                    return {"final": msg, "messages": messages}
                for tc in tool_calls:
                    fn = (tc.get("function") or {})
                    name = fn.get("name", "")
                    raw_args = fn.get("arguments") or "{}"
                    try:
                        import json as _json

                        args = _json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except Exception:
                        args = {}
                    envelope = await dispatcher.dispatch(name, args)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.get("id"),
                            "name": name,
                            "content": _json_dumps(envelope),
                        }
                    )
        return {
            "final": None,
            "messages": messages,
            "warning": "max_turns reached without final assistant response",
        }


def _json_dumps(obj) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False)

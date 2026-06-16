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
import time
from typing import Any

from .schemas import to_openai_functions

# Process-start timestamp for uptime metrics. Set at module import so
# /health and /metrics agree on the same baseline regardless of which
# was hit first.
_APP_STARTED = time.monotonic()


def _uptime_s() -> float:
    return time.monotonic() - _APP_STARTED


def _strip_bearer(value: str) -> str:
    """Extract `<key>` from an `Authorization: Bearer <key>` header value."""
    value = value.strip()
    if value.lower().startswith("bearer "):
        return value[7:].strip()
    return value


def create_app(dispatcher=None, *, allow_agent_proxy: bool = True):
    """Build the FastAPI app. Lazy imports so the core MCP runs without [http]."""
    from fastapi import Depends, FastAPI, Header, HTTPException
    from fastapi.middleware.cors import CORSMiddleware

    if dispatcher is None:
        from ..container import build_runtime

        _, dispatcher = build_runtime()

    from .. import __version__ as _pkg_version

    app = FastAPI(
        title="mcp-phone-controll HTTP adapter",
        version=_pkg_version,
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

    # Optional auth: when MCP_HTTP_API_KEY is set, every request must
    # carry `X-Api-Key: <key>` (or `Authorization: Bearer <key>`).
    # Closes review §6 risk #4 — open localhost ports become hostile
    # the moment they're forwarded to a LAN.
    import os

    _expected_key = os.environ.get("MCP_HTTP_API_KEY", "").strip() or None

    async def _require_auth(
        x_api_key: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ) -> None:
        """Auth dependency. No-op when MCP_HTTP_API_KEY is unset; otherwise
        requires `X-Api-Key: <key>` or `Authorization: Bearer <key>`."""
        if _expected_key is None:
            return
        provided = x_api_key or _strip_bearer(authorization or "")
        if provided != _expected_key:
            raise HTTPException(status_code=401, detail="invalid or missing API key")

    @app.get("/tools")
    async def list_tools(
        strict: bool | None = None,
        tier: str | None = None,
        _auth: None = Depends(_require_auth),
    ) -> list[dict[str, Any]]:
        # `?strict=true` opts into structured-output mode at the OpenAI
        # function level — see adapters/schemas.py docstring.
        #
        # `?tier=basic|intermediate|expert` (or the MCP_TOOL_TIER env var)
        # scopes the advertised surface — the SLM/local-model lever. Small
        # models choke on 140+ tool schemas; `tier=basic` (~26) keeps the
        # list reasoning-sized and routes the long tail through
        # describe_capabilities. Default (expert/unset) returns everything,
        # so existing agents are unaffected. Mirrors the stdio server's
        # MCP_TOOL_TIER so both transports behave the same.
        from ..domain.tool_levels import tools_for_level

        descriptors = dispatcher.descriptors
        effective = (
            tier or os.environ.get("MCP_TOOL_TIER", "") or "expert"
        ).strip().lower()
        if effective in ("basic", "intermediate"):
            allowed = set(
                tools_for_level(effective, tuple(d.name for d in descriptors))
            )
            descriptors = [d for d in descriptors if d.name in allowed]
        return to_openai_functions(descriptors, strict=strict)

    @app.post("/tools/{name}")
    async def call_tool(
        name: str,
        args: dict[str, Any] | None = None,
        _auth: None = Depends(_require_auth),
    ):
        if not dispatcher.has(name):
            raise HTTPException(status_code=404, detail=f"unknown tool: {name}")
        return await dispatcher.dispatch(name, args or {})

    # ---- Liveness, readiness, metrics --------------------------------
    #
    # /health = liveness probe (am I running?). Always 200 if the
    #          process can serve a request. Used by Kubernetes
    #          liveness probes / load balancer keepalives.
    # /ready  = readiness probe (am I ready to serve traffic?).
    #          Verifies the dispatcher is wired + at least one
    #          image-cap backend exists. Returns 503 if degraded —
    #          the load balancer pulls us out of rotation.
    # /metrics = Prometheus-format counters + gauges. Always available;
    #          no auth (Prometheus servers don't typically carry
    #          headers). If you expose remotely, gate at the
    #          reverse-proxy layer.
    @app.get("/health")
    async def health():
        # Liveness: cheap. The fact that this responded is the signal.
        import time as _time

        from ..version_info import version_info as _vinfo

        v = _vinfo()
        return {
            "ok": True,
            "version": v["package_version"],
            "git_sha": v["git_sha"],
            "tools": len(dispatcher.descriptors),
            "uptime_s": round(_time.monotonic() - _APP_STARTED, 1),
        }

    @app.get("/ready")
    async def ready():
        # Readiness: same shape as /health but FAILS (503) if we're
        # degraded. Specifically: dispatcher has zero tools (config
        # broken) OR no image-cap backend at all (screenshots will
        # silently fail the 2000px gate).
        from fastapi.responses import JSONResponse

        from ..data.image_capping import available_backends

        backends = available_backends()
        ready_ok = bool(dispatcher.descriptors) and bool(backends)
        payload = {
            "ok": ready_ok,
            "tools": len(dispatcher.descriptors),
            "image_backends": list(backends),
            "reasons": (
                []
                if ready_ok
                else [
                    r
                    for r in (
                        "no tools registered" if not dispatcher.descriptors else None,
                        "no image-cap backend available" if not backends else None,
                    )
                    if r
                ]
            ),
        }
        return JSONResponse(content=payload, status_code=200 if ready_ok else 503)

    @app.get("/metrics")
    async def metrics():
        # Prometheus exposition format — text/plain; version 0.0.4.
        # Counters only (no histograms yet — wiring up the dispatcher
        # to emit a per-tool timing histogram is the next step).
        # Pulls from `observability.emit` style fields: we recompute
        # most metrics lazily from the dispatcher + venv state.
        from fastapi.responses import PlainTextResponse

        from ..data.image_capping import _max_dim, available_backends
        from ..version_info import version_info as _vinfo

        v = _vinfo()
        backends = available_backends()
        lines = [
            "# HELP mcp_info Build metadata as labels.",
            "# TYPE mcp_info gauge",
            (
                f'mcp_info{{version="{v["package_version"]}",'
                f'git_sha="{v["git_sha"]}",'
                f'branch="{v["git_branch"]}"}} 1'
            ),
            "# HELP mcp_tools_total Number of tools registered.",
            "# TYPE mcp_tools_total gauge",
            f"mcp_tools_total {len(dispatcher.descriptors)}",
            "# HELP mcp_image_cap_px Active image cap (long-edge pixels).",
            "# TYPE mcp_image_cap_px gauge",
            f"mcp_image_cap_px {_max_dim()}",
            "# HELP mcp_image_backends_available Number of working image-cap backends.",
            "# TYPE mcp_image_backends_available gauge",
            f"mcp_image_backends_available {len(backends)}",
            "# HELP mcp_uptime_seconds Seconds since process start.",
            "# TYPE mcp_uptime_seconds counter",
            f"mcp_uptime_seconds {_uptime_s():.1f}",
        ]
        return PlainTextResponse(
            content="\n".join(lines) + "\n",
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    # Dev-session sub-router: a stable URL prefix exposing only the
    # debug-session + IDE + WDA-setup tools. Lets us extract this surface
    # into a standalone MCP later without behavioural change.
    _wire_dev_session_router(app, dispatcher)

    if allow_agent_proxy:
        _wire_agent_proxy(app, dispatcher)

    return app


_DEV_SESSION_TOOL_NAMES = frozenset(
    {
        "start_debug_session",
        "stop_debug_session",
        "restart_debug_session",
        "list_debug_sessions",
        "attach_debug_session",
        "read_debug_log",
        "tail_debug_log",
        "call_service_extension",
        "dump_widget_tree",
        "dump_render_tree",
        "toggle_inspector",
        "open_project_in_ide",
        "list_ide_windows",
        "close_ide_window",
        "focus_ide_window",
        "is_ide_available",
        "setup_webdriveragent",
    }
)


def _wire_dev_session_router(app, dispatcher) -> None:
    from fastapi import APIRouter, HTTPException

    router = APIRouter(prefix="/dev-session", tags=["dev-session"])

    @router.get("/tools")
    async def dev_list_tools() -> list[dict[str, Any]]:
        descriptors = [
            d for d in dispatcher.descriptors if d.name in _DEV_SESSION_TOOL_NAMES
        ]
        return to_openai_functions(descriptors)

    @router.post("/tools/{name}")
    async def dev_call_tool(name: str, args: dict[str, Any] | None = None):
        if name not in _DEV_SESSION_TOOL_NAMES:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"{name!r} is not a dev-session tool; "
                    "use /tools/{name} for the full surface"
                ),
            )
        if not dispatcher.has(name):
            raise HTTPException(status_code=404, detail=f"unknown tool: {name}")
        return await dispatcher.dispatch(name, args or {})

    app.include_router(router)


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
            raise HTTPException(
                status_code=500, detail=f"httpx not installed: {e}"
            ) from e

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

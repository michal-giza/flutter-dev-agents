"""set_agent_profile — one tool that flips every per-agent knob to match
a known model.

Why: a 4B local model needs different ergonomics than Claude Sonnet —
tighter image cap (896 vs 1920), auto-narrate on, strict tool schemas,
Reflexion retries on. Today the user wires this through six env vars
(`MCP_MAX_IMAGE_DIM`, `MCP_AUTO_NARRATE_EVERY`, `MCP_STRICT_TOOLS`,
`MCP_REFLEXION_RETRIES`, …). Easy to forget one; impossible to flip
mid-session.

This tool encapsulates the canonical profiles. The agent calls it
second (after `mcp_ping`). The dispatcher applies the new settings to
the live middleware chain.

Profiles are deliberately conservative defaults that have been
validated in actual usage:

  - **claude** — Sonnet/Opus / large-context. Image cap 1920, no
    auto-narrate, no strict tools, no Reflexion. Minimal interference.
  - **qwen2.5-7b** — local MLX. Image cap 896, narrate every 5 calls,
    strict tool schemas, 2 Reflexion retries on retryable phases.
  - **qwen2.5-14b** — local MLX, slightly more headroom. Same caps
    but Reflexion retries=1.
  - **llava** — vision-first local model. Image cap 672 (its native
    input), narrate every 3 calls, strict, 2 retries.
  - **haiku** — Claude Haiku. Like Claude but with narrate every 8
    calls (helps the smaller cousin keep oriented).

Returns the previous + new settings so the agent can confirm the change
and the operator sees an audit-trail entry of the profile switch.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..failures import InvalidArgumentFailure
from ..result import Result, err, ok
from .base import BaseUseCase

# Canonical profile definitions. Each maps profile name → settings dict.
# When you add a profile, add a row to the README so users can discover it.
PROFILES: dict[str, dict] = {
    "claude": {
        "image_cap": 1920,
        "auto_narrate_every": 0,
        "strict_tools": False,
        "reflexion_retries": 0,
    },
    "haiku": {
        "image_cap": 1920,
        "auto_narrate_every": 8,
        "strict_tools": False,
        "reflexion_retries": 1,
    },
    "qwen2.5-7b": {
        "image_cap": 896,
        "auto_narrate_every": 5,
        "strict_tools": True,
        "reflexion_retries": 2,
    },
    "qwen2.5-14b": {
        "image_cap": 896,
        "auto_narrate_every": 5,
        "strict_tools": True,
        "reflexion_retries": 1,
    },
    "llava": {
        "image_cap": 672,
        "auto_narrate_every": 3,
        "strict_tools": True,
        "reflexion_retries": 2,
    },
    # Reset to defaults; useful for tests.
    "default": {
        "image_cap": 1920,
        "auto_narrate_every": 0,
        "strict_tools": False,
        "reflexion_retries": 0,
    },
}


@dataclass(frozen=True, slots=True)
class SetAgentProfileParams:
    name: str


@dataclass(frozen=True, slots=True)
class AgentProfileApplied:
    profile: str
    previous: dict
    applied: dict
    summary: str


class SetAgentProfile(BaseUseCase[SetAgentProfileParams, AgentProfileApplied]):
    """Apply a named agent profile to the live middleware chain.

    Takes a `middleware_provider` callable that yields the dispatcher's
    middleware list. We reach into specific middlewares to flip their
    knobs — clean enough because the chain is small and the names are
    stable.
    """

    def __init__(self, middleware_provider, env_setter=None) -> None:
        self._middleware_provider = middleware_provider
        # env_setter lets tests intercept env-var mutation; defaults to os.environ.
        if env_setter is None:
            import os

            env_setter = os.environ.__setitem__
        self._env_setter = env_setter

    async def execute(
        self, params: SetAgentProfileParams
    ) -> Result[AgentProfileApplied]:
        if params.name not in PROFILES:
            return err(
                InvalidArgumentFailure(
                    message=f"unknown profile {params.name!r}",
                    next_action="fix_arguments",
                    details={
                        "available": sorted(PROFILES.keys()),
                        "corrected_example": {"name": "qwen2.5-7b"},
                    },
                )
            )
        new_settings = PROFILES[params.name]
        previous = self._snapshot()
        self._apply(new_settings)
        summary = (
            f"profile={params.name} → "
            f"image_cap={new_settings['image_cap']} "
            f"narrate_every={new_settings['auto_narrate_every']} "
            f"strict={new_settings['strict_tools']} "
            f"reflexion_retries={new_settings['reflexion_retries']}"
        )
        return ok(
            AgentProfileApplied(
                profile=params.name,
                previous=previous,
                applied=dict(new_settings),
                summary=summary,
            )
        )

    # ---- internals -----------------------------------------------------

    def _snapshot(self) -> dict:
        """Capture current settings from the live middleware chain."""
        snap: dict = {
            "image_cap": "see MCP_MAX_IMAGE_DIM env var",  # read at file-call time
            "auto_narrate_every": 0,
            "strict_tools": "see MCP_STRICT_TOOLS env var",
            "reflexion_retries": "see MCP_REFLEXION_RETRIES env var",
        }
        try:
            from ...presentation.middleware import AutoNarrateMiddleware

            for mw in self._middleware_provider():
                if isinstance(mw, AutoNarrateMiddleware):
                    snap["auto_narrate_every"] = getattr(mw, "_every", 0)
                    break
        except Exception:
            pass
        return snap

    def _apply(self, settings: dict) -> None:
        """Apply new settings to live middlewares + env vars."""
        # Update AutoNarrate's live counter window.
        try:
            from ...presentation.middleware import AutoNarrateMiddleware

            for mw in self._middleware_provider():
                if isinstance(mw, AutoNarrateMiddleware):
                    mw._every = int(settings["auto_narrate_every"])
                    mw._counter = 0
                    break
        except Exception:
            pass

        # Image cap, strict tools, reflexion retries are read from env on
        # each call boundary (cap on each dispatch; strict on each HTTP
        # GET /tools; reflexion at YamlPlanExecutor construction). So
        # writing the env var is sufficient AND survives sub-process
        # spawn for tools that read it.
        self._env_setter("MCP_MAX_IMAGE_DIM", str(settings["image_cap"]))
        self._env_setter("MCP_STRICT_TOOLS", "1" if settings["strict_tools"] else "0")
        self._env_setter(
            "MCP_REFLEXION_RETRIES", str(settings["reflexion_retries"])
        )

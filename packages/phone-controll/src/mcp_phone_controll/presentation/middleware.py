"""Middleware chain for the dispatcher.

Before this refactor the dispatcher was one ~120-LOC method handling
seven concerns (rate limit, circuit breaker, Patrol guard, output
truncation, image cap seatbelt, trace recording, auto-narrate). Hard
to test individually, hard to extend without growing further.

Now each concern is a `Middleware` with optional `pre_dispatch` and
`post_dispatch` hooks. The dispatcher walks them in order:

  for mw in middlewares:
      guard = mw.pre_dispatch(name, args)
      if guard is not None:
          return guard            # short-circuit (e.g. rate-limited)

  envelope = invoke_use_case(name, args)

  for mw in reversed(middlewares):
      envelope = mw.post_dispatch(name, args, envelope)

Order is meaningful:
  - PatrolGuard         pre   refuse tap_text once Patrol owns session
  - RateLimiter         pre   refuse over-rate calls, post records ok/fail
  - OutputTruncation    post  truncate before anything else inspects size
  - ImageSafetyNet      post  cap any PNG paths in the envelope
  - TraceRecorder       post  persist the call (now sanitised) to trace
  - AutoNarrate         post  add one-line summary every Nth call

Each middleware is independently unit-testable. The dispatcher is back
to a 20-line orchestrator.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

JsonDict = dict[str, Any]


class Middleware(Protocol):
    """Contract every dispatcher middleware satisfies.

    Both hooks have default no-op implementations in the base classes;
    a concrete middleware overrides whichever side it cares about.
    """

    async def pre_dispatch(
        self, name: str, args: JsonDict | None
    ) -> JsonDict | None:
        """Run before the use case is invoked.

        Return None to continue the chain; return an envelope to
        short-circuit dispatch (e.g. rate-limit guards).
        """
        ...

    async def post_dispatch(
        self, name: str, args: JsonDict | None, envelope: JsonDict
    ) -> JsonDict:
        """Run after the use case returns. May rewrite the envelope.
        Must always return an envelope (never None)."""
        ...


class _BaseMiddleware:
    """Default no-op implementations so concrete middlewares only need
    to override the side they care about."""

    async def pre_dispatch(self, name, args):
        return None

    async def post_dispatch(self, name, args, envelope):
        return envelope


# ----------------------------------------------------------------------
# Concrete middlewares
# ----------------------------------------------------------------------


class PatrolGuardMiddleware(_BaseMiddleware):
    """Refuse raw `tap_text` on app UI once a Patrol-driven session is
    active (`prepare_for_test`/`run_patrol_*` succeeded). System
    dialogs are still allowed via `system=true`."""

    _ACTIVATING = frozenset(
        {"prepare_for_test", "run_patrol_test", "run_patrol_suite", "run_test_plan"}
    )
    _DEACTIVATING = frozenset({"release_device", "stop_app", "new_session"})

    def __init__(self) -> None:
        self._active = False

    async def pre_dispatch(self, name, args):
        if (
            name == "tap_text"
            and self._active
            and not bool((args or {}).get("system", False))
        ):
            return {
                "ok": False,
                "error": {
                    "code": "TapTextRefused",
                    "message": (
                        "tap_text is refused while a Patrol-driven session is "
                        "active. Use run_patrol_test for app UI; pass "
                        "system=true only for OS-level dialogs."
                    ),
                    "next_action": "use_patrol",
                    "details": {
                        "reason": "patrol_session_active",
                        "alternatives": [
                            "run_patrol_test",
                            "tap_and_verify (with Patrol-managed UI)",
                        ],
                    },
                },
            }
        return None

    async def post_dispatch(self, name, args, envelope):
        if not envelope.get("ok"):
            return envelope
        if name in self._ACTIVATING:
            self._active = True
        elif name in self._DEACTIVATING:
            self._active = False
        return envelope


class RateLimiterMiddleware(_BaseMiddleware):
    """Per-tool rate limit + circuit breaker. Discovery + introspection
    tools bypass it so the agent can always inspect its own state."""

    _BYPASS = frozenset(
        {"describe_capabilities", "describe_tool", "session_summary",
         "tool_usage_report", "mcp_ping"}
    )

    def __init__(self, limiter) -> None:
        self._limiter = limiter

    async def pre_dispatch(self, name, args):
        if name in self._BYPASS:
            return None
        return self._limiter.check(name)

    async def post_dispatch(self, name, args, envelope):
        if name in self._BYPASS:
            return envelope
        self._limiter.record(name, bool(envelope.get("ok")))
        return envelope


class OutputTruncationMiddleware(_BaseMiddleware):
    """Cap oversized `data` strings/lists so 4B agents don't OOM."""

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled

    async def post_dispatch(self, name, args, envelope):
        if not self._enabled:
            return envelope
        from .output_truncation import truncate_envelope

        return truncate_envelope(envelope)


class ImageSafetyNetMiddleware(_BaseMiddleware):
    """Last line of defence against >2000px PNG paths in the envelope.
    Caps in place when a backend is available; HARD-REFUSES if none is.
    """

    async def post_dispatch(self, name, args, envelope):
        from .image_safety_net import cap_pngs_in_envelope

        return cap_pngs_in_envelope(envelope)


class TraceRecorderMiddleware(_BaseMiddleware):
    """Persist every dispatched call into the session trace repository."""

    def __init__(self, trace_repo, recorder) -> None:
        self._trace_repo = trace_repo
        self._recorder = recorder

    async def post_dispatch(self, name, args, envelope):
        if self._trace_repo is None:
            return envelope
        await self._recorder(name, args, envelope)
        return envelope


class AutoNarrateMiddleware(_BaseMiddleware):
    """Attach a one-line `narrate` field every Nth call. Off when N=0."""

    def __init__(self, every: int = 0) -> None:
        self._every = max(0, int(every))
        self._counter = 0

    async def post_dispatch(self, name, args, envelope):
        if self._every <= 0:
            return envelope
        self._counter += 1
        if self._counter % self._every == 0:
            from ..domain.usecases.narrate import narrate_envelope

            envelope["narrate"] = narrate_envelope(envelope, tool=name)
        return envelope


# ----------------------------------------------------------------------
# Default chain
# ----------------------------------------------------------------------


def build_default_chain(
    *,
    rate_limiter,
    trace_repo,
    recorder: Callable[[str, JsonDict | None, JsonDict], Awaitable[None]],
    truncate_outputs: bool = True,
    auto_narrate_every: int = 0,
    patrol_guard: PatrolGuardMiddleware | None = None,
) -> list:
    """Return the canonical middleware order used by ToolDispatcher.

    `patrol_guard` may be passed in so callers can share its state
    (e.g. when constructing multiple dispatchers in tests). If None,
    a fresh instance is created.
    """
    if patrol_guard is None:
        patrol_guard = PatrolGuardMiddleware()
    return [
        patrol_guard,
        RateLimiterMiddleware(rate_limiter),
        OutputTruncationMiddleware(enabled=truncate_outputs),
        ImageSafetyNetMiddleware(),
        TraceRecorderMiddleware(trace_repo, recorder),
        AutoNarrateMiddleware(every=auto_narrate_every),
    ]

"""Per-tool rate limits + circuit breakers.

Three guards stack on top of the dispatcher:

1. **Burst rate limit**: at most N calls per tool per `window_s` seconds.
   A 4B model that loops the same call repeatedly hits this and is told to
   step back instead of melting the device or the SDK.

2. **Circuit breaker**: if a single tool fails K times in a row, opens for
   `cooldown_s` seconds. Subsequent calls return immediately with
   `next_action="wait_for_circuit"`. Human-in-the-loop friendly — the user
   sees the breaker, decides whether to wait or escalate.

3. **Per-call timeout**: a soft cap so a hung subprocess can't lock the
   whole session. Implemented at the dispatcher layer with `asyncio.wait_for`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class _ToolStats:
    timestamps: list[float] = field(default_factory=list)
    consecutive_failures: int = 0
    breaker_opens_until: float = 0.0


@dataclass(frozen=True, slots=True)
class RateLimitConfig:
    max_per_window: int = 30
    window_s: float = 60.0
    breaker_failure_threshold: int = 5
    breaker_cooldown_s: float = 30.0


# Tool-name → custom config; defaults applied otherwise.
DEFAULT_OVERRIDES: dict[str, RateLimitConfig] = {
    # Hot reload is fast and cheap, allow more
    "restart_debug_session": RateLimitConfig(
        max_per_window=120, window_s=60.0
    ),
    # Take screenshot is a discipline tool — cap aggressively
    "take_screenshot": RateLimitConfig(max_per_window=20, window_s=60.0),
    # Force release is a destructive operation, allow rarely
    "force_release_lock": RateLimitConfig(
        max_per_window=3, window_s=300.0, breaker_failure_threshold=2
    ),
    # tap_text loops are a known small-LLM failure mode
    "tap_text": RateLimitConfig(
        max_per_window=15, window_s=60.0, breaker_failure_threshold=4
    ),
}


class RateLimiter:
    """In-process rate limiter + breaker. Single MCP-process scope.

    For multi-process coordination, use the device-lock layer instead — this
    one is meant to protect the agent from itself.
    """

    def __init__(
        self,
        default: RateLimitConfig | None = None,
        overrides: dict[str, RateLimitConfig] | None = None,
        now=time.monotonic,
    ) -> None:
        self._default = default if default is not None else RateLimitConfig()
        self._overrides = dict(DEFAULT_OVERRIDES)
        if overrides:
            self._overrides.update(overrides)
        self._stats: dict[str, _ToolStats] = {}
        self._now = now

    def _config(self, name: str) -> RateLimitConfig:
        return self._overrides.get(name, self._default)

    def _stat(self, name: str) -> _ToolStats:
        return self._stats.setdefault(name, _ToolStats())

    def check(self, name: str) -> dict | None:
        """Return a guard envelope if the call should be blocked, else None."""
        cfg = self._config(name)
        stat = self._stat(name)
        now = self._now()
        # Breaker open?
        if stat.breaker_opens_until > now:
            wait_s = round(stat.breaker_opens_until - now, 1)
            return {
                "ok": False,
                "error": {
                    "code": "CircuitOpen",
                    "message": (
                        f"{name} circuit-broken after "
                        f"{cfg.breaker_failure_threshold} consecutive failures"
                    ),
                    "next_action": "wait_for_circuit",
                    "details": {
                        "wait_s": wait_s,
                        "cooldown_s": cfg.breaker_cooldown_s,
                    },
                },
            }
        # Window-based rate limit.
        cutoff = now - cfg.window_s
        stat.timestamps = [ts for ts in stat.timestamps if ts > cutoff]
        if len(stat.timestamps) >= cfg.max_per_window:
            oldest = stat.timestamps[0]
            return {
                "ok": False,
                "error": {
                    "code": "RateLimited",
                    "message": (
                        f"{name} rate limit: {cfg.max_per_window} calls per "
                        f"{cfg.window_s:.0f}s"
                    ),
                    "next_action": "back_off",
                    "details": {
                        "retry_after_s": round(oldest + cfg.window_s - now, 1),
                        "max_per_window": cfg.max_per_window,
                    },
                },
            }
        return None

    def record(self, name: str, ok_flag: bool) -> None:
        cfg = self._config(name)
        stat = self._stat(name)
        stat.timestamps.append(self._now())
        if ok_flag:
            stat.consecutive_failures = 0
        else:
            stat.consecutive_failures += 1
            if stat.consecutive_failures >= cfg.breaker_failure_threshold:
                stat.breaker_opens_until = self._now() + cfg.breaker_cooldown_s
                stat.consecutive_failures = 0

"""Unit tests for the per-tool rate limiter + circuit breaker."""

from __future__ import annotations

from mcp_phone_controll.presentation.rate_limiter import (
    RateLimitConfig,
    RateLimiter,
)


class _Clock:
    def __init__(self, t: float = 0.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


def test_first_call_passes():
    rl = RateLimiter()
    assert rl.check("tap_text") is None


def test_blocks_when_window_exceeded():
    clock = _Clock()
    rl = RateLimiter(
        default=RateLimitConfig(max_per_window=2, window_s=10.0),
        now=clock,
    )
    assert rl.check("any") is None
    rl.record("any", True)
    assert rl.check("any") is None
    rl.record("any", True)
    guard = rl.check("any")
    assert guard is not None
    assert guard["error"]["code"] == "RateLimited"
    assert guard["error"]["next_action"] == "back_off"


def test_window_recovers_after_time():
    clock = _Clock()
    rl = RateLimiter(
        default=RateLimitConfig(max_per_window=1, window_s=10.0),
        now=clock,
    )
    rl.record("any", True)
    assert rl.check("any") is not None
    clock.t += 11.0
    assert rl.check("any") is None


def test_breaker_opens_after_threshold_failures():
    clock = _Clock()
    rl = RateLimiter(
        default=RateLimitConfig(
            max_per_window=99,
            window_s=10.0,
            breaker_failure_threshold=3,
            breaker_cooldown_s=20.0,
        ),
        now=clock,
    )
    for _ in range(3):
        rl.record("any", False)
    guard = rl.check("any")
    assert guard is not None
    assert guard["error"]["code"] == "CircuitOpen"
    assert guard["error"]["next_action"] == "wait_for_circuit"


def test_breaker_resets_on_success():
    clock = _Clock()
    rl = RateLimiter(
        default=RateLimitConfig(
            max_per_window=99,
            window_s=10.0,
            breaker_failure_threshold=3,
        ),
        now=clock,
    )
    rl.record("any", False)
    rl.record("any", False)
    rl.record("any", True)   # reset
    rl.record("any", False)
    rl.record("any", False)
    assert rl.check("any") is None    # haven't crossed threshold

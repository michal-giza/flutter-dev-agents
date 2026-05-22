"""Unified ADB client fake for use across the test suite.

Replaces the three slightly-different `_FakeAdb` / `_FakeAdbClient`
classes that used to live in:

  - tests/unit/test_deep_link.py
  - tests/unit/test_ui_automation_pause.py

(Surfaced by the internal senior-tester audit 2026-05-22 as a
duplication smell.)

Two modes:

  **Canned mode** — every `.shell()` call returns the same
  ProcessResult. Set via `stdout` / `stderr` / `returncode`
  kwargs on the constructor.

      adb = FakeAdbClient(stdout="Status: ok\\n")

  **Per-command mode** — supply a `responses` dict keyed by the
  exact shell args tuple (NOT including serial). Calls that
  match the key return the scripted ProcessResult; calls that
  don't match fall back to `default`.

      adb = FakeAdbClient(responses={
          ("pm", "list", "packages", "com.foo"):
              ProcessResult(stdout="package:com.foo\\n"),
      })

Both modes record every call into `.calls` as `(serial, *args)`
tuples so the test can inspect call history.

The `_runner` attribute is exposed as a placeholder object — the
deep_link use case touches it when wiring the iOS simctl path,
and without it `AttributeError` would crash the test.

For more elaborate state-machine behaviour (e.g. pause/resume
round-trip tests where calls mutate shared state), build a
bespoke inline fake — that's a one-off pattern, not worth
shared-fake'ing.
"""

from __future__ import annotations

from typing import Any

from mcp_phone_controll.infrastructure.process_runner import ProcessResult


class FakeAdbClient:
    """AdbClient test double supporting canned + per-command modes.

    See module docstring for usage.
    """

    def __init__(
        self,
        # Canned mode
        stdout: str = "",
        stderr: str = "",
        returncode: int = 0,
        # Per-command mode (overrides canned for matching keys)
        responses: dict[tuple[str, ...], ProcessResult] | None = None,
        default: ProcessResult | None = None,
    ) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.responses = responses or {}
        self.default = default or ProcessResult(
            stdout=stdout, stderr=stderr, returncode=returncode,
        )
        self.calls: list[tuple[str, ...]] = []
        # The deep_link / dev_session use cases touch `._runner`
        # when wiring up the iOS simctl path. Placeholder so the
        # `getattr` doesn't AttributeError on test fakes.
        self._runner: Any = object()

    async def shell(
        self, serial: str, *args: str, timeout_s: float = 30.0,
    ) -> ProcessResult:
        self.calls.append((serial, *args))
        # Per-command mode wins when a matching key exists; else
        # canned default.
        return self.responses.get(args, self.default)

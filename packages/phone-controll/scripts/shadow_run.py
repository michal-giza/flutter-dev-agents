"""Shadow-run harness — exercise a new tool against the fake dispatcher
many times before exposing it to live agents.

Usage:

    python -m scripts.shadow_run --tool tap_and_verify --iterations 100
    python -m scripts.shadow_run --suite tier_g                 # all G tools
    python -m scripts.shadow_run --tool recall --strategy fuzz  # randomized args

Why this exists: article enhancement #7. New tools land with their
domain-level unit tests, but live agents call them with shapes you
didn't anticipate. Shadow-run drives a tool through the full dispatcher
(coercion + truncation + rate-limiter + tracing) under a load profile
representative of what a 4B-class agent actually does — random arg
permutations, repeated calls, malformed types.

Outputs a JUnit-style report under `~/.mcp_phone_controll/shadow-runs/`:

    {
      "tool": "tap_and_verify",
      "iterations": 100,
      "ok_rate": 0.93,
      "next_actions_seen": {"capture_diagnostics": 7, ...},
      "envelope_invariants_violated": 0,
      "duration_ms": 412
    }

If `envelope_invariants_violated > 0`, the tool isn't ready to ship.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import string
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# Strategies a 4B agent has been observed to attempt:
#  1. "happy"  — args copied from corrected_example
#  2. "fuzz"   — random permutations (wrong types, missing fields, extras)
#  3. "repeat" — same args N times in a row (loop pathology)
_STRATEGIES = ("happy", "fuzz", "repeat")


_TIER_G_TOOLS: tuple[str, ...] = (
    "describe_capabilities",
    "describe_tool",
    "recall",
    "index_project",
    "tap_and_verify",
    "assert_no_errors_since",
    "run_quick_check",
    "summarize_session",
)


def _rand_string(n: int = 6) -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=n))


def _happy_args(name: str, descriptor) -> dict:
    """Return a sensible, schema-conforming arg blob for the tool."""
    schema = descriptor.input_schema or {}
    required = schema.get("required", []) or []
    props = schema.get("properties", {}) or {}
    out: dict[str, Any] = {}
    for key in required:
        prop = props.get(key, {})
        ptype = prop.get("type", "string")
        if ptype == "string":
            out[key] = "x" if "pattern" not in key else ".*"
            if key == "query":
                out[key] = "what does UMP_GATE require?"
            if key == "path":
                out[key] = "/tmp/none.log"
            if "project_path" in key:
                out[key] = "/tmp/no-such-project"
            if key == "text":
                out[key] = "Sign in"
            if key == "expect_text":
                out[key] = "Welcome"
            if key == "name":
                out[key] = "select_device"
        elif ptype == "integer":
            out[key] = 1
        elif ptype == "number":
            out[key] = 1.0
        elif ptype == "boolean":
            out[key] = False
        elif ptype == "array":
            out[key] = []
        elif ptype == "object":
            out[key] = {}
    return out


def _fuzz_args(base: dict) -> dict:
    """Permute a base args dict with a 4B-style mistake."""
    out = dict(base)
    if not out:
        return {_rand_string(): _rand_string()}
    op = random.choice(("drop_required", "wrong_type", "extra_garbage", "stringify"))
    keys = list(out.keys())
    key = random.choice(keys)
    if op == "drop_required":
        out.pop(key, None)
    elif op == "wrong_type":
        out[key] = [_rand_string()]
    elif op == "extra_garbage":
        out[_rand_string()] = _rand_string()
    elif op == "stringify" and isinstance(out[key], (int, float, bool)):
        out[key] = str(out[key])
    return out


async def _drive(dispatcher, name: str, iterations: int, strategy: str) -> dict:
    descriptor = dispatcher._by_name.get(name)
    if descriptor is None:
        return {"tool": name, "error": "unknown tool"}
    base = _happy_args(name, descriptor)
    next_actions: dict[str, int] = {}
    invariants_violated = 0
    ok_count = 0
    started = time.monotonic()
    for i in range(iterations):
        if strategy == "happy":
            args = dict(base)
        elif strategy == "fuzz":
            args = _fuzz_args(base) if i % 3 else dict(base)
        elif strategy == "repeat":
            args = dict(base)
        else:
            args = dict(base)
        envelope = await dispatcher.dispatch(name, args)
        # Envelope invariants — every reply MUST satisfy these. If not,
        # the tool's wiring has a bug and we abort.
        if not isinstance(envelope, dict):
            invariants_violated += 1
            continue
        if "ok" not in envelope:
            invariants_violated += 1
            continue
        if envelope["ok"]:
            ok_count += 1
        else:
            err = envelope.get("error") or {}
            if not isinstance(err, dict) or "code" not in err:
                invariants_violated += 1
                continue
            na = err.get("next_action")
            if na:
                next_actions[na] = next_actions.get(na, 0) + 1
    duration_ms = int((time.monotonic() - started) * 1000)
    return {
        "tool": name,
        "iterations": iterations,
        "strategy": strategy,
        "ok_rate": round(ok_count / iterations, 3) if iterations else 0.0,
        "next_actions_seen": next_actions,
        "envelope_invariants_violated": invariants_violated,
        "duration_ms": duration_ms,
    }


async def _async_main(args) -> int:
    # Build the same fake dispatcher the unit tests use. Hermetic.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests.integration.test_tool_dispatcher import _build_fake_dispatcher

    out_dir = Path.home() / ".mcp_phone_controll" / "shadow-runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now()
    out_path = out_dir / started.strftime("%Y%m%d-%H%M%S-shadow.json")

    dispatcher = _build_fake_dispatcher(Path("/tmp"))

    tools: list[str]
    if args.suite == "tier_g":
        tools = list(_TIER_G_TOOLS)
    elif args.tool:
        tools = [args.tool]
    else:
        tools = list(_TIER_G_TOOLS)

    results = []
    for tool in tools:
        res = await _drive(dispatcher, tool, args.iterations, args.strategy)
        results.append(res)

    failed = sum(1 for r in results if r.get("envelope_invariants_violated", 0) > 0)
    report = {
        "started": started.isoformat(),
        "finished": datetime.now().isoformat(),
        "suite": args.suite,
        "strategy": args.strategy,
        "results": results,
        "tools_with_violations": failed,
    }
    out_path.write_text(json.dumps(report, indent=2))
    print(f"shadow-run done → {out_path}")
    if failed:
        print(f"FAILED: {failed} tool(s) violated envelope invariants", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool", help="Single tool name to shadow-run")
    ap.add_argument("--suite", default=None, help="'tier_g' to run all G tools")
    ap.add_argument("--iterations", type=int, default=100)
    ap.add_argument("--strategy", choices=_STRATEGIES, default="fuzz")
    args = ap.parse_args()
    if not args.tool and not args.suite:
        args.suite = "tier_g"
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    sys.exit(main())

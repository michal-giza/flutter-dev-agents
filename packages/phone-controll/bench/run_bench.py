"""Tool-usage benchmark — measure agent stack quality on fixed tasks.

Inspired by Qin et al., 2023 (ToolBench, arXiv:2307.16789), but scoped
down: 10 deterministic tasks, each replayed against the dispatcher with
expected envelope invariants. Used to measure regressions between
versions and to compare agent-driving stacks (Claude vs Qwen vs Llama
when those harnesses arrive).

Output: JUnit XML at `~/.mcp_phone_controll/bench/<timestamp>.junit.xml`
plus a JSON summary. The JUnit format means the same report can be
consumed by any CI runner.

Usage:

    python -m bench.run_bench
    python -m bench.run_bench --tasks T01,T03,T10
    python -m bench.run_bench --json-only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET


def _expect_ok(actual: dict, expect: dict) -> tuple[bool, str]:
    """Return (passed, reason)."""
    ok_flag = bool(actual.get("ok"))
    if "ok" in expect and ok_flag is not bool(expect["ok"]):
        return False, f"ok: expected {expect['ok']}, got {ok_flag}"
    if "next_action" in expect:
        actual_na = (actual.get("error") or {}).get("next_action")
        if actual_na != expect["next_action"]:
            return False, f"next_action: expected {expect['next_action']!r}, got {actual_na!r}"
    if "data_type" in expect:
        data = actual.get("data")
        type_map = {"list": list, "dict": dict, "str": str, "null": type(None)}
        if not isinstance(data, type_map[expect["data_type"]]):
            return False, f"data_type: expected {expect['data_type']}, got {type(data).__name__}"
    if "data_min_len" in expect:
        data = actual.get("data")
        if not hasattr(data, "__len__"):
            return False, f"data_min_len check needs sized data, got {type(data).__name__}"
        if len(data) < expect["data_min_len"]:
            return False, f"data_min_len: expected ≥ {expect['data_min_len']}, got {len(data)}"
    return True, ""


async def _run_task(dispatcher, task: dict) -> dict:
    started = time.monotonic()
    failed_call = None
    failed_reason = None
    last_envelope = None
    for idx, call in enumerate(task["calls"]):
        last_envelope = await dispatcher.dispatch(call["tool"], call.get("args") or {})
        passed, reason = _expect_ok(last_envelope, call.get("expect") or {})
        if not passed:
            failed_call = idx
            failed_reason = f"{call['tool']}: {reason}"
            break
    duration_ms = int((time.monotonic() - started) * 1000)
    return {
        "task": task["id"],
        "description": task["description"],
        "passed": failed_call is None,
        "failed_at": failed_call,
        "reason": failed_reason,
        "duration_ms": duration_ms,
        "last_envelope_summary": (
            "ok"
            if last_envelope and last_envelope.get("ok")
            else (last_envelope or {}).get("error", {}).get("code", "n/a")
        ),
    }


def _emit_junit(results: list[dict], out_path: Path, total_ms: int) -> None:
    suite = ET.Element(
        "testsuite",
        {
            "name": "phone-controll-bench",
            "tests": str(len(results)),
            "failures": str(sum(1 for r in results if not r["passed"])),
            "time": f"{total_ms / 1000:.3f}",
        },
    )
    for r in results:
        case = ET.SubElement(
            suite,
            "testcase",
            {
                "classname": "bench",
                "name": r["task"],
                "time": f"{r['duration_ms'] / 1000:.3f}",
            },
        )
        if not r["passed"]:
            failure = ET.SubElement(
                case,
                "failure",
                {"message": (r.get("reason") or "")[:500]},
            )
            failure.text = r.get("reason") or "no reason captured"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(suite).write(out_path, encoding="utf-8", xml_declaration=True)


async def _async_main(args) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests.integration.test_tool_dispatcher import _build_fake_dispatcher

    tasks_path = Path(__file__).resolve().parent / "tasks.json"
    tasks = json.loads(tasks_path.read_text())
    if args.tasks:
        wanted = set(args.tasks.split(","))
        tasks = [t for t in tasks if t["id"] in wanted]
        if not tasks:
            print(f"no tasks matched {args.tasks!r}", file=sys.stderr)
            return 2

    out_dir = Path.home() / ".mcp_phone_controll" / "bench"
    out_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now()
    stamp = started.strftime("%Y%m%d-%H%M%S")
    json_path = out_dir / f"{stamp}.json"
    junit_path = out_dir / f"{stamp}.junit.xml"

    overall_started = time.monotonic()
    results: list[dict] = []
    for task in tasks:
        # Fresh dispatcher per task — no cross-contamination of state.
        dispatcher = _build_fake_dispatcher(Path("/tmp"))
        result = await _run_task(dispatcher, task)
        results.append(result)
    total_ms = int((time.monotonic() - overall_started) * 1000)

    summary = {
        "started": started.isoformat(),
        "finished": datetime.now().isoformat(),
        "tasks_run": len(results),
        "tasks_passed": sum(1 for r in results if r["passed"]),
        "duration_ms": total_ms,
        "results": results,
    }
    json_path.write_text(json.dumps(summary, indent=2))
    if not args.json_only:
        _emit_junit(results, junit_path, total_ms)

    print(f"bench done → {json_path}")
    if not args.json_only:
        print(f"  junit → {junit_path}")
    print(f"  passed: {summary['tasks_passed']}/{summary['tasks_run']}")
    failures = [r for r in results if not r["passed"]]
    if failures:
        for f in failures:
            print(f"    ✗ {f['task']}: {f['reason']}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", help="Comma-separated task ids (e.g. T01,T03)")
    ap.add_argument("--json-only", action="store_true", help="Skip JUnit XML")
    args = ap.parse_args()
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    sys.exit(main())

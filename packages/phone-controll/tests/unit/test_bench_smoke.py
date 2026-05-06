"""Bench harness must execute all tasks cleanly against the fake stack.

This is the CI gate that protects the benchmark report from drifting
silently. If a task starts failing, either the task is wrong or a tool
regressed — either way, we want red CI.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_bench_all_tasks_pass_against_fake_stack():
    bench_path = (
        Path(__file__).resolve().parents[2] / "bench" / "run_bench.py"
    )
    spec = importlib.util.spec_from_file_location("bench_run", bench_path)
    assert spec and spec.loader
    bench = importlib.util.module_from_spec(spec)
    sys.modules["bench_run"] = bench
    spec.loader.exec_module(bench)

    from tests.integration.test_tool_dispatcher import _build_fake_dispatcher

    tasks_path = bench_path.parent / "tasks.json"
    tasks = json.loads(tasks_path.read_text())
    assert len(tasks) >= 10, "bench should ship with ≥10 tasks"

    failed: list[dict] = []
    for task in tasks:
        dispatcher = _build_fake_dispatcher(Path("/tmp"))
        result = await bench._run_task(dispatcher, task)
        if not result["passed"]:
            failed.append(result)
    assert not failed, f"bench tasks regressed: {failed}"

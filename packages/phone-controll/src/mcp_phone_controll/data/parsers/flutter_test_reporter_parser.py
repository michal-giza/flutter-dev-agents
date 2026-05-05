"""Parse `flutter test --reporter=json` event stream into a TestRun.

The reporter emits one JSON object per line; we care about:
  - `testStart` (event payload has `test.id`, `test.name`, `test.url`)
  - `testDone` (`testID`, `result`: success|failure|error, `hidden`, `time`)
  - `error` (`testID`, `error`, `stackTrace`)
  - `done` (overall `success`, `time`)
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ...domain.entities import TestCase, TestRun, TestStatus


@dataclass
class _Pending:
    name: str
    started_at_ms: int
    error_message: str | None = None
    stack_trace: str | None = None
    status: TestStatus | None = None
    done_at_ms: int | None = None
    hidden: bool = False


def parse_flutter_json_reporter(stdout: str) -> TestRun:
    pending: dict[int, _Pending] = {}
    overall_time_ms = 0

    for raw in stdout.splitlines():
        line = raw.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        if kind == "testStart":
            test = event.get("test", {})
            test_id = test.get("id")
            if test_id is None:
                continue
            pending[test_id] = _Pending(
                name=test.get("name", f"test {test_id}"),
                started_at_ms=event.get("time", 0),
            )
        elif kind == "error":
            test_id = event.get("testID")
            entry = pending.get(test_id)
            if entry is None:
                continue
            entry.error_message = event.get("error")
            entry.stack_trace = event.get("stackTrace")
        elif kind == "testDone":
            test_id = event.get("testID")
            entry = pending.get(test_id)
            if entry is None:
                continue
            entry.hidden = bool(event.get("hidden", False))
            entry.done_at_ms = event.get("time", entry.started_at_ms)
            result = event.get("result", "success")
            if event.get("skipped"):
                entry.status = TestStatus.SKIPPED
            elif result == "success":
                entry.status = TestStatus.PASSED
            elif result == "failure":
                entry.status = TestStatus.FAILED
            else:
                entry.status = TestStatus.ERRORED
        elif kind == "done":
            overall_time_ms = event.get("time", overall_time_ms)

    cases: list[TestCase] = []
    passed = failed = errored = skipped = 0
    for entry in pending.values():
        if entry.hidden or entry.status is None:
            continue
        duration = max(0, (entry.done_at_ms or entry.started_at_ms) - entry.started_at_ms)
        cases.append(
            TestCase(
                name=entry.name,
                status=entry.status,
                duration_ms=duration,
                error_message=entry.error_message,
                stack_trace=entry.stack_trace,
            )
        )
        if entry.status is TestStatus.PASSED:
            passed += 1
        elif entry.status is TestStatus.FAILED:
            failed += 1
        elif entry.status is TestStatus.ERRORED:
            errored += 1
        elif entry.status is TestStatus.SKIPPED:
            skipped += 1

    total = passed + failed + errored + skipped
    return TestRun(
        total=total,
        passed=passed,
        failed=failed,
        errored=errored,
        skipped=skipped,
        duration_ms=overall_time_ms,
        cases=cases,
    )

import json

from mcp_phone_controll.data.parsers.flutter_test_reporter_parser import (
    parse_flutter_json_reporter,
)
from mcp_phone_controll.domain.entities import TestStatus


def _events(*evts) -> str:
    return "\n".join(json.dumps(e) for e in evts) + "\n"


def test_parses_pass_fail_and_skip():
    stream = _events(
        {"type": "start", "time": 0},
        {"type": "testStart", "test": {"id": 1, "name": "passes"}, "time": 10},
        {"type": "testDone", "testID": 1, "result": "success", "time": 20},
        {"type": "testStart", "test": {"id": 2, "name": "fails"}, "time": 30},
        {"type": "error", "testID": 2, "error": "boom", "stackTrace": "..."},
        {"type": "testDone", "testID": 2, "result": "failure", "time": 60},
        {"type": "testStart", "test": {"id": 3, "name": "skipped"}, "time": 70},
        {"type": "testDone", "testID": 3, "result": "success", "skipped": True, "time": 71},
        {"type": "done", "success": False, "time": 72},
    )
    run = parse_flutter_json_reporter(stream)
    assert run.total == 3
    assert run.passed == 1
    assert run.failed == 1
    assert run.skipped == 1
    assert run.errored == 0
    assert run.duration_ms == 72
    failing = next(c for c in run.cases if c.name == "fails")
    assert failing.status is TestStatus.FAILED
    assert failing.error_message == "boom"
    assert failing.duration_ms == 30


def test_hidden_tests_are_excluded():
    stream = _events(
        {"type": "testStart", "test": {"id": 1, "name": "loading"}, "time": 0},
        {"type": "testDone", "testID": 1, "result": "success", "hidden": True, "time": 1},
        {"type": "testStart", "test": {"id": 2, "name": "real"}, "time": 2},
        {"type": "testDone", "testID": 2, "result": "success", "time": 3},
    )
    run = parse_flutter_json_reporter(stream)
    assert run.total == 1
    assert run.cases[0].name == "real"


def test_handles_garbage_lines():
    stream = "not json\n" + _events(
        {"type": "testStart", "test": {"id": 1, "name": "ok"}, "time": 0},
        {"type": "testDone", "testID": 1, "result": "success", "time": 1},
    )
    run = parse_flutter_json_reporter(stream)
    assert run.total == 1

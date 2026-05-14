"""Pure-function tests for the flutter --machine event parser."""

from __future__ import annotations

import json

from mcp_phone_controll.data.parsers.flutter_machine_event_parser import (
    app_id_from_started,
    event_to_log,
    parse_machine_line,
    vm_service_uri_from_started,
)


def test_parses_event_line():
    line = json.dumps([{"event": "app.start", "params": {"appId": "abc"}}])
    out = parse_machine_line(line)
    assert len(out) == 1
    assert out[0]["event"] == "app.start"


def test_parses_response_line():
    line = json.dumps([{"id": 1, "result": {"hotReload": True}}])
    out = parse_machine_line(line)
    assert out[0]["id"] == 1


def test_ignores_non_json_lines():
    assert parse_machine_line("Launching ...") == []
    assert parse_machine_line("") == []
    assert parse_machine_line("not [json") == []


def test_ignores_non_array_json():
    assert parse_machine_line(json.dumps({"event": "x"})) == []


def test_event_to_log_handles_app_log():
    log = event_to_log({"event": "app.log", "params": {"log": "hello", "isolateId": "i-1"}})
    assert log is not None
    assert log.message == "hello"
    assert log.source == "app"
    assert log.level == "info"
    assert log.isolate_id == "i-1"


def test_event_to_log_handles_app_log_error():
    log = event_to_log({"event": "app.log", "params": {"log": "boom", "error": True}})
    assert log is not None
    assert log.level == "error"


def test_event_to_log_handles_daemon_log():
    log = event_to_log(
        {"event": "daemon.logMessage", "params": {"level": "warning", "message": "hi"}}
    )
    assert log is not None
    assert log.source == "daemon"
    assert log.level == "warning"


def test_event_to_log_returns_none_for_lifecycle_events():
    assert event_to_log({"event": "app.start"}) is None
    assert event_to_log({"event": "app.started"}) is None
    assert event_to_log({"event": "daemon.connected"}) is None


def test_app_id_from_started():
    assert app_id_from_started({"event": "app.started", "params": {"appId": "abc"}}) == "abc"
    assert app_id_from_started({"event": "app.start", "params": {"appId": "abc"}}) is None
    assert app_id_from_started({"event": "app.started", "params": {}}) is None


def test_vm_service_uri_from_app_started():
    uri = vm_service_uri_from_started(
        {"event": "app.started", "params": {"wsUri": "ws://localhost:1234/abc/ws"}}
    )
    assert uri == "ws://localhost:1234/abc/ws"


def test_vm_service_uri_from_debug_port():
    uri = vm_service_uri_from_started(
        {"event": "app.debugPort", "params": {"uri": "http://localhost:1234"}}
    )
    assert uri == "http://localhost:1234"

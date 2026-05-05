"""Tests for the simctl JSON parser."""

from __future__ import annotations

import json

from mcp_phone_controll.data.parsers.simctl_parser import parse_simctl_devices
from mcp_phone_controll.domain.entities import DeviceClass, DeviceState, Platform


_BASE_PAYLOAD = {
    "devices": {
        "com.apple.CoreSimulator.SimRuntime.iOS-17-4": [
            {
                "udid": "ABC-123",
                "name": "iPhone 15",
                "state": "Booted",
                "isAvailable": True,
                "deviceTypeIdentifier": "com.apple.CoreSimulator.SimDeviceType.iPhone-15",
            },
            {
                "udid": "DEF-456",
                "name": "iPhone 14",
                "state": "Shutdown",
                "isAvailable": True,
                "deviceTypeIdentifier": "com.apple.CoreSimulator.SimDeviceType.iPhone-14",
            },
            {
                "udid": "OLD-999",
                "name": "iPhone 6",
                "state": "Shutdown",
                "isAvailable": False,
                "deviceTypeIdentifier": "iPhone-6",
            },
        ],
        "com.apple.CoreSimulator.SimRuntime.watchOS-10-2": [
            {
                "udid": "WATCH-1",
                "name": "Apple Watch",
                "state": "Booted",
                "isAvailable": True,
            }
        ],
    }
}


def test_parses_booted_and_shutdown_simulators():
    out = parse_simctl_devices(json.dumps(_BASE_PAYLOAD))
    serials = {d.serial for d in out}
    assert serials == {"ABC-123", "DEF-456"}
    booted = next(d for d in out if d.serial == "ABC-123")
    shutdown = next(d for d in out if d.serial == "DEF-456")
    assert booted.state is DeviceState.DEVICE
    assert shutdown.state is DeviceState.OFFLINE
    assert all(d.platform is Platform.IOS for d in out)
    assert all(d.device_class is DeviceClass.SIMULATOR for d in out)


def test_only_booted_filter():
    out = parse_simctl_devices(json.dumps(_BASE_PAYLOAD), only_booted=True)
    assert [d.serial for d in out] == ["ABC-123"]


def test_skips_unavailable_simulators():
    out = parse_simctl_devices(json.dumps(_BASE_PAYLOAD))
    assert "OLD-999" not in {d.serial for d in out}


def test_ignores_non_ios_runtimes():
    out = parse_simctl_devices(json.dumps(_BASE_PAYLOAD))
    assert "WATCH-1" not in {d.serial for d in out}


def test_extracts_runtime_version():
    out = parse_simctl_devices(json.dumps(_BASE_PAYLOAD))
    assert all(d.os_version == "17.4" for d in out)


def test_handles_empty_input():
    assert parse_simctl_devices("") == []
    assert parse_simctl_devices("{}") == []
    assert parse_simctl_devices("not json") == []


def test_handles_malformed_runtime_block():
    payload = {"devices": {"com.apple.CoreSimulator.SimRuntime.iOS-17-4": "broken"}}
    assert parse_simctl_devices(json.dumps(payload)) == []

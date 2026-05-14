"""Parse `xcrun simctl list devices --json` output.

Output shape (truncated):
    {
      "devices": {
        "com.apple.CoreSimulator.SimRuntime.iOS-17-4": [
          { "udid": "...", "name": "iPhone 15", "state": "Booted",
            "isAvailable": true, "deviceTypeIdentifier": "...iPhone-15" },
          ...
        ],
        "com.apple.CoreSimulator.SimRuntime.iOS-16-4": [...]
      }
    }

We extract iOS simulators only, marking each with DeviceClass.SIMULATOR and
the runtime version pulled from the runtime key.
"""

from __future__ import annotations

import json
import re

from ...domain.entities import Device, DeviceClass, DeviceState, Platform

_RUNTIME_RE = re.compile(r"iOS-(\d+)-(\d+)")


def _runtime_to_version(runtime_key: str) -> str | None:
    match = _RUNTIME_RE.search(runtime_key)
    if not match:
        return None
    major, minor = match.group(1), match.group(2)
    return f"{major}.{minor}"


def _state_for(simctl_state: str, available: bool) -> DeviceState:
    if not available:
        return DeviceState.UNKNOWN
    if simctl_state == "Booted":
        return DeviceState.DEVICE
    if simctl_state == "Shutdown":
        return DeviceState.OFFLINE
    return DeviceState.UNKNOWN


def parse_simctl_devices(stdout: str, *, only_booted: bool = False) -> list[Device]:
    text = stdout.strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    by_runtime = payload.get("devices") or {}
    if not isinstance(by_runtime, dict):
        return []

    out: list[Device] = []
    for runtime_key, sims in by_runtime.items():
        if not isinstance(sims, list):
            continue
        if "iOS" not in runtime_key:
            continue  # ignore watchOS / tvOS / visionOS for now
        os_version = _runtime_to_version(runtime_key)
        for sim in sims:
            if not isinstance(sim, dict):
                continue
            if not sim.get("isAvailable", True):
                continue
            simctl_state = str(sim.get("state", ""))
            if only_booted and simctl_state != "Booted":
                continue
            udid = sim.get("udid")
            if not udid:
                continue
            out.append(
                Device(
                    serial=str(udid),
                    state=_state_for(simctl_state, bool(sim.get("isAvailable", True))),
                    model=sim.get("name") or sim.get("deviceTypeIdentifier"),
                    os_version=os_version,
                    platform=Platform.IOS,
                    device_class=DeviceClass.SIMULATOR,
                )
            )
    return out

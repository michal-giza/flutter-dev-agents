"""Parse `pymobiledevice3 usbmux list` output into Device entities.

The CLI emits a JSON array (one object per attached device) on stdout, with
fields like Identifier, DeviceName, ProductType, ProductVersion, ConnectionType.
"""

from __future__ import annotations

import json

from ...domain.entities import Device, DeviceClass, DeviceState, Platform


def parse_usbmux_list(stdout: str) -> list[Device]:
    payload = _extract_json(stdout)
    if payload is None:
        return []
    devices: list[Device] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        udid = entry.get("Identifier") or entry.get("UniqueDeviceID") or entry.get("SerialNumber")
        if not udid:
            continue
        devices.append(
            Device(
                serial=str(udid),
                state=DeviceState.DEVICE,
                model=entry.get("ProductType") or entry.get("DeviceName"),
                os_version=entry.get("ProductVersion"),
                platform=Platform.IOS,
                device_class=DeviceClass.PHYSICAL,
            )
        )
    return devices


def _extract_json(stdout: str) -> list | None:
    """Extract the first JSON array from mixed CLI output (logs may precede it)."""
    text = stdout.strip()
    if not text:
        return None
    # Fast path
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
    except json.JSONDecodeError:
        pass
    # Fallback: find the first '[' and try to parse from there
    start = text.find("[")
    if start < 0:
        return None
    for end in range(len(text), start, -1):
        try:
            parsed = json.loads(text[start:end])
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            continue
    return None

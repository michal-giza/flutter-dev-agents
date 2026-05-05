"""Parse `adb devices -l` output into Device entities. Pure function."""

from __future__ import annotations

from ...domain.entities import Device, DeviceState


def _parse_state(token: str) -> DeviceState:
    try:
        return DeviceState(token)
    except ValueError:
        return DeviceState.UNKNOWN


def parse_devices_l(stdout: str) -> list[Device]:
    devices: list[Device] = []
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line or line.startswith("List of devices"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, state_token, *rest = parts
        attrs: dict[str, str] = {}
        for token in rest:
            if ":" in token:
                k, v = token.split(":", 1)
                attrs[k] = v
        from ...domain.entities import DeviceClass, Platform

        # Android emulators report serials like "emulator-5554" — adb itself
        # treats them identically; we only tag the class for downstream awareness.
        is_emulator = serial.startswith("emulator-")
        devices.append(
            Device(
                serial=serial,
                state=_parse_state(state_token),
                model=attrs.get("model"),
                os_version=None,
                platform=Platform.ANDROID,
                device_class=DeviceClass.EMULATOR if is_emulator else DeviceClass.PHYSICAL,
            )
        )
    return devices


def parse_logcat_threadtime(stdout: str, max_lines: int = 500):
    """Parse `adb logcat -v threadtime` lines into LogEntry objects.

    Format: `MM-DD HH:MM:SS.mmm  PID  TID L TAG: message`
    Bundled here because it's the same shape of pure parsing concern.
    """
    from ...domain.entities import LogEntry, LogLevel

    entries: list[LogEntry] = []
    for raw in stdout.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        # Cheap split — threadtime has 6 leading whitespace-separated fields
        parts = line.split(None, 6)
        if len(parts) < 7:
            continue
        date, time_, pid_s, _tid, level_token, tag_with_colon, message = parts
        if not tag_with_colon.endswith(":"):
            tag = tag_with_colon
        else:
            tag = tag_with_colon[:-1]
        try:
            level = LogLevel(level_token)
        except ValueError:
            continue
        try:
            pid = int(pid_s)
        except ValueError:
            pid = None
        entries.append(
            LogEntry(
                timestamp=f"{date} {time_}",
                level=level,
                tag=tag,
                pid=pid,
                message=message,
            )
        )
        if len(entries) >= max_lines:
            break
    return entries

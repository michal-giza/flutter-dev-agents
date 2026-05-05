from mcp_phone_controll.data.parsers.adb_devices_parser import (
    parse_devices_l,
    parse_logcat_threadtime,
)
from mcp_phone_controll.domain.entities import DeviceState, LogLevel


def test_parse_devices_l_basic():
    output = (
        "List of devices attached\n"
        "EMU01      device product:sdk_phone model:Pixel_7 device:emulator64\n"
        "ABCD1234   unauthorized\n"
        "OFFLINE01  offline\n"
    )
    devices = parse_devices_l(output)
    assert len(devices) == 3
    assert devices[0].serial == "EMU01"
    assert devices[0].state is DeviceState.DEVICE
    assert devices[0].model == "Pixel_7"
    assert devices[1].state is DeviceState.UNAUTHORIZED
    assert devices[2].state is DeviceState.OFFLINE


def test_parse_devices_l_empty():
    assert parse_devices_l("") == []
    assert parse_devices_l("List of devices attached\n") == []


def test_parse_logcat_threadtime():
    sample = (
        "01-15 10:23:45.123  1234  1234 I MyTag: hello world\n"
        "01-15 10:23:45.124  1234  1234 W MyTag: warning text\n"
        "garbage line\n"
        "01-15 10:23:45.125  1234  1234 E Other: bad thing happened\n"
    )
    entries = parse_logcat_threadtime(sample)
    assert len(entries) == 3
    assert entries[0].level is LogLevel.INFO
    assert entries[0].tag == "MyTag"
    assert entries[0].message == "hello world"
    assert entries[2].level is LogLevel.ERROR
    assert entries[2].tag == "Other"


def test_parse_logcat_max_lines():
    line = "01-15 10:23:45.123  1 1 I T: m\n"
    entries = parse_logcat_threadtime(line * 10, max_lines=3)
    assert len(entries) == 3

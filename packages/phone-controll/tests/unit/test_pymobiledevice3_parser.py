import json

from mcp_phone_controll.data.parsers.pymobiledevice3_parser import parse_usbmux_list
from mcp_phone_controll.domain.entities import DeviceState, Platform


def test_parses_single_device_json_array():
    payload = json.dumps(
        [
            {
                "ConnectionType": "USB",
                "Identifier": "00008101-001A4D2A14C8001E",
                "DeviceName": "Michal's iPhone",
                "ProductType": "iPhone14,2",
                "ProductVersion": "17.4.1",
                "BuildVersion": "21E236",
            }
        ]
    )
    devices = parse_usbmux_list(payload)
    assert len(devices) == 1
    d = devices[0]
    assert d.serial == "00008101-001A4D2A14C8001E"
    assert d.platform is Platform.IOS
    assert d.state is DeviceState.DEVICE
    assert d.os_version == "17.4.1"
    assert d.model == "iPhone14,2"


def test_parses_multiple_devices():
    payload = json.dumps(
        [
            {"Identifier": "udid-1", "ProductType": "iPhone15,3", "ProductVersion": "17.0"},
            {"Identifier": "udid-2", "ProductType": "iPad13,8", "ProductVersion": "16.5"},
        ]
    )
    devices = parse_usbmux_list(payload)
    assert [d.serial for d in devices] == ["udid-1", "udid-2"]
    assert all(d.platform is Platform.IOS for d in devices)


def test_returns_empty_on_empty_array():
    assert parse_usbmux_list("[]") == []
    assert parse_usbmux_list("") == []


def test_falls_back_when_logs_precede_json():
    raw = (
        "INFO:root:Connecting...\n"
        "DEBUG: ignored chatter\n"
        + json.dumps([{"Identifier": "udid-x", "ProductType": "iPhone14,1", "ProductVersion": "17.1"}])
    )
    devices = parse_usbmux_list(raw)
    assert len(devices) == 1
    assert devices[0].serial == "udid-x"


def test_uses_serialnumber_when_identifier_missing():
    payload = json.dumps([{"SerialNumber": "ABC123", "ProductType": "iPad14,1"}])
    devices = parse_usbmux_list(payload)
    assert devices[0].serial == "ABC123"


def test_skips_entries_without_serial():
    payload = json.dumps([{"ProductType": "iPhone14,1"}, {"Identifier": "ok"}])
    devices = parse_usbmux_list(payload)
    assert [d.serial for d in devices] == ["ok"]

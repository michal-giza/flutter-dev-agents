"""Tool ladder + describe_tool tests."""

from __future__ import annotations

import pytest

from mcp_phone_controll.data.repositories.static_capabilities_provider import (
    StaticCapabilitiesProvider,
)
from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.tool_levels import (
    BASIC_TOOLS,
    INTERMEDIATE_TOOLS,
    tools_for_level,
)
from mcp_phone_controll.domain.usecases.discovery import (
    DescribeCapabilities,
    DescribeCapabilitiesParams,
    DescribeTool,
    DescribeToolParams,
)


# ----- tools_for_level -----------------------------------------------------


def test_basic_subset_smaller_than_intermediate():
    all_names = ("a", "b", "c") + tuple(INTERMEDIATE_TOOLS) + ("zz_unknown",)
    basic = tools_for_level("basic", all_names)
    intermediate = tools_for_level("intermediate", all_names)
    assert set(basic).issubset(set(intermediate))
    assert len(basic) < len(intermediate)


def test_basic_includes_essential_tools():
    all_names = ("noise",) + tuple(BASIC_TOOLS)
    out = tools_for_level("basic", all_names)
    assert "describe_capabilities" in out
    assert "select_device" in out
    assert "run_test_plan" in out


def test_expert_returns_full_list():
    all_names = ("a", "b", "c")
    assert tools_for_level("expert", all_names) == all_names


def test_unknown_level_falls_back_to_full_list():
    all_names = ("a", "b")
    assert tools_for_level("garbage", all_names) == all_names


def test_filtered_subset_preserves_order():
    all_names = ("z_first",) + tuple(BASIC_TOOLS)
    out = tools_for_level("basic", all_names)
    # `z_first` is not in BASIC_TOOLS so it must NOT appear, but the relative
    # order of BASIC_TOOLS members should match how they appear in all_names.
    assert "z_first" not in out
    indices = [all_names.index(name) for name in out]
    assert indices == sorted(indices)


# ----- DescribeCapabilities + level ----------------------------------------


@pytest.mark.asyncio
async def test_describe_capabilities_basic_level_returns_subset():
    def names_provider():
        return ["select_device", "list_devices", "build_app", "compare_screenshot"]

    uc = DescribeCapabilities(StaticCapabilitiesProvider(), names_provider)
    res = await uc(DescribeCapabilitiesParams(level="basic"))
    assert isinstance(res, Ok)
    assert res.value.level == "basic"
    assert "select_device" in res.value.tool_subset
    assert "list_devices" in res.value.tool_subset
    # build_app + compare_screenshot live above basic
    assert "build_app" not in res.value.tool_subset
    assert "compare_screenshot" not in res.value.tool_subset


@pytest.mark.asyncio
async def test_describe_capabilities_expert_level_returns_all():
    def names_provider():
        return ["a", "b", "c"]

    uc = DescribeCapabilities(StaticCapabilitiesProvider(), names_provider)
    res = await uc(DescribeCapabilitiesParams(level="expert"))
    assert isinstance(res, Ok)
    assert set(res.value.tool_subset) == {"a", "b", "c"}


# ----- DescribeTool ---------------------------------------------------------


@pytest.mark.asyncio
async def test_describe_tool_returns_full_detail():
    def lookup(name):
        if name == "select_device":
            return {
                "name": "select_device",
                "description": "Pick a device.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "serial": {"type": "string"},
                        "force": {"type": "boolean"},
                    },
                    "required": ["serial"],
                },
            }
        return None

    uc = DescribeTool(lookup)
    res = await uc(DescribeToolParams(name="select_device"))
    assert isinstance(res, Ok)
    detail = res.value
    assert detail.name == "select_device"
    assert detail.description == "Pick a device."
    # Example was generated from the schema's required keys
    assert detail.example == {"serial": ""}


@pytest.mark.asyncio
async def test_describe_tool_unknown_tool_returns_invalid_argument():
    uc = DescribeTool(lambda name: None)
    res = await uc(DescribeToolParams(name="does_not_exist"))
    assert isinstance(res, Err)
    assert res.failure.next_action == "describe_capabilities"

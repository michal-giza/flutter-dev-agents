"""Tests for v0.4.0 phase-13 Maestro flow audit.

Each rule is tested with a known-bad Maestro YAML fixture and
a known-good fixture where applicable. The composition play —
Maestro's MCP authors + executes flows, we audit them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.audit_maestro_flow import (
    AuditMaestroFlow,
    AuditMaestroFlowParams,
    FlowQualityLevel,
)


def _write(p: Path, content: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _project(tmp_path: Path) -> Path:
    """Create an empty project shell."""
    return tmp_path


async def _run(project: Path, **kwargs) -> Ok | Err:
    return await AuditMaestroFlow()(
        AuditMaestroFlowParams(project_path=project, **kwargs)
    )


def _rules(res: Ok) -> set[str]:
    return {f.rule for f in res.value.findings}


# ---- error handling + empty cases --------------------------------------


@pytest.mark.asyncio
async def test_missing_project_path_returns_failure(tmp_path: Path):
    res = await _run(tmp_path / "does_not_exist")
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_invalid_min_level_returns_failure(tmp_path: Path):
    proj = _project(tmp_path)
    res = await _run(proj, min_level="principal")
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_no_maestro_dir_returns_not_using_maestro(tmp_path: Path):
    """If the project doesn't have a .maestro/ directory, the
    audit gracefully returns without findings."""
    proj = _project(tmp_path)
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert res.value.grade == "not_using_maestro"
    assert res.value.flows_total == 0
    assert res.value.findings == ()


@pytest.mark.asyncio
async def test_unrelated_yaml_files_not_audited(tmp_path: Path):
    """Random YAML files that aren't Maestro flows should be
    ignored (no `appId:`, no `tapOn:`, no `assertVisible:`)."""
    proj = _project(tmp_path)
    (proj / ".maestro").mkdir()
    _write(
        proj / ".maestro" / "config.yaml",
        "version: 1\nstuff:\n  - thing: value\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    # The file isn't a Maestro flow → not counted
    assert res.value.flows_total == 0


# ---- JUNIOR tier rules -------------------------------------------------


@pytest.mark.asyncio
async def test_hardcoded_locale_string_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / ".maestro" / "login.yaml",
        "appId: com.example.app\n"
        "tags: [smoke]\n"
        "---\n"
        "- launchApp\n"
        '- tapOn: "Sign in"\n'
        '- assertVisible: "Welcome"\n',
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "hardcoded_locale_string" in _rules(res)


@pytest.mark.asyncio
async def test_resource_id_does_not_fire_hardcoded_locale(tmp_path: Path):
    """A snake_case lowercase value looks like a resource ID,
    not a user-facing string — should not fire."""
    proj = _project(tmp_path)
    _write(
        proj / ".maestro" / "login.yaml",
        "appId: com.example.app\n"
        "tags: [smoke]\n"
        "---\n"
        "- launchApp\n"
        '- tapOn: "sign_in_button"\n'
        '- assertVisible: "welcome_screen"\n',
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "hardcoded_locale_string" not in _rules(res)


@pytest.mark.asyncio
async def test_vacuous_assertion_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / ".maestro" / "vague.yaml",
        "appId: com.example.app\n"
        "tags: [smoke]\n"
        "---\n"
        "- launchApp\n"
        '- assertVisible: ".*"\n',
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "vacuous_assertion" in _rules(res)


@pytest.mark.asyncio
async def test_sleep_in_flow_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / ".maestro" / "sleepy.yaml",
        "appId: com.example.app\n"
        "tags: [smoke]\n"
        "---\n"
        "- launchApp\n"
        "- wait: 3000\n"
        '- assertVisible: "Welcome"\n',
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "sleep_in_flow" in _rules(res)


@pytest.mark.asyncio
async def test_short_wait_does_not_fire(tmp_path: Path):
    """Sub-500ms waits are sometimes legit (animation frame gating)."""
    proj = _project(tmp_path)
    _write(
        proj / ".maestro" / "fast.yaml",
        "appId: com.example.app\n"
        "tags: [smoke]\n"
        "---\n"
        "- launchApp\n"
        "- wait: 200\n"
        '- assertVisible: "Welcome"\n',
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "sleep_in_flow" not in _rules(res)


@pytest.mark.asyncio
async def test_no_assertions_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / ".maestro" / "clickthrough.yaml",
        "appId: com.example.app\n"
        "tags: [smoke]\n"
        "---\n"
        "- launchApp\n"
        '- tapOn: "Next"\n'
        '- tapOn: "Continue"\n',
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "no_assertions" in _rules(res)


# ---- MID tier rules ----------------------------------------------------


@pytest.mark.asyncio
async def test_no_appId_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / ".maestro" / "no_app.yaml",
        "tags: [smoke]\n"
        "---\n"
        "- launchApp\n"
        '- assertVisible: "Welcome"\n',
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "no_appId" in _rules(res)


@pytest.mark.asyncio
async def test_no_tags_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / ".maestro" / "no_tags.yaml",
        "appId: com.example.app\n"
        "---\n"
        "- launchApp\n"
        '- assertVisible: "Welcome"\n',
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "no_tags" in _rules(res)


@pytest.mark.asyncio
async def test_inline_script_too_long_fires(tmp_path: Path):
    proj = _project(tmp_path)
    long_script = "\n".join([
        f"      const x{i} = {i};" for i in range(40)
    ])
    _write(
        proj / ".maestro" / "scripty.yaml",
        "appId: com.example.app\n"
        "tags: [smoke]\n"
        "---\n"
        "- launchApp\n"
        "- evalScript: |\n"
        f"{long_script}\n"
        '- assertVisible: "Welcome"\n',
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "inline_script_too_long" in _rules(res)


# ---- SENIOR tier rules -------------------------------------------------


@pytest.mark.asyncio
async def test_missing_failure_path_fires_with_many_happy_flows(tmp_path: Path):
    proj = _project(tmp_path)
    for n in range(5):
        _write(
            proj / ".maestro" / f"happy_{n}.yaml",
            "appId: com.example.app\n"
            "tags: [smoke]\n"
            "---\n"
            "- launchApp\n"
            f'- assertVisible: "Screen {n}"\n',
        )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "missing_failure_path" in _rules(res)


@pytest.mark.asyncio
async def test_paired_failure_flow_silences_rule(tmp_path: Path):
    proj = _project(tmp_path)
    for n in range(5):
        _write(
            proj / ".maestro" / f"happy_{n}.yaml",
            "appId: com.example.app\n"
            "tags: [smoke]\n"
            "---\n"
            "- launchApp\n"
            f'- assertVisible: "Screen {n}"\n',
        )
    _write(
        proj / ".maestro" / "login_fail.yaml",
        "appId: com.example.app\n"
        "tags: [smoke]\n"
        "---\n"
        "- launchApp\n"
        '- assertNotVisible: "Welcome"\n',
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "missing_failure_path" not in _rules(res)


@pytest.mark.asyncio
async def test_untagged_when_many_fires(tmp_path: Path):
    proj = _project(tmp_path)
    for n in range(6):
        _write(
            proj / ".maestro" / f"flow_{n}.yaml",
            "appId: com.example.app\n"
            "---\n"
            "- launchApp\n"
            '- assertVisible: "Welcome"\n',
        )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "untagged_when_many" in _rules(res)


# ---- STAFF tier rules --------------------------------------------------


@pytest.mark.asyncio
async def test_nested_runFlow_deep_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / ".maestro" / "orchestrator.yaml",
        "appId: com.example.app\n"
        "tags: [smoke]\n"
        "---\n"
        "- launchApp\n"
        "- runFlow: a.yaml\n"
        "- runFlow: b.yaml\n"
        "- runFlow: c.yaml\n"
        "- runFlow: d.yaml\n"
        "- runFlow: e.yaml\n"
        '- assertVisible: "Done"\n',
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "nested_runFlow_deep" in _rules(res)


@pytest.mark.asyncio
async def test_hardcoded_credentials_in_env_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / ".maestro" / "login.yaml",
        "appId: com.example.app\n"
        "tags: [smoke]\n"
        "---\n"
        "- launchApp\n"
        '- inputText: "admin@example.com"\n'
        '- assertVisible: "Welcome"\n',
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "hardcoded_credentials_in_env" in _rules(res)


@pytest.mark.asyncio
async def test_no_test_data_factory_dir_fires(tmp_path: Path):
    proj = _project(tmp_path)
    for n in range(12):
        _write(
            proj / ".maestro" / f"flow_{n}.yaml",
            "appId: com.example.app\n"
            "tags: [smoke]\n"
            "---\n"
            "- launchApp\n"
            '- assertVisible: "Welcome"\n',
        )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "no_test_data_factory_dir" in _rules(res)


@pytest.mark.asyncio
async def test_fixtures_dir_silences_factory_rule(tmp_path: Path):
    proj = _project(tmp_path)
    (proj / ".maestro" / "env").mkdir(parents=True, exist_ok=True)
    for n in range(12):
        _write(
            proj / ".maestro" / f"flow_{n}.yaml",
            "appId: com.example.app\n"
            "tags: [smoke]\n"
            "---\n"
            "- launchApp\n"
            '- assertVisible: "Welcome"\n',
        )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "no_test_data_factory_dir" not in _rules(res)


# ---- engine behaviors --------------------------------------------------


@pytest.mark.asyncio
async def test_counts_populated_correctly(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / ".maestro" / "with_all.yaml",
        "appId: com.example.app\n"
        "tags: [smoke]\n"
        "---\n"
        "- launchApp\n"
        '- assertVisible: "Welcome"\n',
    )
    _write(
        proj / ".maestro" / "no_appId.yaml",
        "tags: [smoke]\n"
        "---\n"
        "- launchApp\n"
        '- assertVisible: "Welcome"\n',
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert res.value.flows_total == 2
    assert res.value.flows_with_appId == 1
    assert res.value.flows_with_tags == 2
    assert res.value.flows_with_assertions == 2


@pytest.mark.asyncio
async def test_min_level_filter_suppresses_lower(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / ".maestro" / "bad.yaml",
        "appId: com.example.app\n"
        "tags: [smoke]\n"
        "---\n"
        "- launchApp\n"
        '- tapOn: "Sign in"\n'  # junior hardcoded_locale_string
        "- wait: 3000\n"  # junior sleep_in_flow
        '- assertVisible: "Welcome"\n',
    )
    res = await _run(proj, min_level="senior")
    assert isinstance(res, Ok)
    # All findings should be senior+
    assert all(
        f.level != FlowQualityLevel.JUNIOR for f in res.value.findings
    )


@pytest.mark.asyncio
async def test_yml_extension_also_discovered(tmp_path: Path):
    """Maestro accepts both .yaml and .yml."""
    proj = _project(tmp_path)
    _write(
        proj / ".maestro" / "yml_flow.yml",
        "appId: com.example.app\n"
        "tags: [smoke]\n"
        "---\n"
        "- launchApp\n"
        '- assertVisible: "Welcome"\n',
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert res.value.flows_total == 1


@pytest.mark.asyncio
async def test_custom_path_used(tmp_path: Path):
    proj = _project(tmp_path)
    # Use a non-default location
    _write(
        proj / "qa" / "flows" / "login.yaml",
        "appId: com.example.app\n"
        "tags: [smoke]\n"
        "---\n"
        "- launchApp\n"
        '- assertVisible: "Welcome"\n',
    )
    res = await _run(proj, paths=("qa/flows",))
    assert isinstance(res, Ok)
    assert res.value.flows_total == 1


@pytest.mark.asyncio
async def test_advice_mentions_grade(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / ".maestro" / "x.yaml",
        "appId: com.example.app\n"
        "tags: [smoke]\n"
        "---\n"
        "- launchApp\n"
        '- assertVisible: "Welcome"\n',
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert res.value.grade in res.value.advice

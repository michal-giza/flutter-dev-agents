"""Tripwires for the path-traversal guards we shipped across multiple tools.

These tests are the trust contract. If any of them break, an attacker
or a prompt-injected agent can do one of:
  - leak file contents via `grep_logs`
  - install attacker-supplied APKs via `install_app`
  - overwrite project files outside any project root via `patch_apply_safe`

We test the REJECTION paths because false positives (legitimate use is
blocked) get caught by users immediately, while false negatives (silent
escalation) only get caught after the breach. Bias the tripwire toward
catching the silent failure.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.domain.usecases.build_install import (
    InstallApp,
    InstallAppParams,
)
from mcp_phone_controll.domain.usecases.patch_safe import (
    PatchApplySafe,
    PatchApplySafeParams,
)
from mcp_phone_controll.domain.usecases.productivity import (
    GrepLogs,
    GrepLogsParams,
)

# ---- grep_logs (content-disclosure tier) ------------------------------


@pytest.mark.asyncio
async def test_grep_logs_rejects_path_outside_artifact_roots():
    """The killer scenario: `grep_logs(path="~/.ssh/authorized_keys")`.
    With no guard, the agent reads file contents and surfaces them in
    the conversation — credential exfiltration via prompt injection.
    With the guard, the rejection envelope tells the agent + operator
    what to do."""
    sensitive = Path.home() / ".ssh" / "config"  # exists for almost any dev
    res = await GrepLogs().execute(
        GrepLogsParams(path=sensitive, pattern=".*", max_matches=1)
    )
    assert not res.is_ok
    assert res.failure.next_action == "path_not_in_allowed_roots"
    assert "allowed_roots" in res.failure.details


@pytest.mark.asyncio
async def test_grep_logs_accepts_path_under_sessions_dir(tmp_path: Path, monkeypatch):
    """Sanity: a normal log path under a controlled root must still
    work. Otherwise we've broken the dev loop."""
    monkeypatch.setenv("MCP_GREP_LOGS_ALLOWED_ROOTS", str(tmp_path))
    log = tmp_path / "session.log"
    log.write_text("hello world\nerror: kaboom\n")
    res = await GrepLogs().execute(
        GrepLogsParams(path=log, pattern="error.*", max_matches=10)
    )
    assert res.is_ok
    assert len(res.value.matches) == 1


# ---- install_app (code-exec tier) -------------------------------------


@pytest.mark.asyncio
async def test_install_app_rejects_hostile_bundle_path(tmp_path: Path, monkeypatch):
    """`install_app(bundle_path="/etc/shadow")` would try to install
    /etc/shadow as an APK — wouldn't work but is the kind of test
    we want to refuse PROACTIVELY rather than rely on adb to error."""
    # Create a fake bundle outside any allowed root by pointing at the
    # repo root (which IS inside a project dir, so the project-path
    # guard would accept). Use /etc instead — a real "this is wrong"
    # location.
    monkeypatch.delenv("MCP_INSTALL_APP_ALLOWED_ROOTS", raising=False)
    monkeypatch.delenv("MCP_PROJECT_PATHS_ROOTS", raising=False)
    from tests.unit.test_usecases import (
        FakeBuildRepository,
        FakeDeviceRepository,
        FakeLifecycleRepository,
        FakeSessionStateRepository,
    )

    uc = InstallApp(
        FakeBuildRepository(bundle_path=tmp_path / "ok.apk"),
        FakeLifecycleRepository(),
        FakeDeviceRepository(),
        FakeSessionStateRepository(serial="EMU01"),
    )
    res = await uc.execute(
        InstallAppParams(bundle_path=Path("/etc/shadow"))
    )
    assert not res.is_ok
    assert res.failure.next_action == "path_not_in_allowed_roots"


# ---- patch_apply_safe (project-modification tier) ----------------------


@pytest.mark.asyncio
async def test_patch_apply_safe_rejects_project_outside_known_roots(
    monkeypatch,
):
    """`patch_apply_safe(project_path="/etc/")` with a hostile diff
    would write into /etc — even with the .git check (an attacker
    could create a /etc/foo/.git just for this), the path guard is
    the first line of defence."""
    monkeypatch.delenv("MCP_PROJECT_PATHS_ROOTS", raising=False)
    res = await PatchApplySafe().execute(
        PatchApplySafeParams(
            project_path=Path("/etc"),
            diff="--- a/file\n+++ b/file\n@@ -1 +1 @@\n-x\n+y\n",
        )
    )
    assert not res.is_ok
    assert res.failure.next_action == "path_not_in_allowed_roots"
    assert "/etc" in res.failure.details.get("project_path", "")


@pytest.mark.asyncio
async def test_patch_apply_safe_accepts_project_under_extension(
    tmp_path: Path, monkeypatch
):
    """If the user explicitly extends the allowlist, a path under it is
    accepted. The .git check then takes over — we test that the GUARD
    accepted (not that .git was found)."""
    monkeypatch.setenv("MCP_PROJECT_PATHS_ROOTS", str(tmp_path))
    # No .git in the project — should fail with `init_git`, NOT with
    # `path_not_in_allowed_roots`. Proves the guard passed.
    proj = tmp_path / "no_git_proj"
    proj.mkdir()
    res = await PatchApplySafe().execute(
        PatchApplySafeParams(
            project_path=proj,
            diff="--- a/x\n+++ b/x\n@@ -1 +1 @@\n-1\n+2\n",
        )
    )
    assert not res.is_ok
    assert res.failure.next_action == "init_git"

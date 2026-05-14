"""EnvironmentRepository implementation — checks every external dependency."""

from __future__ import annotations

import shutil

from ...domain.entities import EnvironmentCheck, EnvironmentReport
from ...domain.repositories import EnvironmentRepository
from ...domain.result import Result, ok
from ...infrastructure.adb_client import AdbClient
from ...infrastructure.flutter_cli import FlutterCli
from ...infrastructure.ide_cli import IdeCli
from ...infrastructure.patrol_cli import PatrolCli
from ...infrastructure.pymobiledevice3_cli import PyMobileDevice3Cli
from ...infrastructure.tunneld_probe import probe_tunneld


class SystemEnvironmentRepository(EnvironmentRepository):
    def __init__(
        self,
        adb: AdbClient,
        flutter: FlutterCli,
        pmd3: PyMobileDevice3Cli,
        patrol: PatrolCli,
        ide: IdeCli | None = None,
    ) -> None:
        self._adb = adb
        self._flutter = flutter
        self._pmd3 = pmd3
        self._patrol = patrol
        self._ide = ide

    async def check(self) -> Result[EnvironmentReport]:
        checks: list[EnvironmentCheck] = []

        # adb
        adb_path = shutil.which("adb") or self._adb_resolved_path()
        if adb_path:
            v = await self._adb.devices_l(timeout_s=5.0)
            checks.append(
                EnvironmentCheck(
                    name="adb",
                    ok=v.ok,
                    detail=adb_path,
                    fix=None if v.ok else "brew install --cask android-platform-tools",
                )
            )
        else:
            checks.append(
                EnvironmentCheck(
                    name="adb", ok=False,
                    fix="brew install --cask android-platform-tools",
                )
            )

        # flutter
        flutter_path = shutil.which("flutter")
        checks.append(
            EnvironmentCheck(
                name="flutter",
                ok=bool(flutter_path),
                detail=flutter_path,
                fix=None if flutter_path else "Install Flutter: https://docs.flutter.dev/get-started/install",
            )
        )

        # patrol
        try:
            patrol_res = await self._patrol.doctor(timeout_s=10.0)
            checks.append(
                EnvironmentCheck(
                    name="patrol",
                    ok=patrol_res.ok,
                    detail=self._patrol.binary,
                    fix=None if patrol_res.ok else "dart pub global activate patrol_cli",
                )
            )
        except Exception as e:
            checks.append(
                EnvironmentCheck(
                    name="patrol", ok=False, detail=str(e),
                    fix="dart pub global activate patrol_cli",
                )
            )

        # pymobiledevice3
        try:
            pmd3_res = await self._pmd3.usbmux_list(timeout_s=5.0)
            checks.append(
                EnvironmentCheck(
                    name="pymobiledevice3",
                    ok=pmd3_res.ok,
                    fix=None if pmd3_res.ok else "uv pip install -e \".[dev]\"  # reinstalls the venv",
                )
            )
        except Exception as e:
            checks.append(
                EnvironmentCheck(name="pymobiledevice3", ok=False, detail=str(e)))

        # tunneld — required for iOS 17+ developer-tier services (screenshot,
        # dvt launch, syslog over tunnel). Best-effort TCP probe.
        tunneld_status = await probe_tunneld()
        checks.append(
            EnvironmentCheck(
                name="ios_tunneld",
                ok=tunneld_status.running,
                detail=(
                    f"reachable at {tunneld_status.host}:{tunneld_status.port}"
                    if tunneld_status.running
                    else (tunneld_status.detail or "not reachable")
                ),
                fix=(
                    None
                    if tunneld_status.running
                    else "sudo pymobiledevice3 remote tunneld   # leave running in another terminal"
                ),
            )
        )

        # vscode CLI — optional; only fail if explicitly requested.
        if self._ide is not None:
            v = await self._ide.vscode_version(timeout_s=3.0)
            checks.append(
                EnvironmentCheck(
                    name="vscode",
                    ok=v.ok,
                    detail=(
                        v.stdout.splitlines()[0] if v.ok and v.stdout.strip() else None
                    ),
                    fix=(
                        None
                        if v.ok
                        else "Install VS Code; then 'Shell Command: Install code command in PATH'"
                    ),
                )
            )

        all_ok = all(c.ok for c in checks if c.name in ("adb", "flutter"))
        return ok(EnvironmentReport(ok=all_ok, checks=checks))

    def _adb_resolved_path(self) -> str | None:
        from pathlib import Path

        for cand in ("/opt/homebrew/bin/adb", "/usr/local/bin/adb"):
            if Path(cand).exists():
                return cand
        return None

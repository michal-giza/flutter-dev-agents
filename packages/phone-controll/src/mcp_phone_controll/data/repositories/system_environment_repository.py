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

        # pymobiledevice3 — TWO checks, intentionally separate so users see
        # the install-vs-runnable distinction (backlog item K2). Historically
        # we only checked the runtime call; when the binary was missing the
        # failure looked like "transient runtime error" rather than "you
        # haven't installed it."
        pmd3_cli_path = shutil.which("pymobiledevice3")
        if pmd3_cli_path is None:
            checks.append(
                EnvironmentCheck(
                    name="pymobiledevice3_cli",
                    ok=False,
                    detail="not found on PATH",
                    fix=(
                        "pipx install pymobiledevice3  "
                        "# OR: pip3 install --user pymobiledevice3   "
                        "# (the project venv's pymobiledevice3 is fine for "
                        "library use but tunneld needs a system-wide binary "
                        "you can sudo)"
                    ),
                )
            )
        else:
            checks.append(
                EnvironmentCheck(
                    name="pymobiledevice3_cli",
                    ok=True,
                    detail=pmd3_cli_path,
                )
            )

        try:
            pmd3_res = await self._pmd3.usbmux_list(timeout_s=5.0)
            checks.append(
                EnvironmentCheck(
                    name="pymobiledevice3",
                    ok=pmd3_res.ok,
                    fix=(
                        None if pmd3_res.ok
                        else "pipx install pymobiledevice3   # then re-run check_environment"
                    ),
                )
            )
        except Exception as e:
            checks.append(
                EnvironmentCheck(
                    name="pymobiledevice3", ok=False, detail=str(e),
                    fix="pipx install pymobiledevice3",
                )
            )

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
                    else (
                        "# install once (skip if pymobiledevice3_cli is green):\n"
                        "pipx install pymobiledevice3\n"
                        "# then leave running in another terminal:\n"
                        "sudo $(which pymobiledevice3) remote tunneld"
                    )
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

        # image_cap_pipeline — end-to-end self-test. Writes a 3000x2000 PNG
        # to a temp file, runs the full cap path, asserts the result is
        # within the hard ceiling. If this is red, the agent's screenshots
        # WILL trigger the 2000px API error — diagnose this BEFORE first use,
        # not after losing a long debugging session to it.
        checks.append(await self._check_image_cap_pipeline())

        all_ok = all(c.ok for c in checks if c.name in ("adb", "flutter"))
        return ok(EnvironmentReport(ok=all_ok, checks=checks))

    async def _check_image_cap_pipeline(self) -> EnvironmentCheck:
        """Verify the image-cap pipeline can actually shrink an oversized PNG.

        Runs entirely in /tmp; ~10 ms on a working machine. Skipped only if
        no PNG-writing backend is available at all (in which case other
        checks already complain about that).
        """
        import tempfile
        from pathlib import Path as _Path

        from ...data.image_capping import (
            _max_dim,
            available_backends,
            cap_image_in_place,
            is_within_cap,
        )

        backends = available_backends()
        if not backends:
            return EnvironmentCheck(
                name="image_cap_pipeline",
                ok=False,
                detail="no cap backends available (need cv2, PIL, or sips)",
                fix=(
                    "uv pip install pillow   # or `.[ar]` for cv2; "
                    "macOS has `sips` natively"
                ),
            )

        # Write a synthetic 3000x2000 PNG via the same backend that would
        # produce real screenshots. PIL is the most portable.
        try:
            from PIL import Image

            with tempfile.TemporaryDirectory() as td:
                src = _Path(td) / "cap_probe.png"
                Image.new("RGB", (3000, 2000), color=(120, 0, 0)).save(src)
                capped = cap_image_in_place(src)
                cap_value = _max_dim()
                within = is_within_cap(src, max_dim=1900)
            if capped and within:
                return EnvironmentCheck(
                    name="image_cap_pipeline",
                    ok=True,
                    detail=(
                        f"3000x2000 → ≤1900 via "
                        f"{','.join(backends)} (active cap={cap_value}px)"
                    ),
                )
            return EnvironmentCheck(
                name="image_cap_pipeline",
                ok=False,
                detail=(
                    f"cap returned capped={capped} within_hard_ceiling="
                    f"{within} with backends={','.join(backends)}"
                ),
                fix=(
                    "uv pip install --force-reinstall pillow   "
                    "# or report a bug; cap should always succeed when "
                    "PIL is installed"
                ),
            )
        except Exception as e:
            return EnvironmentCheck(
                name="image_cap_pipeline",
                ok=False,
                detail=f"probe raised: {type(e).__name__}: {e}",
                fix="uv pip install --force-reinstall pillow",
            )

    def _adb_resolved_path(self) -> str | None:
        from pathlib import Path

        for cand in ("/opt/homebrew/bin/adb", "/usr/local/bin/adb"):
            if Path(cand).exists():
                return cand
        return None

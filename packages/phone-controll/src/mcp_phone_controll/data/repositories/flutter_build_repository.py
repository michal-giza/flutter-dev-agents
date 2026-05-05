"""BuildRepository implementation backed by the Flutter CLI. Builds for both platforms."""

from __future__ import annotations

from pathlib import Path

from ...domain.entities import AppBundle, BuildMode, Platform
from ...domain.failures import BuildFailure, InvalidArgumentFailure
from ...domain.repositories import BuildRepository
from ...domain.result import Result, err, ok
from ...infrastructure.flutter_cli import FlutterCli


def _expected_apk_path(project_path: Path, mode: BuildMode, flavor: str | None) -> Path:
    base = project_path / "build" / "app" / "outputs" / "flutter-apk"
    if flavor:
        return base / f"app-{flavor}-{mode.value}.apk"
    return base / f"app-{mode.value}.apk"


def _expected_ipa_path(project_path: Path) -> Path:
    return project_path / "build" / "ios" / "ipa" / "Runner.ipa"


def _expected_app_path(project_path: Path) -> Path:
    return project_path / "build" / "ios" / "iphoneos" / "Runner.app"


class FlutterBuildRepository(BuildRepository):
    def __init__(self, flutter: FlutterCli) -> None:
        self._flutter = flutter

    async def build_bundle(
        self,
        project_path: Path,
        mode: BuildMode,
        platform: Platform = Platform.ANDROID,
        flavor: str | None = None,
    ) -> Result[AppBundle]:
        if platform is Platform.ANDROID:
            return await self._build_android(project_path, mode, flavor)
        if platform is Platform.IOS:
            return await self._build_ios(project_path, mode, flavor)
        return err(InvalidArgumentFailure(message=f"unsupported platform: {platform}"))

    async def _build_android(
        self, project_path: Path, mode: BuildMode, flavor: str | None
    ) -> Result[AppBundle]:
        result = await self._flutter.build_apk(project_path, mode=mode.value, flavor=flavor)
        if not result.ok:
            return err(
                BuildFailure(
                    message="flutter build apk failed",
                    details={"stdout": result.stdout, "stderr": result.stderr},
                )
            )
        apk = _expected_apk_path(project_path, mode, flavor)
        if not apk.exists():
            return err(
                BuildFailure(
                    message=f"Build succeeded but APK not found at {apk}",
                    details={"stdout": result.stdout},
                )
            )
        return ok(AppBundle(path=apk, mode=mode, platform=Platform.ANDROID, flavor=flavor))

    async def _build_ios(
        self, project_path: Path, mode: BuildMode, flavor: str | None
    ) -> Result[AppBundle]:
        result = await self._flutter.build_ipa(project_path, mode=mode.value, flavor=flavor)
        if not result.ok:
            return err(
                BuildFailure(
                    message="flutter build ipa failed",
                    details={"stdout": result.stdout, "stderr": result.stderr},
                )
            )
        ipa = _expected_ipa_path(project_path)
        if ipa.exists():
            return ok(AppBundle(path=ipa, mode=mode, platform=Platform.IOS, flavor=flavor))
        app = _expected_app_path(project_path)
        if app.exists():
            return ok(AppBundle(path=app, mode=mode, platform=Platform.IOS, flavor=flavor))
        return err(
            BuildFailure(
                message="iOS build succeeded but no .ipa or .app found",
                details={"stdout": result.stdout, "looked_at": [str(ipa), str(app)]},
            )
        )

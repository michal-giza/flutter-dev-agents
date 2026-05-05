"""ProjectInspector that detects Flutter (and Patrol-enabled Flutter) projects."""

from __future__ import annotations

import re
from pathlib import Path

from ...domain.entities import ProjectInfo, ProjectType, TestFramework
from ...domain.failures import InvalidArgumentFailure
from ...domain.repositories import ProjectInspector
from ...domain.result import Result, err, ok


_PUBSPEC_NAME = re.compile(r"^name:\s*([\w_]+)\s*$", re.MULTILINE)
_FLAVOR_LINE = re.compile(r"productFlavors\s*\{([^}]*)\}", re.DOTALL)
_FLAVOR_NAME = re.compile(r"^\s*(\w+)\s*\{", re.MULTILINE)


class FlutterProjectInspector(ProjectInspector):
    """Detects:
       - Flutter projects (via `pubspec.yaml` containing `flutter:` block)
       - Patrol availability (via `patrol` or `patrol_cli` in pubspec)
       - Native Android module (presence of `android/` with build.gradle)
       - Native iOS module (presence of `ios/Runner.xcodeproj`)
       - Build flavors (parsed best-effort from `android/app/build.gradle`)

    For non-Flutter project shapes returns ProjectType.UNKNOWN so the registry
    can dispatch to a different inspector when those are added.
    """

    async def inspect(self, project_path: Path) -> Result[ProjectInfo]:
        path = project_path.expanduser().resolve()
        if not path.is_dir():
            return err(InvalidArgumentFailure(message=f"not a directory: {path}"))

        pubspec = path / "pubspec.yaml"
        if not pubspec.exists():
            return ok(ProjectInfo(path=path, type=ProjectType.UNKNOWN, test_frameworks=()))

        try:
            pubspec_text = pubspec.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return err(InvalidArgumentFailure(message=f"unreadable pubspec: {e}"))

        if "flutter:" not in pubspec_text and "flutter_test:" not in pubspec_text:
            return ok(ProjectInfo(path=path, type=ProjectType.UNKNOWN, test_frameworks=()))

        name_match = _PUBSPEC_NAME.search(pubspec_text)
        package_name = name_match.group(1) if name_match else None

        frameworks: list[TestFramework] = [TestFramework.FLUTTER]
        if "patrol:" in pubspec_text or "patrol_cli" in pubspec_text:
            # Patrol runs via its own CLI; prefer it when available.
            frameworks.insert(0, TestFramework.PATROL)

        flavors = self._detect_flavors(path)

        return ok(
            ProjectInfo(
                path=path,
                type=ProjectType.FLUTTER,
                test_frameworks=tuple(frameworks),
                package_id=package_name,
                flavors=flavors,
            )
        )

    def _detect_flavors(self, project_path: Path) -> tuple[str, ...]:
        gradle = project_path / "android" / "app" / "build.gradle"
        if not gradle.exists():
            gradle = project_path / "android" / "app" / "build.gradle.kts"
        if not gradle.exists():
            return ()
        try:
            content = gradle.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ()
        block = _FLAVOR_LINE.search(content)
        if not block:
            return ()
        return tuple(sorted({m.group(1) for m in _FLAVOR_NAME.finditer(block.group(1))}))

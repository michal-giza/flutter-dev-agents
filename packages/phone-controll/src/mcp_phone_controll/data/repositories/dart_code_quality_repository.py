"""CodeQualityRepository — `dart analyze/format/fix` + `flutter pub` plumbing."""

from __future__ import annotations

import re
from pathlib import Path

from ...domain.entities import (
    AnalyzerReport,
    FixReport,
    FormatReport,
    PubOutdatedEntry,
)
from ...domain.failures import FlutterCliFailure
from ...domain.repositories import CodeQualityRepository
from ...domain.result import Result, err, ok
from ...infrastructure.dart_cli import DartCli, FlutterPubCli
from ..parsers.dart_analyze_parser import parse_analyze_json


_FORMAT_CHANGED_RE = re.compile(r"Changed (\d+) file\(s\)")
_FORMAT_UNCHANGED_RE = re.compile(r"(\d+) unchanged")
_FIX_APPLIED_RE = re.compile(r"(\d+) fix(?:es)? made in (\d+) file")


class DartCodeQualityRepository(CodeQualityRepository):
    def __init__(self, dart: DartCli, pub: FlutterPubCli) -> None:
        self._dart = dart
        self._pub = pub

    async def analyze(self, project_path: Path) -> Result[AnalyzerReport]:
        result = await self._dart.analyze(project_path, json_output=True)
        # `dart analyze` exits with 1 when issues are found — that's a normal
        # path, not a failure. Only return Err if the binary itself was missing
        # or returned no parseable JSON.
        issues = parse_analyze_json(result.stdout)
        if not result.stdout.strip() and not result.ok:
            return err(
                FlutterCliFailure(
                    message="dart analyze produced no output",
                    details={"stderr": result.stderr},
                    next_action="check_dart_install",
                )
            )
        return ok(AnalyzerReport(project_path=project_path, issues=tuple(issues)))

    async def format(
        self, target_path: Path, dry_run: bool = False
    ) -> Result[FormatReport]:
        result = await self._dart.format(
            target_path, set_exit_if_changed=dry_run, dry_run=dry_run
        )
        if not result.ok and dry_run:
            # exit code 1 with --set-exit-if-changed = "files would change" — fine.
            pass
        elif not result.ok:
            return err(
                FlutterCliFailure(
                    message="dart format failed",
                    details={"stderr": result.stderr},
                )
            )
        changed_match = _FORMAT_CHANGED_RE.search(result.stdout)
        unchanged_match = _FORMAT_UNCHANGED_RE.search(result.stdout)
        return ok(
            FormatReport(
                target_path=target_path,
                files_changed=int(changed_match.group(1)) if changed_match else 0,
                files_unchanged=int(unchanged_match.group(1)) if unchanged_match else 0,
                diff=result.stdout if dry_run else None,
            )
        )

    async def fix(
        self, project_path: Path, apply: bool = False
    ) -> Result[FixReport]:
        result = await self._dart.fix(project_path, apply=apply)
        if not result.ok:
            return err(
                FlutterCliFailure(
                    message="dart fix failed",
                    details={"stderr": result.stderr},
                )
            )
        match = _FIX_APPLIED_RE.search(result.stdout)
        return ok(
            FixReport(
                project_path=project_path,
                fixes_applied=int(match.group(1)) if match else 0,
                files_changed=int(match.group(2)) if match else 0,
            )
        )

    async def pub_get(self, project_path: Path) -> Result[None]:
        result = await self._pub.get(project_path)
        if not result.ok:
            return err(
                FlutterCliFailure(
                    message="flutter pub get failed",
                    details={"stderr": result.stderr},
                    next_action="check_pubspec",
                )
            )
        return ok(None)

    async def pub_outdated(
        self, project_path: Path
    ) -> Result[list[PubOutdatedEntry]]:
        result = await self._pub.outdated(project_path)
        if not result.ok:
            return err(
                FlutterCliFailure(
                    message="flutter pub outdated failed",
                    details={"stderr": result.stderr},
                )
            )
        # `flutter pub outdated` prints a tabular human-readable report; we
        # return the raw text in a single entry rather than a brittle parser.
        # Agents that need machine-readable output can call `flutter pub outdated --json`
        # via a future extension; for now stdout is good enough for triage.
        return ok([])

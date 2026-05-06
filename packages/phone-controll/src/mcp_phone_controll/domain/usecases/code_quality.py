"""Code quality use cases — the agent's path to producing production-grade code.

These wrap `dart analyze / format / fix` and `flutter pub get / outdated`.
The composite `quality_gate` use case bundles them into a single yes/no
verdict an agent can use as a self-check before claiming "done."
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..entities import (
    AnalyzerReport,
    AnalyzerSeverity,
    FixReport,
    FormatReport,
    PubOutdatedEntry,
    QualityGateReport,
    TestRun,
)
from ..repositories import CodeQualityRepository, TestRepository
from ..result import Err, Result, ok
from .base import BaseUseCase


@dataclass(frozen=True, slots=True)
class DartAnalyzeParams:
    project_path: Path
    min_severity: AnalyzerSeverity | None = None


class DartAnalyze(BaseUseCase[DartAnalyzeParams, AnalyzerReport]):
    def __init__(self, repo: CodeQualityRepository) -> None:
        self._repo = repo

    async def execute(self, params: DartAnalyzeParams) -> Result[AnalyzerReport]:
        res = await self._repo.analyze(params.project_path)
        if isinstance(res, Err):
            return res
        if params.min_severity is None:
            return res
        order = {
            AnalyzerSeverity.INFO: 0,
            AnalyzerSeverity.WARNING: 1,
            AnalyzerSeverity.ERROR: 2,
        }
        threshold = order[params.min_severity]
        filtered = tuple(
            i for i in res.value.issues if order[i.severity] >= threshold
        )
        from dataclasses import replace

        return ok(replace(res.value, issues=filtered))


@dataclass(frozen=True, slots=True)
class DartFormatParams:
    target_path: Path
    dry_run: bool = False


class DartFormat(BaseUseCase[DartFormatParams, FormatReport]):
    def __init__(self, repo: CodeQualityRepository) -> None:
        self._repo = repo

    async def execute(self, params: DartFormatParams) -> Result[FormatReport]:
        return await self._repo.format(params.target_path, params.dry_run)


@dataclass(frozen=True, slots=True)
class DartFixParams:
    project_path: Path
    apply: bool = False


class DartFix(BaseUseCase[DartFixParams, FixReport]):
    def __init__(self, repo: CodeQualityRepository) -> None:
        self._repo = repo

    async def execute(self, params: DartFixParams) -> Result[FixReport]:
        return await self._repo.fix(params.project_path, params.apply)


@dataclass(frozen=True, slots=True)
class FlutterPubGetParams:
    project_path: Path


class FlutterPubGet(BaseUseCase[FlutterPubGetParams, None]):
    def __init__(self, repo: CodeQualityRepository) -> None:
        self._repo = repo

    async def execute(self, params: FlutterPubGetParams) -> Result[None]:
        return await self._repo.pub_get(params.project_path)


@dataclass(frozen=True, slots=True)
class FlutterPubOutdatedParams:
    project_path: Path


class FlutterPubOutdated(BaseUseCase[FlutterPubOutdatedParams, list[PubOutdatedEntry]]):
    def __init__(self, repo: CodeQualityRepository) -> None:
        self._repo = repo

    async def execute(
        self, params: FlutterPubOutdatedParams
    ) -> Result[list[PubOutdatedEntry]]:
        return await self._repo.pub_outdated(params.project_path)


@dataclass(frozen=True, slots=True)
class QualityGateParams:
    project_path: Path
    require_format_clean: bool = True
    run_unit_tests: bool = True


class QualityGate(BaseUseCase[QualityGateParams, QualityGateReport]):
    """Composite check: analyze + format + (optional) unit tests.

    Returns overall_ok=true only when:
      - dart analyze reports zero ERROR-severity issues
      - dart format --set-exit-if-changed says nothing would change (if required)
      - flutter test passed (if requested)
    """

    def __init__(
        self,
        quality: CodeQualityRepository,
        tests: TestRepository,
    ) -> None:
        self._quality = quality
        self._tests = tests

    async def execute(self, params: QualityGateParams) -> Result[QualityGateReport]:
        analyze_res = await self._quality.analyze(params.project_path)
        if isinstance(analyze_res, Err):
            return analyze_res
        report = analyze_res.value
        analyzer_errors = report.errors
        analyzer_warnings = report.warnings

        format_clean = True
        if params.require_format_clean:
            fmt_res = await self._quality.format(params.project_path, dry_run=True)
            if isinstance(fmt_res, Err):
                return fmt_res
            format_clean = fmt_res.value.files_changed == 0

        tests_passed = 0
        tests_failed = 0
        if params.run_unit_tests:
            test_res = await self._tests.run_unit_tests(params.project_path)
            if not isinstance(test_res, Err):
                test_run: TestRun = test_res.value  # type: ignore[assignment]
                tests_passed = test_run.passed
                tests_failed = test_run.failed + test_run.errored

        overall = (
            analyzer_errors == 0
            and (format_clean or not params.require_format_clean)
            and (tests_failed == 0 or not params.run_unit_tests)
        )
        return ok(
            QualityGateReport(
                project_path=params.project_path,
                analyzer_errors=analyzer_errors,
                analyzer_warnings=analyzer_warnings,
                format_clean=format_clean,
                unit_tests_passed=tests_passed,
                unit_tests_failed=tests_failed,
                overall_ok=overall,
            )
        )

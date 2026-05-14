"""Tier-F productivity tools — compact helpers that replace repetitive ops.

Five tools, each pure-ish and small:
    scaffold_feature, run_quick_check, grep_logs, summarize_session,
    find_flutter_widget.

These exist because the agent (or Claude) was previously doing them by
chaining 3-5 lower-level tool calls. Each one is a 30-second time saver
that compounds across an iteration loop.
"""

from __future__ import annotations

import asyncio
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..entities import SessionTrace
from ..failures import FilesystemFailure, InvalidArgumentFailure
from ..repositories import (
    CodeQualityRepository,
    SessionTraceRepository,
)
from ..result import Err, Result, err, ok
from .base import BaseUseCase

# ---------------- F1: scaffold_feature -----------------------------------


@dataclass(frozen=True, slots=True)
class ScaffoldFeatureParams:
    project_path: Path
    feature_name: str   # snake_case, e.g. "auth_login"
    overwrite: bool = False


@dataclass(frozen=True, slots=True)
class ScaffoldedFiles:
    feature_dir: Path
    created: tuple[str, ...]
    skipped: tuple[str, ...]


_SCAFFOLD_TEMPLATES: dict[str, str] = {
    "domain/entities/{snake}.dart": (
        "import 'package:equatable/equatable.dart';\n\n"
        "class {Class} extends Equatable {{\n"
        "  const {Class}();\n\n"
        "  @override\n"
        "  List<Object?> get props => [];\n"
        "}}\n"
    ),
    "domain/failures/{snake}_failures.dart": (
        "import '../../core/errors/failures.dart';\n\n"
        "class {Class}Failure extends Failure {{\n"
        "  const {Class}Failure(super.message);\n"
        "}}\n"
    ),
    "domain/repositories/{snake}_repository.dart": (
        "import 'package:dartz/dartz.dart';\n"
        "import '../../core/errors/failures.dart';\n"
        "import '../entities/{snake}.dart';\n\n"
        "abstract class {Class}Repository {{\n"
        "  Future<Either<Failure, {Class}>> fetch();\n"
        "}}\n"
    ),
    "domain/usecases/get_{snake}.dart": (
        "import 'package:dartz/dartz.dart';\n"
        "import '../../core/errors/failures.dart';\n"
        "import '../entities/{snake}.dart';\n"
        "import '../repositories/{snake}_repository.dart';\n\n"
        "class Get{Class} {{\n"
        "  final {Class}Repository repository;\n"
        "  Get{Class}(this.repository);\n\n"
        "  Future<Either<Failure, {Class}>> call() => repository.fetch();\n"
        "}}\n"
    ),
    "presentation/bloc/{snake}_bloc.dart": (
        "import 'package:flutter_bloc/flutter_bloc.dart';\n"
        "import '../../domain/usecases/get_{snake}.dart';\n\n"
        "abstract class {Class}Event {{}}\n\n"
        "abstract class {Class}State {{}}\n\n"
        "class {Class}Bloc extends Bloc<{Class}Event, {Class}State> {{\n"
        "  final Get{Class} get{Class};\n"
        "  {Class}Bloc(this.get{Class}) : super(_Initial());\n"
        "}}\n\n"
        "class _Initial extends {Class}State {{}}\n"
    ),
    "presentation/pages/{snake}_page.dart": (
        "import 'package:flutter/material.dart';\n\n"
        "class {Class}Page extends StatelessWidget {{\n"
        "  const {Class}Page({{super.key}});\n\n"
        "  @override\n"
        "  Widget build(BuildContext context) {{\n"
        "    return Scaffold(appBar: AppBar(title: const Text('{Class}')));\n"
        "  }}\n"
        "}}\n"
    ),
}

_SCAFFOLD_TEST_TEMPLATES: dict[str, str] = {
    "domain/usecases/get_{snake}_test.dart": (
        "// TODO: write Get{Class} use case tests\n"
    ),
    "presentation/bloc/{snake}_bloc_test.dart": (
        "// TODO: write {Class}Bloc tests\n"
    ),
}


def _to_class(snake: str) -> str:
    return "".join(part.capitalize() for part in snake.split("_") if part)


class ScaffoldFeature(BaseUseCase[ScaffoldFeatureParams, ScaffoldedFiles]):
    async def execute(
        self, params: ScaffoldFeatureParams
    ) -> Result[ScaffoldedFiles]:
        project = Path(params.project_path).expanduser()
        if not (project / "pubspec.yaml").exists():
            return err(
                FilesystemFailure(
                    message="not a Flutter project (no pubspec.yaml)",
                    next_action="check_path",
                )
            )
        snake = params.feature_name.strip()
        if not re.fullmatch(r"[a-z][a-z0-9_]*", snake):
            return err(
                InvalidArgumentFailure(
                    message="feature_name must be snake_case",
                    next_action="fix_arguments",
                    details={
                        "corrected_example": {
                            "project_path": str(project),
                            "feature_name": "auth_login",
                        }
                    },
                )
            )
        klass = _to_class(snake)
        feature_root = project / "lib" / "features" / snake
        test_root = project / "test" / "features" / snake
        created: list[str] = []
        skipped: list[str] = []
        for tpl_path, tpl_body in _SCAFFOLD_TEMPLATES.items():
            target = feature_root / tpl_path.format(snake=snake)
            if target.exists() and not params.overwrite:
                skipped.append(str(target.relative_to(project)))
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(tpl_body.format(snake=snake, **{"Class": klass}))
            created.append(str(target.relative_to(project)))
        for tpl_path, tpl_body in _SCAFFOLD_TEST_TEMPLATES.items():
            target = test_root / tpl_path.format(snake=snake)
            if target.exists() and not params.overwrite:
                skipped.append(str(target.relative_to(project)))
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(tpl_body.format(snake=snake, **{"Class": klass}))
            created.append(str(target.relative_to(project)))
        return ok(
            ScaffoldedFiles(
                feature_dir=feature_root,
                created=tuple(created),
                skipped=tuple(skipped),
            )
        )


# ---------------- F2: run_quick_check ------------------------------------


@dataclass(frozen=True, slots=True)
class RunQuickCheckParams:
    project_path: Path


@dataclass(frozen=True, slots=True)
class QuickCheckReport:
    ok: bool
    analyzer_errors: int
    analyzer_warnings: int
    format_clean: bool
    git_dirty: bool
    summary: str


class RunQuickCheck(BaseUseCase[RunQuickCheckParams, QuickCheckReport]):
    """Composite "is the working tree healthy?" check — analyzer + format
    + git status. Skips unit tests (use quality_gate for those)."""

    def __init__(self, quality: CodeQualityRepository) -> None:
        self._quality = quality

    async def execute(
        self, params: RunQuickCheckParams
    ) -> Result[QuickCheckReport]:
        project = Path(params.project_path).expanduser()
        analyze_res = await self._quality.analyze(project)
        if isinstance(analyze_res, Err):
            return analyze_res
        report = analyze_res.value
        fmt_res = await self._quality.format(project, dry_run=True)
        if isinstance(fmt_res, Err):
            return fmt_res
        format_clean = fmt_res.value.files_changed == 0
        git_dirty = False
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "status",
                "--porcelain",
                cwd=str(project),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            out, _ = await proc.communicate()
            git_dirty = bool(out.strip())
        except FileNotFoundError:
            git_dirty = False
        ok_flag = report.errors == 0 and format_clean
        summary = (
            f"errors={report.errors} warnings={report.warnings} "
            f"format_clean={format_clean} git_dirty={git_dirty}"
        )
        return ok(
            QuickCheckReport(
                ok=ok_flag,
                analyzer_errors=report.errors,
                analyzer_warnings=report.warnings,
                format_clean=format_clean,
                git_dirty=git_dirty,
                summary=summary,
            )
        )


# ---------------- F3: grep_logs ------------------------------------------


@dataclass(frozen=True, slots=True)
class GrepLogsParams:
    path: Path
    pattern: str
    context_lines: int = 2
    max_matches: int = 50


@dataclass(frozen=True, slots=True)
class GrepMatch:
    line_no: int
    line: str
    context_before: tuple[str, ...]
    context_after: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GrepLogsResult:
    path: Path
    pattern: str
    matches: tuple[GrepMatch, ...]
    truncated: bool


class GrepLogs(BaseUseCase[GrepLogsParams, GrepLogsResult]):
    """Grep a saved log artifact for a regex with line context.

    Cheaper than calling fetch_artifact + parsing. The agent gets line
    numbers it can pass back to the user as evidence.
    """

    async def execute(self, params: GrepLogsParams) -> Result[GrepLogsResult]:
        path = Path(params.path).expanduser()
        if not path.is_file():
            return err(
                FilesystemFailure(
                    message=f"log artifact not found: {path}",
                    next_action="check_path",
                )
            )
        try:
            regex = re.compile(params.pattern)
        except re.error as exc:
            return err(
                InvalidArgumentFailure(
                    message=f"invalid regex: {exc}",
                    next_action="fix_arguments",
                )
            )
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError as exc:
            return err(
                FilesystemFailure(
                    message=f"failed to read log: {exc}",
                    next_action="check_permissions",
                )
            )
        matches: list[GrepMatch] = []
        truncated = False
        for idx, line in enumerate(lines):
            if regex.search(line):
                if len(matches) >= params.max_matches:
                    truncated = True
                    break
                start = max(0, idx - params.context_lines)
                end = min(len(lines), idx + params.context_lines + 1)
                matches.append(
                    GrepMatch(
                        line_no=idx + 1,
                        line=line,
                        context_before=tuple(lines[start:idx]),
                        context_after=tuple(lines[idx + 1:end]),
                    )
                )
        return ok(
            GrepLogsResult(
                path=path,
                pattern=params.pattern,
                matches=tuple(matches),
                truncated=truncated,
            )
        )


# ---------------- F4: summarize_session ----------------------------------


@dataclass(frozen=True, slots=True)
class SummarizeSessionParams:
    session_id: str | None = None
    top_facts: int = 5


@dataclass(frozen=True, slots=True)
class SessionElevatorPitch:
    headline: str
    facts: tuple[str, ...]
    errors: tuple[str, ...]


class SummarizeSession(
    BaseUseCase[SummarizeSessionParams, SessionElevatorPitch]
):
    """Boil a session trace down to a 3-line headline a human can scan."""

    def __init__(self, traces: SessionTraceRepository) -> None:
        self._traces = traces

    async def execute(
        self, params: SummarizeSessionParams
    ) -> Result[SessionElevatorPitch]:
        res = await self._traces.summary(params.session_id)
        if isinstance(res, Err):
            return res
        trace: SessionTrace = res.value
        entries = trace.entries
        total = len(entries)
        ok_count = sum(1 for e in entries if e.ok)
        err_count = total - ok_count
        headline = (
            f"session {trace.session_id}: {total} calls, "
            f"{ok_count}✓ / {err_count}✗"
        )
        # Facts: most recent ok-true tools at phase boundaries.
        recent_ok = [
            f"#{e.sequence} {e.tool_name} → {e.summary}"
            for e in reversed(entries)
            if e.ok
        ][: params.top_facts]
        # Errors: most recent failures with their codes.
        recent_err = [
            f"#{e.sequence} {e.tool_name}: {e.error_code or 'error'} — {e.summary}"
            for e in reversed(entries)
            if not e.ok
        ][:3]
        return ok(
            SessionElevatorPitch(
                headline=headline,
                facts=tuple(reversed(recent_ok)),
                errors=tuple(reversed(recent_err)),
            )
        )


# ---------------- F5: find_flutter_widget --------------------------------


@dataclass(frozen=True, slots=True)
class FindFlutterWidgetParams:
    project_path: Path
    name_pattern: str   # regex on the class name
    max_results: int = 50


@dataclass(frozen=True, slots=True)
class WidgetMatch:
    name: str
    path: str
    line_no: int


@dataclass(frozen=True, slots=True)
class FindFlutterWidgetResult:
    matches: tuple[WidgetMatch, ...]
    truncated: bool


_WIDGET_DECL_RE = re.compile(
    r"^\s*class\s+([A-Z][A-Za-z0-9_]*)\s+extends\s+(StatelessWidget|StatefulWidget|ConsumerWidget|ConsumerStatefulWidget)"
)


class FindFlutterWidget(
    BaseUseCase[FindFlutterWidgetParams, FindFlutterWidgetResult]
):
    """Scan `lib/` for widget classes whose name matches a regex.

    Faster than asking an agent to Glob+Grep+Read manually for the most
    common Flutter discovery query.
    """

    async def execute(
        self, params: FindFlutterWidgetParams
    ) -> Result[FindFlutterWidgetResult]:
        project = Path(params.project_path).expanduser()
        lib = project / "lib"
        if not lib.is_dir():
            return err(
                FilesystemFailure(
                    message="lib/ not found in project",
                    next_action="check_path",
                )
            )
        try:
            name_re = re.compile(params.name_pattern)
        except re.error as exc:
            return err(
                InvalidArgumentFailure(
                    message=f"invalid regex: {exc}",
                    next_action="fix_arguments",
                )
            )
        matches: list[WidgetMatch] = []
        truncated = False
        for dart_file in sorted(lib.rglob("*.dart")):
            try:
                lines = dart_file.read_text(errors="replace").splitlines()
            except OSError:
                continue
            for idx, line in enumerate(lines):
                m = _WIDGET_DECL_RE.match(line)
                if m and name_re.search(m.group(1)):
                    matches.append(
                        WidgetMatch(
                            name=m.group(1),
                            path=str(dart_file.relative_to(project)),
                            line_no=idx + 1,
                        )
                    )
                    if len(matches) >= params.max_results:
                        truncated = True
                        break
            if truncated:
                break
        return ok(
            FindFlutterWidgetResult(
                matches=tuple(matches),
                truncated=truncated,
            )
        )

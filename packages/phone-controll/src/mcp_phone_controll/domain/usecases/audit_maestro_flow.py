"""Maestro flow audit — senior-tester discipline applied to
Maestro YAML flows.

Maestro (mobile.dev) is a flow-based cross-platform mobile UI
testing framework. Its MCP server (launched Feb 2026) lets
agents author YAML flows in natural language and execute them
against devices. **It doesn't ship audit / linting tooling.**

This use case audits Maestro flow YAML against the same senior-
tester discipline encoded in `audit_test_quality` for Dart
tests — translated for YAML idioms.

What this catches (12 rules across 4 tiers):

  **JUNIOR — syntactic / immediate smells (4 rules)**
    • hardcoded_locale_string  — `tapOn: "Sign in"` literal
                                  that breaks on non-default
                                  locales (the Polish-phone
                                  lesson, now in YAML form)
    • vacuous_assertion        — `assertVisible: ".*"` regex
                                  wildcard always matches
    • sleep_in_flow            — `- wait: 3000` real-time wait
                                  instead of
                                  `waitForAnimationToEnd`
    • no_assertions            — flow has steps but zero
                                  `assertVisible` / `assertNotVisible`
                                  / `assertTrue` directives

  **MID — flow hygiene (3 rules)**
    • no_appId                 — flow doesn't declare `appId`
                                  in the front-matter block
    • no_tags                  — no `tags:` list (CI can't
                                  selectively run smoke vs full)
    • inline_script_too_long   — `evalScript` block > 30 lines
                                  (move to a separate .js file)

  **SENIOR — coverage discipline (3 rules)**
    • missing_failure_path     — flow tests a happy path with
                                  no paired negative variant
                                  (e.g. login_flow.yaml without
                                  login_fail_flow.yaml beside it)
    • untagged_when_many       — directory has 5+ flows but
                                  no tagging convention applied
    • no_test_data_factory_dir — directory has 10+ flows but
                                  no test-data fixtures
                                  (env/, fixtures/) directory

  **STAFF — architecture (2 rules)**
    • nested_runFlow_deep      — `runFlow` chain > 4 levels
                                  (refactor candidates exist)
    • hardcoded_credentials_in_env — `inputText: "user@..."`
                                  with a literal email instead
                                  of `${USERNAME}`

What this is NOT:

  • Not a Maestro executor — we don't run flows. We audit them.
    Use Maestro's own `run` tool for execution.
  • Not a YAML validator — Maestro itself does that. We assume
    the flow parses; we audit its quality.
  • Not project-agnostic — encodes the senior-tester
    discipline. Teams using Maestro differently would tune.

Hand-parses Maestro YAML (no PyYAML dependency) — the structure
is regular enough that regex over text is sufficient and keeps
us dependency-free.

Citations:

  Maestro docs: https://docs.maestro.dev
  Senior-tester discipline: docs/senior-tester-discipline.md
  audit_test_quality (Dart sister tool): phase 12
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..failures import FilesystemFailure
from ..result import Result, err, ok
from ._helpers import is_path_excluded
from .base import BaseUseCase


class Severity(str, Enum):
    BLOCKER = "blocker"   # demonstrably broken / never run
    SERIOUS = "serious"   # silent quality smell
    MINOR = "minor"       # cleanup


class FlowQualityLevel(str, Enum):
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"


@dataclass(frozen=True, slots=True)
class MaestroFlowFinding:
    rule: str
    description: str
    severity: Severity
    level: FlowQualityLevel
    file: str
    line: int                # 1-indexed; 0 if file-level
    snippet: str
    fix_hint: str | None
    standard: str | None     # citation


@dataclass(frozen=True, slots=True)
class AuditMaestroFlowParams:
    project_path: Path
    paths: tuple[str, ...] = ()       # default = .maestro/ + maestro/ + tests/
    min_level: str = "junior"
    max_findings: int = 200


@dataclass(frozen=True, slots=True)
class AuditMaestroFlowResult:
    grade: str                                  # excellent / acceptable / fragile / unreliable
    score: float                                # weighted findings per flow
    flows_total: int
    flows_with_appId: int
    flows_with_tags: int
    flows_with_assertions: int
    findings: tuple[MaestroFlowFinding, ...]
    findings_by_level: dict[str, int]
    findings_by_severity: dict[str, int]
    top_actions: tuple[str, ...]
    advice: str


_SEVERITY_WEIGHT = {
    Severity.BLOCKER: 10,
    Severity.SERIOUS: 4,
    Severity.MINOR: 1,
}


class AuditMaestroFlow(
    BaseUseCase[AuditMaestroFlowParams, AuditMaestroFlowResult]
):
    """Audits Maestro YAML flows with senior-tester discipline.

    Pure compute. No PyYAML dependency. Regex over text.
    The composition play: Maestro's MCP authors + executes
    flows; we audit them.
    """

    async def execute(
        self, params: AuditMaestroFlowParams
    ) -> Result[AuditMaestroFlowResult]:
        if not params.project_path.is_dir():
            return err(FilesystemFailure(
                message=f"project_path not found: {params.project_path}",
                next_action="fix_arguments",
            ))
        try:
            min_level = FlowQualityLevel(params.min_level)
        except ValueError:
            return err(FilesystemFailure(
                message=(
                    f"unknown min_level {params.min_level!r}. "
                    "Valid: junior, mid, senior, staff"
                ),
                next_action="fix_arguments",
            ))

        roots = _resolve_roots(params.project_path, params.paths)
        flows = _collect_flow_files(roots, params.project_path)
        if not flows:
            # No Maestro flows found — return a graceful empty result
            return ok(_empty_result())

        all_findings: list[MaestroFlowFinding] = []
        n_appId = 0
        n_tags = 0
        n_with_assertions = 0
        flow_names: set[str] = set()
        flows_by_dir: dict[Path, list[Path]] = {}

        for f in flows:
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = str(f.relative_to(params.project_path))
            findings, has_appId, has_tags, has_assertions = _scan_flow(
                rel, content,
            )
            all_findings.extend(findings)
            if has_appId:
                n_appId += 1
            if has_tags:
                n_tags += 1
            if has_assertions:
                n_with_assertions += 1
            flow_names.add(f.stem)
            flows_by_dir.setdefault(f.parent, []).append(f)

        # Per-directory architectural rules
        all_findings.extend(
            _check_directory_architecture(
                flows_by_dir, flow_names, params.project_path,
            )
        )

        # Filter by min_level
        order = [
            FlowQualityLevel.JUNIOR, FlowQualityLevel.MID,
            FlowQualityLevel.SENIOR, FlowQualityLevel.STAFF,
        ]
        kept = set(order[order.index(min_level):])
        all_findings = [f for f in all_findings if f.level in kept]

        sev_idx = {
            Severity.BLOCKER: 0, Severity.SERIOUS: 1, Severity.MINOR: 2,
        }
        all_findings.sort(
            key=lambda x: (sev_idx[x.severity], x.file, x.line)
        )
        all_findings_t = tuple(all_findings[: params.max_findings])

        by_level: dict[str, int] = {}
        by_sev: dict[str, int] = {}
        for fnd in all_findings_t:
            by_level[fnd.level.value] = by_level.get(fnd.level.value, 0) + 1
            by_sev[fnd.severity.value] = by_sev.get(fnd.severity.value, 0) + 1

        weighted = sum(_SEVERITY_WEIGHT[f.severity] for f in all_findings_t)
        n_flows = max(len(flows), 1)
        score = weighted / n_flows
        grade = _grade_for(score, by_sev, len(flows))

        return ok(AuditMaestroFlowResult(
            grade=grade,
            score=round(score, 2),
            flows_total=len(flows),
            flows_with_appId=n_appId,
            flows_with_tags=n_tags,
            flows_with_assertions=n_with_assertions,
            findings=all_findings_t,
            findings_by_level=by_level,
            findings_by_severity=by_sev,
            top_actions=_build_top_actions(all_findings_t),
            advice=_build_advice(
                grade, score, len(flows), n_with_assertions,
                len(all_findings_t),
            ),
        ))


# ============================================================
# Flow discovery
# ============================================================


def _resolve_roots(project: Path, paths: tuple[str, ...]) -> list[Path]:
    if paths:
        return [project / p for p in paths if (project / p).exists()]
    # Default locations Maestro projects use
    out: list[Path] = []
    for d in (".maestro", "maestro", "tests/maestro", "test/maestro"):
        candidate = project / d
        if candidate.is_dir():
            out.append(candidate)
    return out


def _collect_flow_files(
    roots: list[Path], project_root: Path,
) -> list[Path]:
    """Maestro flows are .yaml / .yml under a Maestro directory.
    A flow is recognised by presence of `appId:` OR a top-level
    list of `- tapOn:` / `- launchApp` directives. We do a quick
    content sniff to avoid auditing unrelated YAML."""
    out: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        if root.is_file() and root.suffix in (".yaml", ".yml"):
            out.append(root)
            continue
        for f in list(root.rglob("*.yaml")) + list(root.rglob("*.yml")):
            if is_path_excluded(f, project_root):
                continue
            if _looks_like_maestro_flow(f):
                out.append(f)
    return sorted(set(out))


def _looks_like_maestro_flow(path: Path) -> bool:
    """Sniff first 1KB for Maestro markers."""
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:1024]
    except OSError:
        return False
    return bool(
        _RE_APP_ID.search(head)
        or _RE_LAUNCH_APP.search(head)
        or _RE_TAP_ON.search(head)
        or _RE_ASSERT_VISIBLE.search(head)
    )


# ============================================================
# Compiled regex patterns
# ============================================================


# Frontmatter / metadata
_RE_APP_ID = re.compile(r"^appId\s*:\s*(\S+)", re.MULTILINE)
_RE_TAGS = re.compile(r"^tags\s*:\s*\[?", re.MULTILINE)

# Flow steps
_RE_LAUNCH_APP = re.compile(r"^-\s+launchApp\b", re.MULTILINE)
_RE_TAP_ON_LITERAL = re.compile(
    r'^-\s+tapOn\s*:\s*["\']([A-Z][A-Za-z0-9 ?!.,]+)["\']',
    re.MULTILINE,
)
_RE_TAP_ON = re.compile(r"^-\s+tapOn\b", re.MULTILINE)
_RE_INPUT_TEXT_LITERAL = re.compile(
    r'^-\s+inputText\s*:\s*["\']([^"\']+)["\']',
    re.MULTILINE,
)
_RE_ASSERT_VISIBLE = re.compile(
    r'^-\s+assertVisible\s*:\s*["\']?([^"\'\n]+)["\']?',
    re.MULTILINE,
)
_RE_ASSERT_NOT_VISIBLE = re.compile(
    r"^-\s+assertNotVisible\b", re.MULTILINE,
)
_RE_ASSERT_TRUE = re.compile(r"^-\s+assertTrue\b", re.MULTILINE)
_RE_WAIT_MS = re.compile(r"^-\s+wait\s*:\s*(\d+)", re.MULTILINE)
_RE_EVAL_SCRIPT = re.compile(
    r"^-\s+evalScript\s*:\s*\|\s*\n((?:\s+.+\n)+)",
    re.MULTILINE,
)
_RE_RUN_FLOW = re.compile(r"^\s*-\s+runFlow\b", re.MULTILINE)
_RE_VACUOUS_REGEX = re.compile(r'["\']\s*\.\*\s*["\']')
_RE_EMAIL_LITERAL = re.compile(
    r"^-\s+inputText\s*:\s*['\"]([^@'\"]+@[^'\"]+)['\"]",
    re.MULTILINE,
)
_RE_ENV_VAR = re.compile(r"\$\{[A-Z_]+\}")


# ============================================================
# Per-flow scanner
# ============================================================


def _scan_flow(
    rel: str, content: str,
) -> tuple[list[MaestroFlowFinding], bool, bool, bool]:
    """Returns (findings, has_appId, has_tags, has_assertions)."""
    findings: list[MaestroFlowFinding] = []
    has_appId = bool(_RE_APP_ID.search(content))
    has_tags = bool(_RE_TAGS.search(content))
    has_assertions = bool(
        _RE_ASSERT_VISIBLE.search(content)
        or _RE_ASSERT_NOT_VISIBLE.search(content)
        or _RE_ASSERT_TRUE.search(content)
    )
    has_steps = bool(
        _RE_TAP_ON.search(content)
        or _RE_LAUNCH_APP.search(content)
        or _RE_INPUT_TEXT_LITERAL.search(content)
    )

    # ---- Mid: no_appId ----
    if not has_appId and has_steps:
        findings.append(_mk(
            "no_appId",
            "Maestro flow has steps but no `appId:` declaration. "
            "The flow can't be routed to a specific app on a "
            "multi-app device.",
            Severity.SERIOUS, FlowQualityLevel.MID,
            rel, 0, "missing appId",
            "Add `appId: com.example.app` at the top of the YAML.",
            "Maestro docs: app-scoped flows",
        ))

    # ---- Mid: no_tags ----
    if not has_tags and has_steps:
        findings.append(_mk(
            "no_tags",
            "Maestro flow has no `tags:`. CI can't selectively "
            "run smoke vs full subsets.",
            Severity.MINOR, FlowQualityLevel.MID,
            rel, 0, "missing tags",
            "Add `tags:` block, e.g. `tags: [smoke, auth]`.",
            "Maestro docs: tag-based selection",
        ))

    # ---- Junior: no_assertions ----
    if has_steps and not has_assertions:
        findings.append(_mk(
            "no_assertions",
            "Flow has steps but zero assertions. It clicks "
            "through the UI without verifying anything.",
            Severity.SERIOUS, FlowQualityLevel.JUNIOR,
            rel, 0, "no assertVisible / assertTrue",
            "Add at least one `- assertVisible: <text-or-id>` "
            "per logical step.",
            "Senior-tester discipline: atomic assertion",
        ))

    # ---- Junior: hardcoded_locale_string (literal in tapOn) ----
    for m in _RE_TAP_ON_LITERAL.finditer(content):
        value = m.group(1)
        # Skip if it looks like an ID (snake_case, all lowercase, no space)
        if re.fullmatch(r"[a-z][a-z0-9_]*", value):
            continue
        line_no = content[: m.start()].count("\n") + 1
        findings.append(_mk(
            "hardcoded_locale_string",
            f"`tapOn: {value!r}` hardcodes the English label. "
            "Breaks on non-default locales (Polish-phone lesson).",
            Severity.MINOR, FlowQualityLevel.JUNIOR,
            rel, line_no, m.group(0).strip()[:140],
            "Use `tapOn: { id: <resource_id> }` or "
            "`tapOn: { textBy: <semantic_label> }`.",
            "i18n discipline applied to flow YAML",
        ))

    # ---- Junior: vacuous_assertion ----
    for m in _RE_ASSERT_VISIBLE.finditer(content):
        match_text = m.group(1).strip()
        if _RE_VACUOUS_REGEX.search(m.group(0)) or match_text in (".*", ".+"):
            line_no = content[: m.start()].count("\n") + 1
            findings.append(_mk(
                "vacuous_assertion",
                "Wildcard `.*` / `.+` assertVisible matches any text. "
                "Test always passes.",
                Severity.SERIOUS, FlowQualityLevel.JUNIOR,
                rel, line_no, m.group(0).strip()[:140],
                "Replace with the actual expected text or id.",
                "Senior-tester discipline #2: meaningful assertions",
            ))

    # ---- Junior: sleep_in_flow ----
    for m in _RE_WAIT_MS.finditer(content):
        ms = int(m.group(1))
        if ms >= 500:  # under 500ms is sometimes legit (animation gate)
            line_no = content[: m.start()].count("\n") + 1
            findings.append(_mk(
                "sleep_in_flow",
                f"`wait: {ms}` is a real-time sleep. Slow + flaky.",
                Severity.SERIOUS, FlowQualityLevel.JUNIOR,
                rel, line_no, m.group(0).strip()[:140],
                "Replace with `waitForAnimationToEnd` or assert "
                "on the next visible element.",
                "flutter_test analog: no real sleeps in tests",
            ))

    # ---- Mid: inline_script_too_long ----
    for m in _RE_EVAL_SCRIPT.finditer(content):
        script_body = m.group(1)
        lines_in_script = len([
            ln for ln in script_body.splitlines() if ln.strip()
        ])
        if lines_in_script > 30:
            line_no = content[: m.start()].count("\n") + 1
            findings.append(_mk(
                "inline_script_too_long",
                f"`evalScript` block is {lines_in_script} lines. "
                "Hard to test + review.",
                Severity.MINOR, FlowQualityLevel.MID,
                rel, line_no,
                f"{lines_in_script}-line evalScript",
                "Move to a separate .js file and reference it.",
                "Maestro docs: external scripts",
            ))

    # ---- Staff: nested_runFlow_deep (count consecutive runFlow refs) ----
    run_flow_count = len(_RE_RUN_FLOW.findall(content))
    if run_flow_count > 4:
        first = _RE_RUN_FLOW.search(content)
        assert first is not None
        line_no = content[: first.start()].count("\n") + 1
        findings.append(_mk(
            "nested_runFlow_deep",
            f"Flow references `runFlow` {run_flow_count} times. "
            "Stack of nested flows is hard to debug when one fails.",
            Severity.MINOR, FlowQualityLevel.STAFF,
            rel, line_no, f"{run_flow_count} runFlow references",
            "Flatten or extract into a single composite flow with "
            "shared setup.",
            "Test architecture: keep call depth shallow",
        ))

    # ---- Staff: hardcoded_credentials_in_env ----
    for m in _RE_EMAIL_LITERAL.finditer(content):
        line_no = content[: m.start()].count("\n") + 1
        if not _RE_ENV_VAR.search(m.group(0)):
            findings.append(_mk(
                "hardcoded_credentials_in_env",
                f"`inputText` with literal email {m.group(1)!r}. "
                "Use ${USERNAME} so the flow runs against any env.",
                Severity.MINOR, FlowQualityLevel.STAFF,
                rel, line_no, m.group(0).strip()[:140],
                "Replace with `inputText: ${USERNAME}` and supply "
                "via env when running.",
                "Maestro docs: env vars + parameterised flows",
            ))

    return findings, has_appId, has_tags, has_assertions


# ============================================================
# Directory-level rules
# ============================================================


def _check_directory_architecture(
    flows_by_dir: dict[Path, list[Path]],
    flow_names: set[str],
    project_root: Path,
) -> list[MaestroFlowFinding]:
    findings: list[MaestroFlowFinding] = []

    for dir_path, flows_in_dir in flows_by_dir.items():
        if len(flows_in_dir) < 5:
            continue
        rel_dir = str(dir_path.relative_to(project_root))

        # Senior: untagged_when_many — many flows but none tagged
        tag_count = sum(
            1 for f in flows_in_dir
            if _RE_TAGS.search(
                f.read_text(encoding="utf-8", errors="replace")[:1024]
                if f.is_file() else ""
            )
        )
        if tag_count == 0:
            findings.append(_mk(
                "untagged_when_many",
                f"{len(flows_in_dir)} flows in `{rel_dir}/` and "
                "none use `tags:`. CI can't run subsets.",
                Severity.MINOR, FlowQualityLevel.SENIOR,
                f"{rel_dir}/", 0,
                f"{len(flows_in_dir)} untagged flows",
                "Add `tags:` to at least 2 categories (smoke, "
                "full, regression).",
                "Maestro docs: tag-based selection",
            ))

        # Senior: missing_failure_path — happy flows w/o paired fail
        if len(flows_in_dir) >= 5:
            happy_stems = [
                f.stem for f in flows_in_dir
                if not any(neg in f.stem.lower() for neg in (
                    "fail", "invalid", "error", "negative", "denied",
                ))
            ]
            fail_stems = {
                f.stem.lower() for f in flows_in_dir
                if any(neg in f.stem.lower() for neg in (
                    "fail", "invalid", "error", "negative", "denied",
                ))
            }
            if happy_stems and not fail_stems:
                findings.append(_mk(
                    "missing_failure_path",
                    f"{len(happy_stems)} happy-path flows in "
                    f"`{rel_dir}/` with zero negative-path "
                    "counterparts.",
                    Severity.SERIOUS, FlowQualityLevel.SENIOR,
                    f"{rel_dir}/", 0,
                    f"{len(happy_stems)} happy / 0 negative",
                    "Add paired `<flow>_fail.yaml` for each "
                    "happy flow asserting the failure mode.",
                    "Senior-tester discipline #7: paired failure path",
                ))

        # Staff: no_test_data_factory_dir
        if len(flows_in_dir) >= 10:
            has_fixtures = any(
                (dir_path / d).is_dir()
                for d in ("env", "fixtures", "data", "helpers")
            )
            if not has_fixtures:
                findings.append(_mk(
                    "no_test_data_factory_dir",
                    f"{len(flows_in_dir)} flows in `{rel_dir}/` "
                    "and no `env/`, `fixtures/`, `data/`, or "
                    "`helpers/` subdirectory.",
                    Severity.MINOR, FlowQualityLevel.STAFF,
                    f"{rel_dir}/", 0,
                    f"{len(flows_in_dir)} flows; no fixtures dir",
                    "Create `env/` for env-var sets or "
                    "`fixtures/` for shared YAML snippets.",
                    "Test data factory discipline applied to YAML",
                ))

    return findings


# ============================================================
# Empty result + grading + advice
# ============================================================


def _empty_result() -> AuditMaestroFlowResult:
    return AuditMaestroFlowResult(
        grade="not_using_maestro",
        score=0.0,
        flows_total=0,
        flows_with_appId=0,
        flows_with_tags=0,
        flows_with_assertions=0,
        findings=(),
        findings_by_level={},
        findings_by_severity={},
        top_actions=(
            "No Maestro flows found. Looked under .maestro/, "
            "maestro/, tests/maestro/, test/maestro/.",
        ),
        advice=(
            "Project doesn't use Maestro (no flow files found). "
            "If you want to add Maestro to this project, follow "
            "docs.maestro.dev/get-started — then re-run this audit."
        ),
    )


def _grade_for(
    score: float, by_sev: dict[str, int], flows: int,
) -> str:
    if flows == 0:
        return "not_using_maestro"
    if by_sev.get("blocker", 0) > 0:
        return "unreliable"
    if score >= 10 or by_sev.get("serious", 0) >= 5:
        return "fragile"
    if score >= 3 or by_sev.get("serious", 0) > 0:
        return "acceptable"
    return "excellent"


def _mk(
    rule: str, desc: str, severity: Severity, level: FlowQualityLevel,
    file: str, line: int, snippet: str,
    fix_hint: str | None, standard: str | None,
) -> MaestroFlowFinding:
    return MaestroFlowFinding(
        rule=rule, description=desc, severity=severity, level=level,
        file=file, line=line, snippet=snippet[:140],
        fix_hint=fix_hint, standard=standard,
    )


def _build_top_actions(
    findings: tuple[MaestroFlowFinding, ...],
) -> tuple[str, ...]:
    if not findings:
        return ("Maestro flows pass the senior-tester discipline.",)
    counts: dict[str, tuple[int, MaestroFlowFinding]] = {}
    for f in findings:
        prev = counts.get(f.rule)
        if prev is None or _SEVERITY_WEIGHT[f.severity] > _SEVERITY_WEIGHT[prev[1].severity]:
            counts[f.rule] = ((prev[0] if prev else 0) + 1, f)
        else:
            counts[f.rule] = (prev[0] + 1, prev[1])
    ranked = sorted(
        counts.items(),
        key=lambda kv: (
            -_SEVERITY_WEIGHT[kv[1][1].severity],
            -kv[1][0],
        ),
    )
    out: list[str] = []
    for rule, (n, sample) in ranked[:5]:
        hint = sample.fix_hint or "see rule definition"
        out.append(f"[{sample.severity.value}] {rule} ×{n} — {hint}")
    return tuple(out)


def _build_advice(
    grade: str, score: float, n_flows: int,
    n_with_assertions: int, n_findings: int,
) -> str:
    return (
        f"Maestro flow grade: {grade} ({score:.1f} weighted "
        f"findings/flow). {n_flows} flows, "
        f"{n_with_assertions} with assertions. "
        f"{n_findings} findings to address."
    )

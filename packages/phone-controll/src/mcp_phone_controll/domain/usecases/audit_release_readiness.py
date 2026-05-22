"""Release-readiness audit — the composite gate.

Composes the five v0.3.0 audit verticals into a single
ship / hold / block verdict. Designed to paste into a release
PR comment.

  audit_code_seniority   →  architecture          (phase 7)
  audit_security         →  OWASP MASVS           (phase 8)
  audit_localization     →  i18n hygiene          (phase 9)
  audit_dependencies     →  supply chain          (phase 10)
  + accessibility / app_size optionally           (existing)

What this does
--------------
Runs the configured domains concurrently via asyncio.gather,
maps each domain's grade to a 0-100 score, applies weights,
computes a composite letter grade (A–F) + verdict (ship /
hold / block), and produces a unified top_actions list
sorted across all domains by severity-weight.

What this is NOT
----------------
  • Not a build runner. We don't call `flutter build`; if you
    want size analysis included, build the APK/IPA first and
    pass the path.
  • Not a UI driver. Accessibility audit needs a running app
    on a device, so it's opt-in (run it manually if needed
    and pass the result via `include_accessibility=False`
    when running offline).
  • Not opinionated about weights — defaults are sane but
    you can override per-team.

Design notes
------------
  • Pure compute by default. Runs in sub-second on any pubspec.
  • Domains run concurrently. The slowest single audit (usually
    seniority on a large lib/) gates total runtime.
  • Per-domain failure is caught and recorded as a domain-level
    error — one failed audit doesn't kill the whole report.
  • Verdict is a hard-cutoff function on blocker counts; below
    the cutoff, score+weights drive the letter grade.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..failures import FilesystemFailure
from ..result import Err, Ok, Result, err, ok
from .audit_code_seniority import (
    AuditCodeSeniority,
    AuditCodeSeniorityParams,
)
from .audit_dependencies import (
    AuditDependencies,
    AuditDependenciesParams,
)
from .audit_localization import (
    AuditLocalization,
    AuditLocalizationParams,
)
from .audit_security import (
    AuditSecurity,
    AuditSecurityParams,
)
from .audit_test_quality import (
    AuditTestQuality,
    AuditTestQualityParams,
)
from .base import BaseUseCase


class Verdict(str, Enum):
    SHIP = "ship"       # no blockers, composite >= 80
    HOLD = "hold"       # no blockers but composite < 80
    BLOCK = "block"     # any blocker / any critical


@dataclass(frozen=True, slots=True)
class DomainResult:
    domain: str                  # 'seniority' / 'security' / etc.
    ran: bool                    # False if skipped/errored
    grade: str | None            # the domain's own grade
    score: float                 # normalized 0-100 (higher is better)
    findings_count: int
    blockers_count: int          # critical / blocker severity
    error: str | None            # populated if the audit failed
    advice: str | None           # the domain's own advice line


@dataclass(frozen=True, slots=True)
class AuditReleaseReadinessParams:
    project_path: Path
    # Min level to apply across all sub-audits.
    min_level: str = "junior"
    # Run individual domains or skip. All True by default except
    # device-touching audits (accessibility) which are opt-in.
    include_seniority: bool = True
    include_security: bool = True
    include_localization: bool = True
    include_dependencies: bool = True
    include_test_quality: bool = True
    # Whether your app ships to production (passed to
    # audit_dependencies' is_published toggle).
    is_published: bool = True
    # Per-domain weights for composite score. Must sum > 0.
    # Defaults weight security highest, then dependencies, then
    # test_quality, then seniority, then localization.
    weight_seniority: float = 1.0
    weight_security: float = 2.0
    weight_localization: float = 1.0
    weight_dependencies: float = 1.5
    weight_test_quality: float = 1.5
    # Cap on findings preserved in `top_actions`.
    max_top_actions: int = 10


@dataclass(frozen=True, slots=True)
class AuditReleaseReadinessResult:
    verdict: str                          # ship / hold / block
    composite_grade: str                  # A / B / C / D / F
    composite_score: float                # 0-100
    domains: tuple[DomainResult, ...]     # per-domain breakdown
    total_findings: int
    total_blockers: int
    top_actions: tuple[str, ...]          # cross-domain prioritized
    advice: str                           # release-PR-ready summary
    ran_in_s: float                       # wall-clock seconds


# ============================================================
# Grade → score mapping (per-domain → normalized 0-100)
# ============================================================
# Higher is better. Each domain reports a string grade; we map
# it here so the composite arithmetic is uniform.

_SENIORITY_GRADE_SCORES = {
    "staff": 100, "senior": 85, "mid": 65, "junior": 40,
    "needs_review": 0,
}
_SECURITY_GRADE_SCORES = {
    "secure": 100, "acceptable": 75, "at_risk": 40, "critical": 0,
}
_LOCALIZATION_GRADE_SCORES = {
    "well_localized": 100, "acceptable": 75,
    "single_locale": 50, "missing_l10n": 20,
}
_DEPENDENCIES_GRADE_SCORES = {
    "clean": 100, "acceptable": 75, "at_risk": 40, "blocked": 0,
}
_TEST_QUALITY_GRADE_SCORES = {
    "excellent": 100, "acceptable": 75, "fragile": 40,
    "unreliable": 0,
}


class AuditReleaseReadiness(
    BaseUseCase[AuditReleaseReadinessParams, AuditReleaseReadinessResult]
):
    """Composes all v0.3.0 audit verticals into one ship/hold/block verdict.

    Pure compute. Concurrent. No device, no network. The output
    is designed to paste into a release PR comment.
    """

    async def execute(
        self, params: AuditReleaseReadinessParams
    ) -> Result[AuditReleaseReadinessResult]:
        if not params.project_path.is_dir():
            return err(
                FilesystemFailure(
                    message=f"project_path not found: {params.project_path}",
                    next_action="fix_arguments",
                )
            )

        start = time.monotonic()

        # Build the per-domain task list
        domain_tasks: list[tuple[str, asyncio.Task]] = []
        weights: dict[str, float] = {}

        if params.include_seniority:
            domain_tasks.append((
                "seniority",
                asyncio.create_task(
                    AuditCodeSeniority()(
                        AuditCodeSeniorityParams(
                            project_path=params.project_path,
                            min_level=params.min_level,
                        )
                    )
                ),
            ))
            weights["seniority"] = params.weight_seniority

        if params.include_security:
            min_sev_for_security = _security_min_severity(params.min_level)
            domain_tasks.append((
                "security",
                asyncio.create_task(
                    AuditSecurity()(
                        AuditSecurityParams(
                            project_path=params.project_path,
                            min_severity=min_sev_for_security,
                        )
                    )
                ),
            ))
            weights["security"] = params.weight_security

        if params.include_localization:
            domain_tasks.append((
                "localization",
                asyncio.create_task(
                    AuditLocalization()(
                        AuditLocalizationParams(
                            project_path=params.project_path,
                            min_level=params.min_level,
                        )
                    )
                ),
            ))
            weights["localization"] = params.weight_localization

        if params.include_dependencies:
            domain_tasks.append((
                "dependencies",
                asyncio.create_task(
                    AuditDependencies()(
                        AuditDependenciesParams(
                            project_path=params.project_path,
                            min_level=params.min_level,
                            is_published=params.is_published,
                        )
                    )
                ),
            ))
            weights["dependencies"] = params.weight_dependencies

        if params.include_test_quality:
            domain_tasks.append((
                "test_quality",
                asyncio.create_task(
                    AuditTestQuality()(
                        AuditTestQualityParams(
                            project_path=params.project_path,
                            min_level=params.min_level,
                        )
                    )
                ),
            ))
            weights["test_quality"] = params.weight_test_quality

        if not domain_tasks:
            return err(
                FilesystemFailure(
                    message=(
                        "At least one audit domain must be enabled. "
                        "All include_* flags were False."
                    ),
                    next_action="fix_arguments",
                )
            )

        # Wait for all to complete
        completed = await asyncio.gather(
            *(t for _, t in domain_tasks),
            return_exceptions=True,
        )

        # Aggregate
        domain_results: list[DomainResult] = []
        cross_findings: list[tuple[int, str, str]] = []  # (weight, severity, action)
        total_blockers = 0
        total_findings = 0

        for (name, _), audit_res in zip(
            domain_tasks, completed, strict=True,
        ):
            domain_result, n_findings, n_blockers, actions = _reduce(
                name, audit_res,
            )
            domain_results.append(domain_result)
            total_findings += n_findings
            total_blockers += n_blockers
            cross_findings.extend(actions)

        ran_in_s = round(time.monotonic() - start, 3)

        # Compute composite score (weighted average over included domains)
        weighted_sum = 0.0
        weight_sum = 0.0
        for dr in domain_results:
            if not dr.ran:
                continue
            w = weights.get(dr.domain, 1.0)
            weighted_sum += dr.score * w
            weight_sum += w
        composite_score = (
            weighted_sum / weight_sum if weight_sum > 0 else 0.0
        )

        # Verdict + letter grade
        verdict = _verdict_for(total_blockers, composite_score)
        composite_grade = _letter_grade(composite_score)

        # Cross-domain top_actions (sorted by severity weight, dedup)
        cross_findings.sort(key=lambda x: -x[0])
        top_actions = tuple(
            action for _, _, action in cross_findings[: params.max_top_actions]
        )
        if not top_actions:
            top_actions = (
                "No release-blocking findings. Ship-ready.",
            )

        return ok(AuditReleaseReadinessResult(
            verdict=verdict.value,
            composite_grade=composite_grade,
            composite_score=round(composite_score, 1),
            domains=tuple(domain_results),
            total_findings=total_findings,
            total_blockers=total_blockers,
            top_actions=top_actions,
            advice=_build_advice(
                verdict, composite_grade, composite_score,
                total_findings, total_blockers, domain_results, ran_in_s,
            ),
            ran_in_s=ran_in_s,
        ))


# ============================================================
# Per-domain reducer
# ============================================================


def _reduce(
    domain: str,
    audit_res,
) -> tuple[DomainResult, int, int, list[tuple[int, str, str]]]:
    """Reduce a single audit result into a DomainResult + extracted
    cross-domain top_actions. Returns (DomainResult, n_findings,
    n_blockers, cross_actions)."""
    # Exception during the audit?
    if isinstance(audit_res, Exception):
        return (
            DomainResult(
                domain=domain, ran=False, grade=None,
                score=0.0, findings_count=0, blockers_count=0,
                error=f"{type(audit_res).__name__}: {audit_res}",
                advice=None,
            ),
            0, 0, [],
        )
    # Use-case-level Err?
    if isinstance(audit_res, Err):
        return (
            DomainResult(
                domain=domain, ran=False, grade=None,
                score=0.0, findings_count=0, blockers_count=0,
                error=audit_res.failure.message,
                advice=None,
            ),
            0, 0, [],
        )
    # Ok
    assert isinstance(audit_res, Ok)
    value = audit_res.value
    grade = getattr(value, "grade", None)
    score = _score_for_domain(domain, grade)
    findings = getattr(value, "findings", ())
    findings_count = len(findings)
    blockers_count = _count_blockers(domain, findings)
    advice = getattr(value, "advice", None)
    top_acts = list(getattr(value, "top_actions", ()))

    # Decorate top_actions with domain prefix + severity weight
    # for cross-domain ranking
    cross: list[tuple[int, str, str]] = []
    for line in top_acts:
        weight, sev = _extract_severity_weight(line)
        cross.append((
            weight,
            sev,
            f"[{domain}] {line}",
        ))

    return (
        DomainResult(
            domain=domain, ran=True, grade=grade, score=score,
            findings_count=findings_count,
            blockers_count=blockers_count,
            error=None, advice=advice,
        ),
        findings_count,
        blockers_count,
        cross,
    )


def _score_for_domain(domain: str, grade: str | None) -> float:
    if grade is None:
        return 0.0
    table = {
        "seniority": _SENIORITY_GRADE_SCORES,
        "security": _SECURITY_GRADE_SCORES,
        "localization": _LOCALIZATION_GRADE_SCORES,
        "dependencies": _DEPENDENCIES_GRADE_SCORES,
        "test_quality": _TEST_QUALITY_GRADE_SCORES,
    }.get(domain, {})
    return float(table.get(grade, 50))  # unknown grade → 50


def _count_blockers(domain: str, findings) -> int:
    """Count blocker/critical severity findings."""
    blocker_terms = (
        "blocker", "critical",
    )
    return sum(
        1 for f in findings
        if getattr(f.severity, "value", str(f.severity)) in blocker_terms
    )


def _extract_severity_weight(line: str) -> tuple[int, str]:
    """Parse a top_action line like '[blocker] rule_name x3 — fix'."""
    for sev, weight in (
        ("critical", 100),
        ("blocker", 80),
        ("serious", 40),
        ("high", 40),
        ("medium", 10),
        ("minor", 5),
    ):
        if f"[{sev}]" in line:
            return weight, sev
    return 1, "info"


def _security_min_severity(min_level: str) -> str:
    """Map shared min_level → security tool's min_severity."""
    return {
        "junior": "medium",
        "mid": "medium",
        "senior": "high",
        "staff": "high",
    }.get(min_level, "medium")


# ============================================================
# Verdict + letter grade
# ============================================================


def _verdict_for(total_blockers: int, score: float) -> Verdict:
    if total_blockers > 0:
        return Verdict.BLOCK
    if score >= 80:
        return Verdict.SHIP
    return Verdict.HOLD


def _letter_grade(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _build_advice(
    verdict: Verdict, letter: str, score: float,
    n_findings: int, n_blockers: int,
    domains: list[DomainResult], ran_in_s: float,
) -> str:
    ran_domains = ", ".join(d.domain for d in domains if d.ran)
    domain_grades = " · ".join(
        f"{d.domain}={d.grade or 'error'}"
        for d in domains if d.ran
    )
    if verdict == Verdict.BLOCK:
        verdict_line = (
            f"BLOCK — {n_blockers} blocker(s) detected. Do not ship."
        )
    elif verdict == Verdict.HOLD:
        verdict_line = (
            f"HOLD — composite {score:.0f}/100 below 80. "
            "Resolve top issues before merge."
        )
    else:
        verdict_line = f"SHIP — composite {score:.0f}/100. Ready to release."
    return (
        f"{verdict_line} Grade: {letter}. "
        f"{n_findings} findings across [{ran_domains}] in "
        f"{ran_in_s:.2f}s. ({domain_grades})"
    )

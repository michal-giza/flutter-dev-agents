"""Dependency / supply-chain audit.

Walks pubspec.yaml + pubspec.lock + lib/*.dart imports to catch
the smells most likely to bite a Flutter app's supply chain:

  • Floating version ranges on security-sensitive packages
  • Git / path overrides in apps that ship to production
  • Dev tools accidentally landed in dependencies (vs dev_dependencies)
  • Unused dependencies (declared but never imported)
  • Transitive-as-direct (imported in lib/ but not in pubspec)
  • Duplicates across dependencies + dev_dependencies
  • Known-vulnerable / known-deprecated packages (small hardcoded list)
  • Major-version drift between pubspec constraint and lock pin
  • GPL/AGPL license signals (best-effort detection)
  • Loose Flutter SDK constraint (`>=3.0.0` without upper bound)

What this is NOT
----------------
  • Not a pub.dev API call. No network. No CVE database lookup.
    The 'known vulnerable' list is a small, curated set
    encoding well-publicized issues. The right place to lookup
    real CVEs is `flutter pub outdated` + Dependabot — this
    tool runs offline and gives a fast, repeatable signal.
  • Not a license auditor for compliance — we surface license
    risk indicators, not a legal opinion.
  • Not a transitive vulnerability scanner — we only check the
    lockfile names, not their transitive trees.

Pure compute. Sub-second on any pubspec.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..failures import FilesystemFailure
from ..result import Result, err, ok
from .base import BaseUseCase


class Severity(str, Enum):
    BLOCKER = "blocker"
    SERIOUS = "serious"
    MINOR = "minor"


class DependencyLevel(str, Enum):
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"


@dataclass(frozen=True, slots=True)
class DependencyFinding:
    rule: str
    description: str
    severity: Severity
    level: DependencyLevel
    file: str                # 'pubspec.yaml' / 'pubspec.lock' / dart file
    line: int                # 1-indexed; 0 for file-level
    package: str | None      # the affected package name when applicable
    snippet: str
    fix_hint: str | None
    standard: str | None


@dataclass(frozen=True, slots=True)
class AuditDependenciesParams:
    project_path: Path
    min_level: str = "junior"
    # Whether this app ships to production (changes the severity
    # of git:/path: overrides; for in-house tools they're fine).
    is_published: bool = True
    max_findings: int = 200


@dataclass(frozen=True, slots=True)
class AuditDependenciesResult:
    grade: str                              # clean / acceptable / at_risk / blocked
    score: float                            # weighted findings per dep
    deps_total: int                         # main dependencies count
    dev_deps_total: int                     # dev_dependencies count
    deps_unused: int                        # declared but unimported
    deps_undeclared: int                    # imported but not declared
    findings: tuple[DependencyFinding, ...]
    findings_by_level: dict[str, int]
    findings_by_severity: dict[str, int]
    top_actions: tuple[str, ...]
    advice: str


_SEVERITY_WEIGHT = {
    Severity.BLOCKER: 10,
    Severity.SERIOUS: 4,
    Severity.MINOR: 1,
}


# ---- knowledge bases (curated, intentionally short) --------------------


# Packages a publish-ready app should pin tightly, not float on `^`
# — security-sensitive surface where a minor version can land a
# breaking auth change or a CVE patch you want explicitly.
_SECURITY_SENSITIVE_PACKAGES = frozenset({
    "firebase_auth", "firebase_core", "firebase_messaging",
    "firebase_remote_config",
    "google_sign_in", "sign_in_with_apple",
    "flutter_secure_storage",
    "dio", "http",
    "webview_flutter", "webview_flutter_android", "webview_flutter_wkwebview",
    "url_launcher",
    "local_auth",
    "jwt_decoder",
    "encrypt", "pointycastle",
    "shared_preferences",
})


# Tools that should live in dev_dependencies, never in
# `dependencies`. Landing them in dependencies inflates the
# app binary and ships code only the build needs.
_DEV_ONLY_PACKAGES = frozenset({
    "build_runner", "json_serializable", "freezed",
    "freezed_annotation",   # annotation IS runtime, leave out
    "mockito", "mocktail", "build_test",
    "flutter_test", "integration_test",
    "patrol", "patrol_cli", "patrol_finders",
    "very_good_analysis", "flutter_lints",
    "test", "fake_async",
    "golden_toolkit",
    "injectable_generator",
    "drift_dev",
    "go_router_builder",
})


# Curated list of packages with widely-known issues. Kept SHORT
# on purpose — false positives are worse than false negatives
# here. Each entry: package -> human-readable note.
_KNOWN_PROBLEMATIC_PACKAGES = {
    "flutter_html": (
        "Frequent CVE history; review usage and consider an "
        "allowlist-based renderer."
    ),
    "package_info": (
        "Discontinued — migrate to package_info_plus."
    ),
    "connectivity": (
        "Discontinued — migrate to connectivity_plus."
    ),
    "device_info": (
        "Discontinued — migrate to device_info_plus."
    ),
    "battery": (
        "Discontinued — migrate to battery_plus."
    ),
    "android_intent": (
        "Discontinued — migrate to android_intent_plus."
    ),
    "share": (
        "Discontinued — migrate to share_plus."
    ),
    "sensors": (
        "Discontinued — migrate to sensors_plus."
    ),
    "url_launcher_web": (
        "Web-only — verify you actually need it on web."
    ),
    "image_picker_for_web": (
        "Web-only — verify you actually need it on web."
    ),
}


# License keywords that signal copyleft. We don't read package
# LICENSE files (offline), but the package NAME or pubspec
# `description` sometimes hints. This is best-effort.
_COPYLEFT_LICENSE_HINTS = frozenset({
    "gpl", "agpl", "lgpl",
})


# ============================================================
# Use case
# ============================================================


class AuditDependencies(
    BaseUseCase[AuditDependenciesParams, AuditDependenciesResult]
):
    """Audits pubspec.yaml + pubspec.lock + lib imports.

    Pure compute. No network. Walks the project once, applies 14
    rules across 4 tiers, returns a graded report.
    """

    async def execute(
        self, params: AuditDependenciesParams
    ) -> Result[AuditDependenciesResult]:
        if not params.project_path.is_dir():
            return err(
                FilesystemFailure(
                    message=f"project_path not found: {params.project_path}",
                    next_action="fix_arguments",
                )
            )

        try:
            min_level = DependencyLevel(params.min_level)
        except ValueError:
            return err(
                FilesystemFailure(
                    message=(
                        f"unknown min_level {params.min_level!r}. "
                        "Valid: junior, mid, senior, staff"
                    ),
                    next_action="fix_arguments",
                )
            )

        pubspec = params.project_path / "pubspec.yaml"
        lockfile = params.project_path / "pubspec.lock"
        if not pubspec.is_file():
            return err(
                FilesystemFailure(
                    message=f"pubspec.yaml not found at {pubspec}",
                    next_action="fix_arguments",
                )
            )

        pubspec_text = pubspec.read_text(encoding="utf-8", errors="replace")
        deps, dev_deps, sdk_constraints = _parse_pubspec(pubspec_text)
        lock_pins = (
            _parse_lock(lockfile.read_text(encoding="utf-8", errors="replace"))
            if lockfile.is_file() else {}
        )

        # Walk lib/ imports
        used_packages = _collect_imported_packages(
            params.project_path / "lib"
        )

        all_findings: list[DependencyFinding] = []

        # Apply rules
        all_findings.extend(
            _check_floating_security_sensitive(deps)
        )
        all_findings.extend(
            _check_overrides_in_published(
                deps, dev_deps, params.is_published
            )
        )
        all_findings.extend(
            _check_dev_only_in_main(deps)
        )
        all_findings.extend(
            _check_unused_deps(deps, used_packages)
        )
        all_findings.extend(
            _check_undeclared_imports(
                deps, dev_deps, used_packages
            )
        )
        all_findings.extend(
            _check_duplicate_across_sections(deps, dev_deps)
        )
        all_findings.extend(
            _check_known_problematic(deps, dev_deps)
        )
        all_findings.extend(
            _check_pubspec_vs_lock_drift(deps, lock_pins)
        )
        all_findings.extend(
            _check_wide_version_ranges(deps)
        )
        all_findings.extend(
            _check_flutter_sdk_constraint(sdk_constraints)
        )
        all_findings.extend(
            _check_copyleft_hints(deps, dev_deps)
        )

        # Filter by min_level
        order = [
            DependencyLevel.JUNIOR, DependencyLevel.MID,
            DependencyLevel.SENIOR, DependencyLevel.STAFF,
        ]
        kept_levels = set(order[order.index(min_level):])
        all_findings = [f for f in all_findings if f.level in kept_levels]

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
        n_deps = max(len(deps), 1)
        score = weighted / n_deps
        grade = _grade_for(score, by_sev)

        # Counts
        deps_unused = len(set(deps.keys()) - used_packages - _IMPLICIT_DEPS)
        deps_undeclared = len(
            used_packages
            - set(deps.keys())
            - set(dev_deps.keys())
            - _IMPLICIT_DEPS
        )

        return ok(AuditDependenciesResult(
            grade=grade,
            score=round(score, 2),
            deps_total=len(deps),
            dev_deps_total=len(dev_deps),
            deps_unused=deps_unused,
            deps_undeclared=deps_undeclared,
            findings=all_findings_t,
            findings_by_level=by_level,
            findings_by_severity=by_sev,
            top_actions=_build_top_actions(all_findings_t),
            advice=_build_advice(
                grade, len(deps), deps_unused, deps_undeclared,
            ),
        ))


# ============================================================
# Parsers
# ============================================================


# Implicit packages — always available, never need to be in
# pubspec deps section.
_IMPLICIT_DEPS = frozenset({
    "flutter", "dart", "sky_engine", "flutter_test",
    "flutter_localizations", "flutter_driver",
    "flutter_web_plugins", "integration_test",
})


# Match a `package:` import line.
_RE_PACKAGE_IMPORT = re.compile(
    r"""^\s*(?:import|export)\s+['"]package:([a-z_][a-z0-9_]*)/""",
    re.MULTILINE,
)


def _parse_pubspec(
    text: str,
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Parse pubspec.yaml into ({pkg: version}, {pkg: version},
    {sdk: constraint}).

    Intentionally simple — we don't use a YAML library since
    that would add a dependency. Handles the 99% of pubspecs.
    """
    lines = text.splitlines()
    section = None  # None / 'deps' / 'dev_deps' / 'env'
    deps: dict[str, str] = {}
    dev_deps: dict[str, str] = {}
    sdk: dict[str, str] = {}

    for raw in lines:
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        # Section headers (no leading whitespace)
        if re.match(r"^[A-Za-z_]+:\s*$", line):
            head = line.rstrip(":").strip()
            if head == "dependencies":
                section = "deps"
            elif head == "dev_dependencies":
                section = "dev_deps"
            elif head == "environment":
                section = "env"
            else:
                section = None
            continue
        if section is None:
            continue
        # Top-level entry within a section: exactly 2 leading spaces.
        # `    sdk: flutter` (4 spaces) is a nested key, NOT a package.
        m = re.match(r"^ {2}([a-z][a-z0-9_]*):\s*(.*)$", line)
        if not m:
            continue
        name, value = m.group(1), m.group(2).strip()
        bucket = (
            deps if section == "deps"
            else dev_deps if section == "dev_deps"
            else sdk
        )
        if value:
            bucket[name] = value
        else:
            # Nested map — value follows on subsequent indented lines.
            bucket[name] = "<nested>"

    return deps, dev_deps, sdk


def _parse_lock(text: str) -> dict[str, str]:
    """Parse pubspec.lock for package -> pinned version.

    Hand-parser — looks for the `  package_name:` indent then
    later `    version: "1.2.3"` line. Sufficient for the rules
    that need it.
    """
    pins: dict[str, str] = {}
    cur_pkg: str | None = None
    for line in text.splitlines():
        m = re.match(r"^  ([a-z][a-z0-9_]*):\s*$", line)
        if m:
            cur_pkg = m.group(1)
            continue
        if cur_pkg:
            mv = re.match(
                r"^    version:\s*['\"]([^'\"]+)['\"]", line,
            )
            if mv:
                pins[cur_pkg] = mv.group(1)
                cur_pkg = None
    return pins


def _collect_imported_packages(lib: Path) -> set[str]:
    if not lib.is_dir():
        return set()
    used: set[str] = set()
    for f in lib.rglob("*.dart"):
        # Skip generated
        name = f.name
        if (
            name.endswith(".g.dart")
            or name.endswith(".freezed.dart")
            or name.endswith(".gr.dart")
            or name.endswith(".mocks.dart")
            or name.endswith(".config.dart")
        ):
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in _RE_PACKAGE_IMPORT.finditer(content):
            used.add(m.group(1))
    return used


# ============================================================
# Rule implementations
# ============================================================


def _check_floating_security_sensitive(
    deps: dict[str, str],
) -> list[DependencyFinding]:
    out: list[DependencyFinding] = []
    for pkg, ver in deps.items():
        if pkg not in _SECURITY_SENSITIVE_PACKAGES:
            continue
        # Floating: starts with `^` (caret), or `any`, or wide
        # range like `'>=1.0.0 <3.0.0'`
        if ver.startswith("^") or ver == "any":
            out.append(_mk(
                "pinned_to_caret_only",
                f"{pkg} uses caret range {ver!r} — security-"
                "sensitive packages benefit from tighter pinning.",
                Severity.MINOR, DependencyLevel.MID,
                "pubspec.yaml", 0, pkg, f"{pkg}: {ver}",
                f"Pin tightly: `{pkg}: '{_caret_without_caret(ver)}'` "
                "and bump deliberately.",
                "OWASP Dependency Management",
            ))
    return out


def _check_overrides_in_published(
    deps: dict[str, str],
    dev_deps: dict[str, str],
    is_published: bool,
) -> list[DependencyFinding]:
    out: list[DependencyFinding] = []
    if not is_published:
        return out
    for pkg, ver in {**deps, **dev_deps}.items():
        # `flutter: { sdk: flutter }` and `flutter_test: { sdk: flutter }`
        # are the canonical Flutter SDK declarations, NOT overrides.
        # Same for `flutter_localizations`, `integration_test`, etc.
        if pkg in _IMPLICIT_DEPS:
            continue
        if ver == "<nested>":
            # Nested map — likely git: / path: / hosted: override.
            # We can't see the children with this parser, but a
            # bare `<nested>` value on a known-public-name is a
            # smell to surface.
            out.append(_mk(
                "git_or_path_override",
                f"{pkg} uses a nested override (git:/path:/hosted:). "
                "Publish-time risk — vendors a non-pub.dev source.",
                Severity.SERIOUS, DependencyLevel.JUNIOR,
                "pubspec.yaml", 0, pkg, f"{pkg}: <nested>",
                "Replace with a published version from pub.dev "
                "before publishing the app.",
                "Pub publish policy",
            ))
    return out


def _check_dev_only_in_main(
    deps: dict[str, str],
) -> list[DependencyFinding]:
    out: list[DependencyFinding] = []
    for pkg in deps:
        if pkg in _DEV_ONLY_PACKAGES:
            out.append(_mk(
                "dev_dep_in_dependencies",
                f"{pkg} is a build/test tool but is in `dependencies` "
                "— inflates app binary.",
                Severity.SERIOUS, DependencyLevel.JUNIOR,
                "pubspec.yaml", 0, pkg, f"{pkg}: {deps[pkg]}",
                f"Move {pkg} under `dev_dependencies:`.",
                "Flutter docs: dev_dependencies",
            ))
    return out


def _check_unused_deps(
    deps: dict[str, str],
    used: set[str],
) -> list[DependencyFinding]:
    out: list[DependencyFinding] = []
    declared = set(deps.keys()) - _IMPLICIT_DEPS
    unused = declared - used
    # Cap at 20
    for pkg in sorted(unused)[:20]:
        out.append(_mk(
            "unused_dependency",
            f"{pkg} declared in pubspec but never imported under lib/.",
            Severity.MINOR, DependencyLevel.SENIOR,
            "pubspec.yaml", 0, pkg, f"{pkg}: {deps[pkg]}",
            f"Remove {pkg} from pubspec, or move it to "
            "`dev_dependencies` if only used by tests.",
            "Code-pubspec consistency",
        ))
    return out


def _check_undeclared_imports(
    deps: dict[str, str],
    dev_deps: dict[str, str],
    used: set[str],
) -> list[DependencyFinding]:
    out: list[DependencyFinding] = []
    declared = set(deps.keys()) | set(dev_deps.keys()) | _IMPLICIT_DEPS
    undeclared = used - declared
    for pkg in sorted(undeclared)[:20]:
        out.append(_mk(
            "transitive_used_as_direct",
            f"{pkg} imported under lib/ but not declared in pubspec "
            "(works only as long as it stays transitive).",
            Severity.SERIOUS, DependencyLevel.SENIOR,
            "pubspec.yaml", 0, pkg, pkg,
            f"Add `{pkg}:` under dependencies with an explicit "
            "version constraint.",
            "Pub: direct vs transitive",
        ))
    return out


def _check_duplicate_across_sections(
    deps: dict[str, str],
    dev_deps: dict[str, str],
) -> list[DependencyFinding]:
    out: list[DependencyFinding] = []
    for pkg in set(deps.keys()) & set(dev_deps.keys()):
        out.append(_mk(
            "duplicated_dependency",
            f"{pkg} declared in both dependencies and dev_dependencies. "
            "Ambiguous resolution.",
            Severity.SERIOUS, DependencyLevel.SENIOR,
            "pubspec.yaml", 0, pkg, pkg,
            f"Pick one section for {pkg} and remove it from the other.",
            "Pub spec rules",
        ))
    return out


def _check_known_problematic(
    deps: dict[str, str],
    dev_deps: dict[str, str],
) -> list[DependencyFinding]:
    out: list[DependencyFinding] = []
    for pkg in {**deps, **dev_deps}:
        if pkg in _KNOWN_PROBLEMATIC_PACKAGES:
            note = _KNOWN_PROBLEMATIC_PACKAGES[pkg]
            out.append(_mk(
                "known_vulnerable_package",
                f"{pkg}: {note}",
                Severity.SERIOUS, DependencyLevel.STAFF,
                "pubspec.yaml", 0, pkg, pkg,
                note,
                "Curated supply-chain checklist",
            ))
    return out


def _check_pubspec_vs_lock_drift(
    deps: dict[str, str],
    lock_pins: dict[str, str],
) -> list[DependencyFinding]:
    out: list[DependencyFinding] = []
    for pkg, ver in deps.items():
        pinned = lock_pins.get(pkg)
        if not pinned:
            continue
        if not ver.startswith("^"):
            continue
        # caret major mismatch with the lockfile
        ver_clean = ver.lstrip("^")
        ver_major = _major(ver_clean)
        lock_major = _major(pinned)
        if ver_major is not None and lock_major is not None and lock_major > ver_major:
            out.append(_mk(
                "outdated_majors",
                f"{pkg}: pubspec says ^{ver_clean} but lock pinned "
                f"{pinned} — major mismatch impossible (this is bad data).",
                Severity.MINOR, DependencyLevel.MID,
                "pubspec.lock", 0, pkg, f"{pkg}: pubspec={ver} lock={pinned}",
                "Run `flutter pub upgrade --major-versions` and "
                "review the change.",
                "pub version constraints",
            ))
    return out


def _check_wide_version_ranges(
    deps: dict[str, str],
) -> list[DependencyFinding]:
    out: list[DependencyFinding] = []
    for pkg, ver in deps.items():
        # Wide range: `'>=1.0.0 <3.0.0'` spans 2+ majors
        m = re.match(
            r"['\"]?\s*>=\s*(\d+)\.\d+\.\d+\s+<\s*(\d+)\.\d+\.\d+",
            ver,
        )
        if not m:
            continue
        lower, upper = int(m.group(1)), int(m.group(2))
        if upper - lower >= 2:
            out.append(_mk(
                "wide_version_range",
                f"{pkg}: range {ver!r} spans {upper - lower} major "
                "versions — breaking changes can slip in silently.",
                Severity.SERIOUS, DependencyLevel.MID,
                "pubspec.yaml", 0, pkg, f"{pkg}: {ver}",
                "Tighten the upper bound; ratchet up explicitly when "
                "you've tested.",
                "Semantic versioning",
            ))
    return out


def _check_flutter_sdk_constraint(
    sdk: dict[str, str],
) -> list[DependencyFinding]:
    out: list[DependencyFinding] = []
    for key, ver in sdk.items():
        if key not in ("flutter", "sdk"):
            continue
        # Loose: starts with `>=` and has no `<` upper bound
        if re.match(r"['\"]?\s*>=\s*\d+\.\d+", ver) and "<" not in ver:
            out.append(_mk(
                "flutter_sdk_constraint_loose",
                f"environment {key}: {ver!r} has no upper bound — "
                "future Flutter SDK changes can break the app silently.",
                Severity.MINOR, DependencyLevel.STAFF,
                "pubspec.yaml", 0, key, f"{key}: {ver}",
                f"Constrain to a tested range: "
                f"`{key}: '>=3.16.0 <4.0.0'`.",
                "pub environment constraints",
            ))
    return out


def _check_copyleft_hints(
    deps: dict[str, str],
    dev_deps: dict[str, str],
) -> list[DependencyFinding]:
    """Surface packages whose NAME contains gpl/agpl/lgpl as a
    weak hint. False positives expected; rare in practice."""
    out: list[DependencyFinding] = []
    for pkg in {**deps, **dev_deps}:
        lower = pkg.lower()
        for hint in _COPYLEFT_LICENSE_HINTS:
            if hint in lower:
                out.append(_mk(
                    "license_blocklist",
                    f"Package name {pkg!r} contains '{hint}' — "
                    "possible copyleft license. Verify before shipping.",
                    Severity.MINOR, DependencyLevel.STAFF,
                    "pubspec.yaml", 0, pkg, pkg,
                    f"Inspect {pkg}'s LICENSE; replace if "
                    "copyleft conflicts with your distribution.",
                    "License compatibility",
                ))
                break
    return out


# ============================================================
# Helpers
# ============================================================


def _major(version: str) -> int | None:
    m = re.match(r"^(\d+)", version)
    return int(m.group(1)) if m else None


def _caret_without_caret(ver: str) -> str:
    return ver.lstrip("^").strip("'\"")


def _mk(
    rule: str, desc: str, severity: Severity, level: DependencyLevel,
    file: str, line: int, package: str | None,
    snippet: str, fix_hint: str | None, standard: str | None,
) -> DependencyFinding:
    return DependencyFinding(
        rule=rule, description=desc, severity=severity, level=level,
        file=file, line=line, package=package, snippet=snippet[:140],
        fix_hint=fix_hint, standard=standard,
    )


def _grade_for(score: float, by_sev: dict[str, int]) -> str:
    if by_sev.get("blocker", 0) > 0:
        return "blocked"
    if by_sev.get("serious", 0) >= 5 or score >= 4:
        return "at_risk"
    if by_sev.get("serious", 0) > 0 or score >= 1:
        return "acceptable"
    return "clean"


def _build_top_actions(
    findings: tuple[DependencyFinding, ...],
) -> tuple[str, ...]:
    if not findings:
        return ("No dependency findings at the configured threshold.",)
    counts: dict[str, tuple[int, DependencyFinding]] = {}
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
    grade: str, deps_total: int, unused: int, undeclared: int,
) -> str:
    if grade == "blocked":
        tail = "STOP — resolve blockers before merge."
    else:
        tail = (
            "Tighten security-sensitive pins; remove unused; "
            "declare what you import."
        )
    return (
        f"Dependency grade: {grade}. {deps_total} direct deps, "
        f"{unused} unused, {undeclared} undeclared. {tail}"
    )

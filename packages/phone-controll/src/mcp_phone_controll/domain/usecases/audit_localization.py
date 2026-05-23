"""Localization audit — i18n hygiene scanner.

A Polish-locale phone broke `tap_text('Settings')` in an earlier
session because the visible label was `Ustawienia`, not 'Settings'.
That's the moral of this tool: hardcoded user-facing strings
silently break your app the moment a user switches their phone
language.

What this catches that `flutter analyze` won't:

  • `Text('Sign in')` instead of `AppLocalizations.of(ctx)!.signIn`
  • Keys referenced in code but missing from `intl_en.arb`
  • Keys defined in `intl_en.arb` but missing from `intl_pl.arb`
  • `supportedLocales:` in `MaterialApp` that doesn't match the
    arb files actually shipped
  • String concatenation (`'Hello ' + name + '!'`) where Intl
    parameters should be
  • Pluralization done with `if (count == 1)` instead of
    `Intl.plural`
  • RTL-broken UI on a project that supports Arabic/Hebrew

Scope of v0.3.0:

  • Walks lib/*.dart (excluding generated) for hardcoded strings
    inside common user-facing widgets (Text, Tooltip, AppBar
    title, ElevatedButton/TextButton/etc. child, SnackBar
    content, AlertDialog title/content).
  • Parses lib/l10n/*.arb files to build the key catalog and
    cross-reference against code usage.
  • Checks pubspec.yaml for the `flutter_localizations` SDK
    dependency.
  • Checks MaterialApp's supportedLocales (via regex — no AST).

What this is NOT:

  • Not a machine-translation engine. We flag missing
    translations; we don't fill them in.
  • Not a runtime checker. We can't tell if `supportedLocales`
    actually matches what gets loaded at boot — only that the
    static config and arb files are consistent.
  • Not RTL-perfect. We flag the absence of RTL plumbing; we
    can't verify any given layout actually mirrors correctly.

Citations:

  Flutter docs: Internationalizing Flutter apps
  ICU MessageFormat (the standard `Intl.plural` / `Intl.gender`
  syntax)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..failures import FilesystemFailure
from ..result import Result, err, ok
from ._helpers import is_path_excluded
from .base import BaseUseCase


class Severity(str, Enum):
    BLOCKER = "blocker"   # ships broken text to non-default locales
    SERIOUS = "serious"   # missing/inconsistent l10n
    MINOR = "minor"       # cleanup / best practice


class LocalizationLevel(str, Enum):
    JUNIOR = "junior"     # hardcoded strings (the obvious smell)
    MID = "mid"           # missing keys / orphan keys
    SENIOR = "senior"     # plumbing wired wrong
    STAFF = "staff"       # missing RTL / pluralization architecture


@dataclass(frozen=True, slots=True)
class LocalizationFinding:
    rule: str
    description: str
    severity: Severity
    level: LocalizationLevel
    file: str
    line: int
    snippet: str
    fix_hint: str | None
    standard: str | None


@dataclass(frozen=True, slots=True)
class AuditLocalizationParams:
    project_path: Path
    # Subset paths to scan. Default: ['lib'].
    paths: tuple[str, ...] = ()
    # Path to arb files relative to project. Default tries
    # 'lib/l10n' then 'l10n' then './'.
    arb_dir: str | None = None
    # Minimum tier to report.
    min_level: str = "junior"
    # Cap on findings returned.
    max_findings: int = 200


@dataclass(frozen=True, slots=True)
class AuditLocalizationResult:
    grade: str                                  # well_localized / acceptable / single_locale / missing_l10n
    score: float                                # weighted findings per KLOC
    locales_detected: tuple[str, ...]           # ['en', 'pl', 'de'] — from arb files
    keys_total: int                             # total keys across all locales
    keys_used: int                              # keys referenced in code
    keys_unused: int                            # keys defined but never used
    hardcoded_strings: int                      # count of unique hardcoded user-facing strings
    files_scanned: int
    lines_scanned: int
    findings: tuple[LocalizationFinding, ...]
    findings_by_level: dict[str, int]
    findings_by_severity: dict[str, int]
    top_actions: tuple[str, ...]
    advice: str


_SEVERITY_WEIGHT = {
    Severity.BLOCKER: 10,
    Severity.SERIOUS: 4,
    Severity.MINOR: 1,
}


class AuditLocalization(
    BaseUseCase[AuditLocalizationParams, AuditLocalizationResult]
):
    """Scans a Flutter project for i18n hygiene problems.

    Pure compute. No LLM, no device, no network. Regex over .dart
    files + JSON parse of .arb files. Catches the patterns that
    silently break apps on non-default locales.
    """

    async def execute(
        self, params: AuditLocalizationParams
    ) -> Result[AuditLocalizationResult]:
        if not params.project_path.is_dir():
            return err(
                FilesystemFailure(
                    message=f"project_path not found: {params.project_path}",
                    next_action="fix_arguments",
                )
            )

        try:
            min_level = LocalizationLevel(params.min_level)
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

        # --- step 1: discover arb files + parse key catalog ---
        arb_root = _resolve_arb_dir(params.project_path, params.arb_dir)
        arb_catalog, locales = _parse_arb_files(arb_root)
        default_keys = arb_catalog.get(
            _default_locale(locales), set()
        )

        # --- step 2: walk dart files ---
        roots = _resolve_roots(params.project_path, params.paths)
        files = _collect_dart_files(roots, params.project_path)
        all_findings: list[LocalizationFinding] = []
        used_keys: set[str] = set()
        hardcoded_strings: set[str] = set()
        lines_total = 0

        for f in files:
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            lines = content.splitlines()
            lines_total += len(lines)
            rel = str(f.relative_to(params.project_path))
            findings, used, hardcoded = _scan_dart(
                rel, lines, content, default_keys,
            )
            all_findings.extend(findings)
            used_keys.update(used)
            hardcoded_strings.update(hardcoded)

        # --- step 3: cross-locale + plumbing checks ---
        all_findings.extend(
            _check_missing_keys_per_locale(arb_catalog, locales)
        )
        all_findings.extend(
            _check_unused_keys(default_keys, used_keys, locales)
        )
        all_findings.extend(
            _check_pubspec_and_app(params.project_path, locales)
        )

        # --- filter by min_level ---
        order = [
            LocalizationLevel.JUNIOR, LocalizationLevel.MID,
            LocalizationLevel.SENIOR, LocalizationLevel.STAFF,
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
        kloc = max(lines_total, 1) / 1000.0
        score = weighted / kloc if kloc > 0 else 0.0

        keys_unused = max(
            0, len(default_keys) - len(used_keys & default_keys)
        )

        grade = _grade_for(
            score, locales, len(default_keys), len(hardcoded_strings),
        )
        advice = _build_advice(
            grade, locales, len(hardcoded_strings), keys_unused,
        )

        return ok(AuditLocalizationResult(
            grade=grade,
            score=round(score, 2),
            locales_detected=tuple(sorted(locales)),
            keys_total=len(default_keys),
            keys_used=len(used_keys & default_keys),
            keys_unused=keys_unused,
            hardcoded_strings=len(hardcoded_strings),
            files_scanned=len(files),
            lines_scanned=lines_total,
            findings=all_findings_t,
            findings_by_level=by_level,
            findings_by_severity=by_sev,
            top_actions=_build_top_actions(all_findings_t),
            advice=advice,
        ))


# ============================================================
# Arb discovery + parsing
# ============================================================


def _resolve_arb_dir(project: Path, override: str | None) -> Path | None:
    if override:
        candidate = project / override
        return candidate if candidate.is_dir() else None
    for guess in ("lib/l10n", "l10n", "lib/src/l10n"):
        candidate = project / guess
        if candidate.is_dir() and any(candidate.glob("*.arb")):
            return candidate
    return None


def _parse_arb_files(
    arb_root: Path | None,
) -> tuple[dict[str, set[str]], set[str]]:
    """Returns ({locale_code: set_of_keys}, set_of_locale_codes)."""
    catalog: dict[str, set[str]] = {}
    locales: set[str] = set()
    if not arb_root:
        return catalog, locales
    for arb_file in arb_root.glob("*.arb"):
        locale = _locale_from_filename(arb_file.name)
        if not locale:
            continue
        try:
            data = json.loads(
                arb_file.read_text(encoding="utf-8", errors="replace")
            )
        except (json.JSONDecodeError, OSError):
            continue
        # Filter out metadata keys (those starting with '@')
        keys = {
            k for k in data
            if isinstance(k, str) and not k.startswith("@")
        }
        catalog[locale] = keys
        locales.add(locale)
    return catalog, locales


def _locale_from_filename(name: str) -> str | None:
    """Extract locale code from arb filename.

    Handles `app_en.arb`, `intl_en.arb`, `messages_pl.arb`,
    `en.arb`, and variants. Returns None for files that don't
    match a known pattern.
    """
    if not name.endswith(".arb"):
        return None
    stem = name.removesuffix(".arb")
    # patterns: app_en, intl_en, messages_pl, app_pt_BR
    m = re.match(r"^(?:app|intl|messages)_([a-z]{2,3}(?:_[A-Z]{2})?)$", stem)
    if m:
        return m.group(1)
    # Bare locale code: en.arb, pl.arb
    if re.match(r"^[a-z]{2,3}(?:_[A-Z]{2})?$", stem):
        return stem
    return None


def _default_locale(locales: set[str]) -> str:
    """Pick the default locale. Prefer 'en', else first
    alphabetically."""
    if "en" in locales:
        return "en"
    return min(locales) if locales else "en"


# ============================================================
# Dart file scanner
# ============================================================


def _resolve_roots(
    project: Path, paths: tuple[str, ...]
) -> list[Path]:
    if not paths:
        lib = project / "lib"
        return [lib] if lib.is_dir() else []
    return [
        project / p for p in paths if (project / p).exists()
    ]


def _collect_dart_files(
    roots: list[Path], project_root: Path,
) -> list[Path]:
    out: list[Path] = []
    for root in roots:
        if root.is_file() and root.suffix == ".dart":
            out.append(root)
            continue
        if not root.is_dir():
            continue
        for f in root.rglob("*.dart"):
            # Skip build/, .claude/worktrees/, etc.
            # (v0.3.0 field-test calibration finding)
            if is_path_excluded(f, project_root):
                continue
            name = f.name
            if (
                name.endswith(".g.dart")
                or name.endswith(".freezed.dart")
                or name.endswith(".gr.dart")
                or name.endswith(".mocks.dart")
                or name.endswith(".config.dart")
                or ".gen." in name
            ):
                continue
            out.append(f)
    return sorted(out)


# Heuristic: a hardcoded user-facing string is a literal inside
# one of these widget constructors. Three or more chars, contains
# at least one letter, NOT something that's clearly a key/code
# (no spaces in the value rules it out for `find.text` test
# selectors etc, but we strip those by file location below).
_RE_USER_TEXT_WIDGETS = re.compile(
    r"(?:^|[\s,(\[{])(?:Text|AppBar\s*\(\s*title:\s*Text|"
    r"Tooltip\s*\(\s*message:|"
    r"ElevatedButton(?:\.icon)?\s*\([^)]*child:\s*Text|"
    r"TextButton\s*\([^)]*child:\s*Text|"
    r"OutlinedButton\s*\([^)]*child:\s*Text|"
    r"FilledButton\s*\([^)]*child:\s*Text|"
    r"SnackBar\s*\(\s*content:\s*Text|"
    r"AlertDialog\s*\([^)]*title:\s*Text|"
    r"label:\s*Text|"
    r"hintText:|labelText:|helperText:|errorText:)"
    r"\s*\(?\s*['\"]([^'\"]{3,})['\"]"
)

_RE_L10N_REFERENCE = re.compile(
    r"\bAppLocalizations\.of\(\s*\w+\s*\)[!?]?\.([A-Za-z_]\w+)"
    r"|\bcontext\.l10n\.([A-Za-z_]\w+)"
)

_RE_INTL_MESSAGE = re.compile(r"\bIntl\.message\s*\(")
_RE_STRING_CONCAT = re.compile(
    r"['\"][A-Za-z][^'\"]{0,40}\s*['\"]\s*\+\s*\w+\s*\+\s*['\"]"
)
_RE_PLURAL_VIA_IF = re.compile(
    r"\b(\w+)\s*==\s*1\s*\?\s*['\"]([^'\"]+)['\"]\s*:\s*['\"]([^'\"]+)['\"]"
)
_RE_SUPPORTED_LOCALES = re.compile(
    r"supportedLocales\s*:\s*(?:const\s+)?\[([^\]]+)\]",
    re.DOTALL,
)
_RE_LOCALE_LITERAL = re.compile(r"Locale\s*\(\s*['\"]([a-z]{2,3})['\"]")
_RE_LOCALIZATIONS_DELEGATES = re.compile(
    # Accept BOTH a literal list (`localizationsDelegates: [..]`)
    # AND a getter reference (`localizationsDelegates:
    # AppLocalizations.localizationsDelegates`). Surfaced by v0.3.0
    # field test on bike_news_room (which uses the getter style).
    r"localizationsDelegates\s*:\s*(?:const\s+)?(?:\[|[\w.]+)"
)
_RE_RTL_LOCALES = re.compile(r"['\"](ar|he|fa|ur|yi|sd|ps)['\"]")
_RE_DIRECTIONALITY = re.compile(r"\bDirectionality\s*\(|TextDirection\.")


def _scan_dart(
    rel: str,
    lines: list[str],
    content: str,
    default_keys: set[str],
) -> tuple[list[LocalizationFinding], set[str], set[str]]:
    """Walk a single .dart file. Returns (findings, used_keys,
    hardcoded_strings)."""
    findings: list[LocalizationFinding] = []
    used_keys: set[str] = set()
    hardcoded: set[str] = set()

    # Skip test files — `find.text('Sign in')` is intentional.
    if "/test/" in rel or rel.endswith("_test.dart"):
        return findings, used_keys, hardcoded
    # Skip l10n generated dir.
    if "/l10n/" in rel and "intl_" in rel:
        return findings, used_keys, hardcoded

    # Used keys from AppLocalizations or l10n extension calls
    for m in _RE_L10N_REFERENCE.finditer(content):
        key = m.group(1) or m.group(2)
        if key:
            used_keys.add(key)

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()

        # Junior: hardcoded user-facing string
        for m in _RE_USER_TEXT_WIDGETS.finditer(line):
            value = m.group(1)
            if not _looks_user_facing(value):
                continue
            hardcoded.add(value)
            findings.append(_mk(
                "hardcoded_user_text",
                f"Hardcoded user-facing string {value!r}. "
                "Move to AppLocalizations / .arb.",
                Severity.SERIOUS, LocalizationLevel.JUNIOR,
                rel, i, stripped[:140],
                "Replace with `AppLocalizations.of(context)!.<key>`; "
                "add the key to your .arb files.",
                "Flutter i18n docs",
            ))

        # Junior: string concatenation with variable
        if _RE_STRING_CONCAT.search(line):
            findings.append(_mk(
                "direct_text_concatenation",
                "String concatenation with a variable. Localization "
                "breaks because word order varies by language.",
                Severity.SERIOUS, LocalizationLevel.MID,
                rel, i, stripped[:140],
                "Use Intl.message with parameters: "
                "`Intl.message('Hello {name}!', args: [name])`.",
                "ICU MessageFormat",
            ))

        # Mid: pluralization via if/else
        if _RE_PLURAL_VIA_IF.search(line):
            findings.append(_mk(
                "pluralization_via_if",
                "Pluralization done with `count == 1 ? ... : ...`. "
                "Breaks for languages with multiple plural forms "
                "(Polish has 3, Arabic has 6).",
                Severity.SERIOUS, LocalizationLevel.STAFF,
                rel, i, stripped[:140],
                "Use Intl.plural with zero/one/few/many/other "
                "categories.",
                "ICU plural rules / Intl.plural",
            ))

    # Mid: code references a key that's NOT in default arb
    if default_keys:
        missing_in_code = used_keys - default_keys
        for key in sorted(missing_in_code):
            findings.append(_mk(
                "missing_l10n_key",
                f"Code references l10n key {key!r} but it's not "
                "defined in the default arb file.",
                Severity.BLOCKER, LocalizationLevel.MID,
                rel, 0, key,
                f"Add `\"{key}\": \"...\"` to your default .arb file "
                "and re-generate.",
                "Flutter intl_utils / flutter gen-l10n",
            ))

    return findings, used_keys, hardcoded


def _looks_user_facing(value: str) -> bool:
    """Filter out things that look like keys, log strings, asset
    paths, MIME types — they're 'strings' but not 'user-facing
    text'."""
    if not value or not value.strip():
        return False
    # Asset / path-shaped
    if value.startswith(("/", "./", "../", "assets/", "package:")):
        return False
    # Looks like an identifier / key (snake_case, kebab-case, no
    # spaces, all lowercase)
    if re.fullmatch(r"[a-z][a-z0-9_]*", value):
        return False
    # MIME / URL
    if value.startswith(("http://", "https://", "data:")):
        return False
    if "/" in value and " " not in value:
        return False
    # Single char / very short — usually punctuation or unit
    if len(value) <= 2:
        return False
    # Looks like a hex / number / date / locale code
    if re.fullmatch(r"[A-F0-9#x\-:]+", value):
        return False
    # Must contain at least one letter
    if not re.search(r"[A-Za-z]", value):
        return False
    return True


# ============================================================
# Cross-locale checks
# ============================================================


def _check_missing_keys_per_locale(
    catalog: dict[str, set[str]],
    locales: set[str],
) -> list[LocalizationFinding]:
    findings: list[LocalizationFinding] = []
    if len(locales) < 2:
        return findings
    default = _default_locale(locales)
    default_keys = catalog.get(default, set())
    for locale in sorted(locales - {default}):
        locale_keys = catalog.get(locale, set())
        missing = default_keys - locale_keys
        for key in sorted(missing):
            findings.append(_mk(
                "missing_translation_for_locale",
                f"Key {key!r} is in {default}.arb but missing from "
                f"{locale}.arb.",
                Severity.SERIOUS, LocalizationLevel.MID,
                f"{locale}.arb", 0, key,
                f"Add `\"{key}\": \"<translation>\"` to {locale}.arb.",
                "Flutter intl_utils",
            ))
    return findings


def _check_unused_keys(
    default_keys: set[str],
    used_keys: set[str],
    locales: set[str],
) -> list[LocalizationFinding]:
    findings: list[LocalizationFinding] = []
    if not default_keys:
        return findings
    unused = default_keys - used_keys
    # Cap at 20 to keep responses bounded
    for key in sorted(unused)[:20]:
        findings.append(_mk(
            "unused_l10n_key",
            f"Key {key!r} defined in .arb but never referenced "
            "in code.",
            Severity.MINOR, LocalizationLevel.MID,
            "*.arb", 0, key,
            "Remove unused key, or wire it into a widget.",
            "Code-arb consistency",
        ))
    return findings


# ============================================================
# Plumbing checks
# ============================================================


def _check_pubspec_and_app(
    project: Path, locales: set[str],
) -> list[LocalizationFinding]:
    findings: list[LocalizationFinding] = []

    # pubspec: flutter_localizations dependency
    pubspec = project / "pubspec.yaml"
    if pubspec.is_file():
        try:
            ps = pubspec.read_text(encoding="utf-8", errors="replace")
        except OSError:
            ps = ""
        if locales and "flutter_localizations" not in ps:
            findings.append(_mk(
                "missing_flutter_localizations",
                "Project has .arb files but pubspec.yaml doesn't "
                "depend on flutter_localizations SDK.",
                Severity.BLOCKER, LocalizationLevel.SENIOR,
                "pubspec.yaml", 0, "flutter_localizations",
                "Add `flutter_localizations: sdk: flutter` under "
                "dependencies.",
                "Flutter i18n setup",
            ))

    # MaterialApp checks: scan lib/ for it
    lib = project / "lib"
    if not lib.is_dir():
        return findings
    for f in lib.rglob("*.dart"):
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "MaterialApp" not in content and "CupertinoApp" not in content:
            continue
        rel = str(f.relative_to(project))

        # supportedLocales vs arb files
        m = _RE_SUPPORTED_LOCALES.search(content)
        if m and locales:
            declared = set(_RE_LOCALE_LITERAL.findall(m.group(1)))
            extra_in_code = declared - locales
            extra_in_arb = locales - declared
            if extra_in_code:
                line_no = content.count("\n", 0, m.start()) + 1
                findings.append(_mk(
                    "supported_locales_mismatch",
                    f"supportedLocales declares {sorted(extra_in_code)} "
                    f"but no matching .arb files exist.",
                    Severity.SERIOUS, LocalizationLevel.SENIOR,
                    rel, line_no, m.group(0)[:140],
                    "Add the missing .arb files or remove the locale "
                    "from supportedLocales.",
                    "MaterialApp.supportedLocales contract",
                ))
            if extra_in_arb:
                line_no = content.count("\n", 0, m.start()) + 1
                findings.append(_mk(
                    "supported_locales_mismatch",
                    f"Arb files exist for {sorted(extra_in_arb)} "
                    "but they're not in supportedLocales.",
                    Severity.SERIOUS, LocalizationLevel.SENIOR,
                    rel, line_no, m.group(0)[:140],
                    "Add `Locale('xx')` to supportedLocales or "
                    "delete the orphan .arb files.",
                    "MaterialApp.supportedLocales contract",
                ))

        # localizationsDelegates set?
        if locales and not _RE_LOCALIZATIONS_DELEGATES.search(content):
            findings.append(_mk(
                "missing_localizations_delegates",
                "Multiple locales configured but "
                "localizationsDelegates not set on MaterialApp.",
                Severity.BLOCKER, LocalizationLevel.SENIOR,
                rel, 0, "MaterialApp(...)",
                "Add `localizationsDelegates: AppLocalizations."
                "localizationsDelegates` (and Global delegates).",
                "Flutter i18n setup",
            ))

        # RTL locales declared but no Directionality / TextDirection
        # anywhere in lib?
        if _has_rtl_locale(locales) and not _project_uses_directionality(lib):
            findings.append(_mk(
                    "right_to_left_unsupported",
                    f"Project declares RTL locale(s) "
                    f"{[loc for loc in locales if loc in {'ar','he','fa','ur','yi','sd','ps'}]} "
                    "but no Directionality / TextDirection usage "
                    "detected.",
                    Severity.SERIOUS, LocalizationLevel.STAFF,
                    rel, 0, "MaterialApp",
                    "Audit layouts for RTL: use Directionality where "
                    "needed, prefer logical insets (startPadding, "
                    "endPadding) over left/right.",
                    "Flutter docs: Right-to-left",
                ))
        break  # one MaterialApp is enough

    return findings


def _has_rtl_locale(locales: set[str]) -> bool:
    return bool(locales & {"ar", "he", "fa", "ur", "yi", "sd", "ps"})


def _project_uses_directionality(lib: Path) -> bool:
    for f in lib.rglob("*.dart"):
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _RE_DIRECTIONALITY.search(content):
            return True
    return False


# ============================================================
# Helpers
# ============================================================


def _mk(
    rule: str, desc: str, severity: Severity,
    level: LocalizationLevel, file: str, line: int, snippet: str,
    fix_hint: str | None, standard: str | None,
) -> LocalizationFinding:
    return LocalizationFinding(
        rule=rule, description=desc, severity=severity, level=level,
        file=file, line=line, snippet=snippet[:140],
        fix_hint=fix_hint, standard=standard,
    )


def _grade_for(
    score: float, locales: set[str], n_keys: int, n_hardcoded: int,
) -> str:
    if not locales and n_hardcoded > 10:
        return "missing_l10n"
    if len(locales) <= 1:
        return "single_locale"
    if score >= 10 or n_hardcoded >= 50:
        return "single_locale"
    if score >= 3 or n_hardcoded >= 10:
        return "acceptable"
    return "well_localized"


def _build_top_actions(
    findings: tuple[LocalizationFinding, ...],
) -> tuple[str, ...]:
    if not findings:
        return ("No localization findings at the configured threshold.",)
    counts: dict[str, tuple[int, LocalizationFinding]] = {}
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
    grade: str, locales: set[str], n_hardcoded: int, n_unused: int,
) -> str:
    locales_str = ", ".join(sorted(locales)) if locales else "none"
    if grade == "missing_l10n":
        tail = "Add .arb files before shipping internationally."
    else:
        tail = "Wire hardcoded strings to .arb keys first; clean orphans last."
    return (
        f"i18n grade: {grade}. Locales detected: [{locales_str}]. "
        f"{n_hardcoded} hardcoded user-facing strings, "
        f"{n_unused} unused keys. {tail}"
    )

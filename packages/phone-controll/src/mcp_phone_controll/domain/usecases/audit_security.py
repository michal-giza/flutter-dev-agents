"""Security audit — OWASP Mobile Top 10 + MASVS scanner.

Catches the security smells most likely to ship to production
and break things later. Aligned to the OWASP Mobile Application
Security Verification Standard (MASVS) v2.0, scoped to what a
regex can credibly catch without an AST.

What it scans:

  • All .dart files under lib/ (excluding generated files)
  • android/app/build.gradle / build.gradle.kts
  • ios/Runner.xcodeproj/project.pbxproj (string-grep only)
  • pubspec.yaml (for security-sensitive packages)
  • .env / .env.* files at repo root (flagged if committed)
  • AndroidManifest.xml (cleartext traffic, exported components)
  • Info.plist (ATS exceptions)

What it catches (20 rules across 3 severities):

  **CRITICAL — blocker, never ship** (5 rules)
    • hardcoded_api_key       — AWS/GCP/Stripe/SendGrid/etc key
                                 patterns in source
    • hardcoded_jwt           — JWT token literal in source
    • hardcoded_pem           — PEM private key block in source
    • hardcoded_firebase_key  — Firebase web API key not behind
                                 env / not in google-services
    • committed_env_file      — .env / .env.production tracked
                                 (should be in .gitignore)

  **HIGH — fix this PR** (9 rules)
    • cleartext_http          — http:// URL in non-test source
    • prefs_for_secrets       — SharedPreferences storing a
                                 token/password/secret-shaped key
    • missing_secure_storage  — token-shaped variable stored
                                 without flutter_secure_storage
    • webview_js_unguarded    — JavaScript enabled on WebView
                                 without navigation delegate
    • cleartext_traffic_allow — usesCleartextTraffic="true" in
                                 AndroidManifest
    • ats_disabled            — NSAllowsArbitraryLoads = true in
                                 Info.plist
    • debug_signing_in_release — release buildType pointing at
                                 signingConfig.debug
    • exported_component      — Activity/Service exported=true
                                 without explicit permission
    • biometric_no_fallback   — local_auth used without
                                 biometricOnly + sticky_auth
                                 considerations

  **MEDIUM — cleanup** (6 rules)
    • missing_cert_pinning    — Dio/http client without pinning
                                 hint when calling auth endpoint
    • print_leaks_pii         — print() of token/email/password
                                 variable
    • debug_only_unguarded    — debug-only branch not behind
                                 kReleaseMode / kDebugMode
    • root_detection_missing  — no jailbreak/root check despite
                                 sensitive_data hint
    • screenshot_not_blocked  — FLAG_SECURE missing on screens
                                 hinted as sensitive
    • clipboard_for_secrets   — Clipboard.setData with a token-
                                 shaped variable

What this is NOT:

  • Not a SAST product. A real SAST tool runs taint analysis
    across function boundaries. This is regex over text.
  • Not a guarantee. False negatives are expected on dynamic
    string composition (e.g. building the key at runtime).
  • Not a certificate-validation checker. Cert pinning happens
    at runtime; we can only flag the absence of obvious pinning
    code paths in the HTTP client setup.
  • Not project-agnostic. Some rules (e.g. flutter_secure_storage
    expectation) encode Flutter ecosystem conventions. Teams on
    different stacks would tune the rule set.

Citations:

  OWASP MASVS v2.0 (Mobile Application Security Verification
  Standard) — MSTG-STORAGE, MSTG-CRYPTO, MSTG-NETWORK,
  MSTG-PLATFORM, MSTG-CODE, MSTG-RESILIENCE.
  https://mas.owasp.org/MASVS/
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
    CRITICAL = "critical"   # blocker — never ship
    HIGH = "high"           # serious — fix this PR
    MEDIUM = "medium"       # cleanup — nice to have


@dataclass(frozen=True, slots=True)
class SecurityFinding:
    rule: str
    description: str
    severity: Severity
    file: str
    line: int                # 1-indexed; 0 if file-level
    snippet: str             # redacted snippet — secrets masked
    fix_hint: str | None     # short paste-ready remediation
    standard: str            # MASVS or OWASP control reference


@dataclass(frozen=True, slots=True)
class AuditSecurityParams:
    project_path: Path
    # Paths to scan; default = the whole project. Pass
    # ["lib/features/auth"] to scope.
    paths: tuple[str, ...] = ()
    # Minimum severity to report. "medium" returns all.
    min_severity: str = "medium"
    # Maximum findings; bounded so the response stays small.
    max_findings: int = 200


@dataclass(frozen=True, slots=True)
class AuditSecurityResult:
    grade: str                              # secure / acceptable / at_risk / critical
    score: float                            # weighted findings per KLOC
    files_scanned: int
    lines_scanned: int
    findings: tuple[SecurityFinding, ...]
    findings_by_severity: dict[str, int]
    top_actions: tuple[str, ...]
    advice: str                             # one-line PR-comment summary


_SEVERITY_WEIGHT = {
    Severity.CRITICAL: 20,
    Severity.HIGH: 6,
    Severity.MEDIUM: 1,
}


class AuditSecurity(
    BaseUseCase[AuditSecurityParams, AuditSecurityResult]
):
    """Scans a Flutter project for OWASP MASVS-aligned security
    smells.

    Pure compute. No network, no device. Regex over text. Catches
    the 20 patterns most likely to leak secrets / weaken transport
    security / leave debug surfaces in production.
    """

    async def execute(
        self, params: AuditSecurityParams
    ) -> Result[AuditSecurityResult]:
        if not params.project_path.is_dir():
            return err(
                FilesystemFailure(
                    message=f"project_path not found: {params.project_path}",
                    next_action="fix_arguments",
                )
            )

        try:
            min_sev = Severity(params.min_severity)
        except ValueError:
            return err(
                FilesystemFailure(
                    message=(
                        f"unknown min_severity {params.min_severity!r}. "
                        "Valid: critical, high, medium"
                    ),
                    next_action="fix_arguments",
                )
            )

        files = _collect_files(params.project_path, params.paths)
        all_findings: list[SecurityFinding] = []
        lines_total = 0

        for f, kind in files:
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            lines = content.splitlines()
            lines_total += len(lines)
            rel = str(f.relative_to(params.project_path))
            all_findings.extend(
                _scan_file(rel, lines, content, kind)
            )

        # Repo-level checks
        all_findings.extend(_scan_repo_level(params.project_path))

        # Filter by min severity
        order = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM]
        kept = set(order[: order.index(min_sev) + 1])
        all_findings = [f for f in all_findings if f.severity in kept]

        # Sort by severity then file then line
        sev_idx = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2}
        all_findings.sort(
            key=lambda x: (sev_idx[x.severity], x.file, x.line)
        )
        all_findings_t = tuple(all_findings[: params.max_findings])

        by_sev: dict[str, int] = {}
        for fnd in all_findings_t:
            by_sev[fnd.severity.value] = by_sev.get(fnd.severity.value, 0) + 1

        weighted = sum(_SEVERITY_WEIGHT[f.severity] for f in all_findings_t)
        kloc = max(lines_total, 1) / 1000.0
        score = weighted / kloc if kloc > 0 else 0.0
        grade = _grade_for(score, by_sev, len(files))

        return ok(
            AuditSecurityResult(
                grade=grade,
                score=round(score, 2),
                files_scanned=len(files),
                lines_scanned=lines_total,
                findings=all_findings_t,
                findings_by_severity=by_sev,
                top_actions=_build_top_actions(all_findings_t),
                advice=_build_advice(
                    grade, score, len(all_findings_t),
                    len(files), lines_total,
                ),
            )
        )


# ============================================================
# File discovery
# ============================================================


def _collect_files(
    project: Path, paths: tuple[str, ...]
) -> list[tuple[Path, str]]:
    """Returns list of (file, kind) tuples.

    kind is one of: 'dart', 'gradle', 'manifest', 'plist',
    'pubspec', 'env'.
    """
    out: list[tuple[Path, str]] = []
    if paths:
        roots = [project / p for p in paths if (project / p).exists()]
    else:
        roots = [project]
    for root in roots:
        if not root.exists():
            continue
        if root.is_file():
            kind = _kind_for(root)
            if kind:
                out.append((root, kind))
            continue
        for f in root.rglob("*"):
            if not f.is_file():
                continue
            # Skip build/, .claude/worktrees/, .dart_tool/, etc.
            # (v0.3.0 field-test calibration finding)
            if is_path_excluded(f, project):
                continue
            kind = _kind_for(f)
            if not kind:
                continue
            # Skip generated dart
            if kind == "dart":
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
                # Skip test files for the security scan; their
                # hardcoded fixtures are intentional.
                if "/test/" in str(f) or str(f).endswith("_test.dart"):
                    continue
            out.append((f, kind))
    return sorted(out, key=lambda x: str(x[0]))


def _kind_for(f: Path) -> str | None:
    name = f.name.lower()
    suffix = f.suffix.lower()
    if suffix == ".dart":
        return "dart"
    if name == "androidmanifest.xml":
        return "manifest"
    if name == "info.plist":
        return "plist"
    if name == "pubspec.yaml":
        return "pubspec"
    if name.startswith(".env"):
        return "env"
    if suffix in (".gradle", ".kts") and "build" in name:
        return "gradle"
    return None


# ============================================================
# Per-file scanner
# ============================================================


# Compiled patterns
# AWS-style: AKIA + 16 uppercase chars
_RE_AWS_KEY = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
# Google API key: AIza + 35 chars
_RE_GOOGLE_KEY = re.compile(r"\bAIza[0-9A-Za-z\-_]{35,}")
# Stripe live key
_RE_STRIPE = re.compile(r"\bsk_live_[0-9a-zA-Z]{24,}\b")
# SendGrid
_RE_SENDGRID = re.compile(r"\bSG\.[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,}\b")
# Slack token
_RE_SLACK = re.compile(r"\bxox[abps]-[0-9A-Za-z\-]{10,}\b")
# Generic JWT (3-part base64)
_RE_JWT = re.compile(
    r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"
)
# PEM private key block
_RE_PEM = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"
)
# Cleartext http URL (excluding localhost / 10.0.2.2 emulator host)
_RE_HTTP = re.compile(
    r"['\"]http://(?!localhost|127\.0\.0\.1|10\.0\.2\.2|0\.0\.0\.0)"
)
# SharedPreferences usage
_RE_PREFS_WRITE = re.compile(
    r"\.set(?:String|Bool|Int|Double)\s*\(\s*['\"]([^'\"]+)['\"]"
)
# Sensitive-looking key names
_RE_SENSITIVE_KEY_NAME = re.compile(
    r"(?i)(token|password|secret|api[_-]?key|bearer|refresh[_-]?token|jwt|session)"
)
# WebView javascriptMode
_RE_WEBVIEW_JS = re.compile(
    r"javaScriptMode\s*:\s*JavaScriptMode\.unrestricted|"
    r"javascriptMode\s*:\s*JavascriptMode\.unrestricted|"
    r"setJavaScriptMode\s*\(\s*JavaScriptMode\.unrestricted\s*\)"
)
_RE_NAV_DELEGATE = re.compile(
    r"setNavigationDelegate|NavigationDelegate\s*\("
)
# print() with sensitive variable
_RE_PRINT_SENS = re.compile(
    r"\bprint\s*\([^)]*\b(token|password|secret|api[_-]?key|email|jwt|bearer)\b",
    re.IGNORECASE,
)
# Clipboard with secret-shaped variable
_RE_CLIPBOARD = re.compile(
    r"Clipboard\.setData\s*\([^)]*\b(token|password|secret|jwt|bearer)\b",
    re.IGNORECASE,
)
# debug only branch not behind kReleaseMode/kDebugMode
_RE_DEBUG_BRANCH = re.compile(
    r"//\s*(?:debug only|DEBUG ONLY|debug-only|DEBUG-ONLY|FOR DEBUG)"
)
_RE_KMODE = re.compile(r"\bkReleaseMode\b|\bkDebugMode\b|\bkProfileMode\b")
# Local auth without biometricOnly hint
_RE_LOCAL_AUTH = re.compile(r"LocalAuthentication\s*\(")
_RE_BIOMETRIC_ONLY = re.compile(r"biometricOnly\s*:\s*true")
# Android manifest patterns
_RE_CLEARTEXT_ALLOW = re.compile(
    r'usesCleartextTraffic\s*=\s*"true"'
)
_RE_EXPORTED_TRUE = re.compile(
    r'android:exported\s*=\s*"true"(?![^>]*permission)'
)
# iOS ATS arbitrary loads
_RE_ATS = re.compile(
    r"NSAllowsArbitraryLoads(?:\s*</key>\s*<true/>|.*?true)",
    re.DOTALL,
)
# Gradle debug signing in release
_RE_DEBUG_SIGN = re.compile(
    r"release\s*\{[^}]*signingConfig\s+signingConfigs\.debug",
    re.DOTALL,
)
# Dio interceptor without pinning
_RE_DIO_NEW = re.compile(r"\b(Dio|http\.Client)\s*\(\s*\)")
_RE_PINNING_HINT = re.compile(
    r"BadCertificateCallback|setTrustedCertificates|"
    r"SecurityContext\(|certificate_pinning|"
    r"http_certificate_pinning"
)


def _scan_file(
    rel: str,
    lines: list[str],
    content: str,
    kind: str,
) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []

    if kind == "dart":
        findings.extend(_scan_dart(rel, lines, content))
    elif kind == "manifest":
        findings.extend(_scan_manifest(rel, lines, content))
    elif kind == "plist":
        findings.extend(_scan_plist(rel, lines, content))
    elif kind == "gradle":
        findings.extend(_scan_gradle(rel, lines, content))
    elif kind == "env":
        # The committed_env_file check is repo-level (_scan_repo_level)
        # but if we're scanning this file directly, also flag secrets
        # inside it.
        findings.extend(_scan_env_contents(rel, lines))
    return findings


def _scan_dart(
    rel: str, lines: list[str], content: str,
) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    has_kmode_guard = bool(_RE_KMODE.search(content))

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()

        # ---- CRITICAL ----
        if m := _RE_AWS_KEY.search(line):
            findings.append(_mk(
                "hardcoded_api_key",
                "AWS access-key ID literal in source. Rotate immediately + use env var.",
                Severity.CRITICAL, rel, i, _redact(stripped, m.group(0)),
                "Move to --dart-define or a secret manager; rotate the leaked key.",
                "OWASP MASVS-CRYPTO-1 / MSTG-CRYPTO-1",
            ))
        if m := _RE_GOOGLE_KEY.search(line):
            # Firebase web API keys are designed to be public
            # (security depends on Firestore rules, not key
            # secrecy). The flutterfire-generated
            # `firebase_options.dart` file is the canonical
            # place for them — flagging inside that file is a
            # false positive (we'd just be telling the user to
            # do what they already did). Skip when the host
            # file IS firebase_options.dart AND the surrounding
            # context is a FirebaseOptions(...) constructor.
            #
            # Surfaced by v0.3.0 field test on mytaskboardapp —
            # see docs/v030-field-test.md.
            is_firebase_options = rel.endswith("firebase_options.dart")
            uses_firebase_options_ctor = "FirebaseOptions(" in content
            if not (is_firebase_options and uses_firebase_options_ctor):
                findings.append(_mk(
                    "hardcoded_firebase_key",
                    "Google/Firebase API key literal outside "
                    "firebase_options.dart. Use FirebaseOptions."
                    "currentPlatform from firebase_options.dart.",
                    Severity.CRITICAL, rel, i, _redact(stripped, m.group(0)),
                    "flutterfire configure → generate firebase_options.dart; remove the inline key.",
                    "Firebase docs: prefer firebase_options over hardcoded keys",
                ))
        for pat in (_RE_STRIPE, _RE_SENDGRID, _RE_SLACK):
            m = pat.search(line)
            if m:
                findings.append(_mk(
                    "hardcoded_api_key",
                    f"Third-party API key literal in source ({pat.pattern.split(chr(92))[0][:12]}...).",
                    Severity.CRITICAL, rel, i, _redact(stripped, m.group(0)),
                    "Move to env / secret manager; rotate the leaked key.",
                    "OWASP MASVS-CRYPTO-1",
                ))
        if m := _RE_JWT.search(line):
            findings.append(_mk(
                "hardcoded_jwt",
                "JWT literal in source. Tokens belong in secure storage, not source.",
                Severity.CRITICAL, rel, i, _redact(stripped, m.group(0)),
                "Fetch token at runtime; store via flutter_secure_storage.",
                "OWASP MASVS-AUTH-1",
            ))
        if _RE_PEM.search(line):
            findings.append(_mk(
                "hardcoded_pem",
                "PEM private key block in source. Never ship private keys in app code.",
                Severity.CRITICAL, rel, i, "-----BEGIN [REDACTED] PRIVATE KEY-----",
                "Move to a hardware-backed keystore (Android Keystore / iOS Keychain).",
                "OWASP MASVS-CRYPTO-1 / MSTG-CRYPTO-1",
            ))

        # ---- HIGH ----
        if (
            _RE_HTTP.search(line)
            and not rel.startswith("test/")
            and "// allow-http" not in line
        ):
            findings.append(_mk(
                "cleartext_http",
                "Cleartext http:// URL in production code. Use https:// or document the exception.",
                Severity.HIGH, rel, i, stripped[:140],
                "Swap to https://; if a local dev backend, add `// allow-http`.",
                "OWASP MASVS-NETWORK-1",
            ))
        if _RE_WEBVIEW_JS.search(line) and not _RE_NAV_DELEGATE.search(content):
            findings.append(_mk(
                "webview_js_unguarded",
                "WebView with JavaScript unrestricted but no NavigationDelegate to gate URLs.",
                Severity.HIGH, rel, i, stripped[:140],
                "Set a NavigationDelegate that allow-lists trusted hosts before loadRequest.",
                "OWASP MASVS-PLATFORM-2",
            ))
        if m := _RE_PREFS_WRITE.search(line):
            key_name = m.group(1)
            if _RE_SENSITIVE_KEY_NAME.search(key_name):
                findings.append(_mk(
                    "prefs_for_secrets",
                    f"SharedPreferences key {key_name!r} looks sensitive — use flutter_secure_storage.",
                    Severity.HIGH, rel, i, stripped[:140],
                    "Swap to FlutterSecureStorage().write(key: ..., value: ...).",
                    "OWASP MASVS-STORAGE-1",
                ))

        # ---- MEDIUM ----
        if _RE_PRINT_SENS.search(line):
            findings.append(_mk(
                "print_leaks_pii",
                "print() of a sensitive-looking variable. PII leaks via logcat.",
                Severity.MEDIUM, rel, i, stripped[:140],
                "Mask the value or remove the print entirely.",
                "OWASP MASVS-CODE-4",
            ))
        if _RE_CLIPBOARD.search(line):
            findings.append(_mk(
                "clipboard_for_secrets",
                "Clipboard.setData with a sensitive-looking value. Clipboard is world-readable.",
                Severity.MEDIUM, rel, i, stripped[:140],
                "Avoid clipboard for secrets; if unavoidable, schedule a clear after timeout.",
                "OWASP MASVS-STORAGE-2",
            ))
        if _RE_DEBUG_BRANCH.search(line) and not has_kmode_guard:
            findings.append(_mk(
                "debug_only_unguarded",
                "Debug-only branch comment present but no kDebugMode/kReleaseMode guard in file.",
                Severity.MEDIUM, rel, i, stripped[:140],
                "Wrap with `if (kReleaseMode) return;` or `if (kDebugMode) { ... }`.",
                "OWASP MASVS-RESILIENCE-3",
            ))

    # ---- File-level ----
    # missing_cert_pinning: Dio/http instantiated AND auth-shaped
    # endpoints used AND no pinning hint anywhere.
    if (
        _RE_DIO_NEW.search(content)
        and re.search(r"(?i)(/auth|/login|/token|/oauth)", content)
        and not _RE_PINNING_HINT.search(content)
    ):
        line_no = content.count("\n", 0, _RE_DIO_NEW.search(content).start()) + 1
        findings.append(_mk(
            "missing_cert_pinning",
            "HTTP client used for auth endpoints without certificate-pinning setup.",
            Severity.MEDIUM, rel, line_no, "Dio() or http.Client()",
            "Add http_certificate_pinning or configure BadCertificateCallback.",
            "OWASP MASVS-NETWORK-2",
        ))

    # biometric_no_fallback
    if _RE_LOCAL_AUTH.search(content) and not _RE_BIOMETRIC_ONLY.search(content):
        m = _RE_LOCAL_AUTH.search(content)
        assert m is not None
        line_no = content.count("\n", 0, m.start()) + 1
        findings.append(_mk(
            "biometric_no_fallback",
            "LocalAuthentication used without biometricOnly:true — falls back to device PIN.",
            Severity.MEDIUM, rel, line_no, m.group(0),
            "Pass `biometricOnly: true` if PIN fallback is not acceptable.",
            "OWASP MASVS-AUTH-2",
        ))

    return findings


def _scan_manifest(
    rel: str, lines: list[str], content: str,
) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    for i, line in enumerate(lines, start=1):
        if _RE_CLEARTEXT_ALLOW.search(line):
            findings.append(_mk(
                "cleartext_traffic_allow",
                "AndroidManifest enables usesCleartextTraffic. All HTTP allowed.",
                Severity.HIGH, rel, i, line.strip()[:140],
                "Remove usesCleartextTraffic or scope via networkSecurityConfig per-domain.",
                "OWASP MASVS-NETWORK-1",
            ))
        if _RE_EXPORTED_TRUE.search(line):
            findings.append(_mk(
                "exported_component",
                "Android component exported=true without permission attribute.",
                Severity.HIGH, rel, i, line.strip()[:140],
                "Require an explicit android:permission, or set exported=false.",
                "OWASP MASVS-PLATFORM-1",
            ))
    return findings


def _scan_plist(
    rel: str, lines: list[str], content: str,
) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    if _RE_ATS.search(content):
        m = _RE_ATS.search(content)
        assert m is not None
        line_no = content.count("\n", 0, m.start()) + 1
        findings.append(_mk(
            "ats_disabled",
            "Info.plist sets NSAllowsArbitraryLoads=true. ATS is fully disabled.",
            Severity.HIGH, rel, line_no, "NSAllowsArbitraryLoads <true/>",
            "Remove NSAllowsArbitraryLoads or use NSExceptionDomains per-host.",
            "Apple ATS / OWASP MASVS-NETWORK-1",
        ))
    return findings


def _scan_gradle(
    rel: str, lines: list[str], content: str,
) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    if _RE_DEBUG_SIGN.search(content):
        m = _RE_DEBUG_SIGN.search(content)
        assert m is not None
        line_no = content.count("\n", 0, m.start()) + 1
        findings.append(_mk(
            "debug_signing_in_release",
            "Release buildType signs with signingConfigs.debug — release builds are debug-signed.",
            Severity.HIGH, rel, line_no, "signingConfig signingConfigs.debug",
            "Create a release signing config; never reuse the debug keystore in production.",
            "OWASP MASVS-RESILIENCE-1",
        ))
    return findings


def _scan_env_contents(
    rel: str, lines: list[str],
) -> list[SecurityFinding]:
    """If a .env file is being scanned, flag the kinds of keys
    that should not be in any .env that could end up committed."""
    findings: list[SecurityFinding] = []
    for i, line in enumerate(lines, start=1):
        for pat, rule, desc in (
            (_RE_AWS_KEY, "hardcoded_api_key", "AWS key in .env"),
            (_RE_STRIPE, "hardcoded_api_key", "Stripe key in .env"),
            (_RE_PEM, "hardcoded_pem", "PEM key in .env"),
        ):
            m = pat.search(line)
            if m:
                findings.append(_mk(
                    rule, f"{desc} — ensure this file is in .gitignore.",
                    Severity.CRITICAL, rel, i,
                    _redact(line.strip(), m.group(0)),
                    "Add to .gitignore; rotate if ever committed.",
                    "OWASP MASVS-CRYPTO-1",
                ))
    return findings


# ============================================================
# Repo-level checks
# ============================================================


def _scan_repo_level(project: Path) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    # committed_env_file: any .env* at repo root that's NOT in
    # .gitignore is a CRITICAL finding even if its contents are
    # boring — the presence is the smell.
    gitignore = (project / ".gitignore")
    gitignore_text = (
        gitignore.read_text(encoding="utf-8", errors="replace")
        if gitignore.is_file() else ""
    )
    for env_file in project.glob(".env*"):
        if not env_file.is_file():
            continue
        # Check if gitignore explicitly ignores it
        ignored = (
            ".env" in gitignore_text
            or env_file.name in gitignore_text
        )
        if not ignored:
            findings.append(_mk(
                "committed_env_file",
                f"{env_file.name} present at repo root and not in .gitignore.",
                Severity.CRITICAL, env_file.name, 0, env_file.name,
                f"Add `.env*` to .gitignore; rotate any keys inside {env_file.name}.",
                "OWASP MASVS-STORAGE-1",
            ))
    return findings


# ============================================================
# Helpers
# ============================================================


def _redact(line: str, secret: str) -> str:
    if not secret or len(secret) < 6:
        return line[:140]
    masked = secret[:4] + "*" * (len(secret) - 8) + secret[-4:]
    return line.replace(secret, masked)[:140]


def _mk(
    rule: str, desc: str, severity: Severity, file: str, line: int,
    snippet: str, fix_hint: str | None, standard: str,
) -> SecurityFinding:
    return SecurityFinding(
        rule=rule, description=desc, severity=severity,
        file=file, line=line, snippet=snippet[:140],
        fix_hint=fix_hint, standard=standard,
    )


def _grade_for(
    score: float, by_sev: dict[str, int], files_scanned: int,
) -> str:
    if files_scanned == 0:
        return "secure"
    if by_sev.get("critical", 0) > 0:
        return "critical"
    if by_sev.get("high", 0) >= 5 or score >= 15:
        return "at_risk"
    if by_sev.get("high", 0) > 0 or score >= 3:
        return "acceptable"
    return "secure"


def _build_top_actions(
    findings: tuple[SecurityFinding, ...],
) -> tuple[str, ...]:
    if not findings:
        return ("No security findings at the configured threshold.",)
    counts: dict[str, tuple[int, SecurityFinding]] = {}
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
    grade: str, score: float, n_findings: int,
    files: int, lines: int,
) -> str:
    return (
        f"Security grade: {grade} ({score:.1f} weighted findings/KLOC). "
        f"{n_findings} findings across {files} files / {lines} LOC. "
        + (
            "STOP — fix all critical before merge."
            if grade == "critical"
            else "Fix highs this PR, mediums next cleanup."
        )
    )

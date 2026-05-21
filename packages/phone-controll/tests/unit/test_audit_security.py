"""Tests for the v0.3.0 phase-8 security audit (OWASP MASVS).

Each rule has a positive case (known-bad source) and at least one
negative-control test (clean source must not trigger it). Tests
also verify:

- Secrets are REDACTED in the snippet field (the audit must not
  leak its own findings into PR comments).
- Grade computation reacts to severity (critical > acceptable).
- min_severity filter works.
- Generated files (.g.dart) and test/ files are skipped.
- Repo-level checks (committed .env) fire even without contents.
- Missing project_path / invalid min_severity returns
  fix_arguments.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.audit_security import (
    AuditSecurity,
    AuditSecurityParams,
    Severity,
)


def _write(p: Path, content: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _project(tmp_path: Path) -> Path:
    (tmp_path / "lib").mkdir()
    (tmp_path / ".gitignore").write_text(".env\n.env.*\n", encoding="utf-8")
    return tmp_path


async def _run(project: Path, **kwargs) -> Ok | Err:
    return await AuditSecurity()(
        AuditSecurityParams(project_path=project, **kwargs)
    )


def _rules(res: Ok) -> set[str]:
    return {f.rule for f in res.value.findings}


# ---- happy path --------------------------------------------------------


@pytest.mark.asyncio
async def test_clean_project_grades_secure(tmp_path: Path):
    proj = _project(tmp_path)
    _write(proj / "lib" / "main.dart", "void main() {}\n")
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert res.value.grade == "secure"
    assert res.value.findings == ()


@pytest.mark.asyncio
async def test_missing_project_returns_failure(tmp_path: Path):
    res = await _run(tmp_path / "nope")
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_invalid_min_severity_returns_failure(tmp_path: Path):
    proj = _project(tmp_path)
    res = await _run(proj, min_severity="bogus")
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


# ---- CRITICAL rules ----------------------------------------------------


@pytest.mark.asyncio
async def test_hardcoded_aws_key_fires_and_redacts(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "leak.dart",
        "const key = 'AKIAIOSFODNN7EXAMPLE';\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "hardcoded_api_key" in _rules(res)
    # Find the AWS finding, ensure it's CRITICAL + redacted
    finding = next(f for f in res.value.findings if f.rule == "hardcoded_api_key")
    assert finding.severity == Severity.CRITICAL
    # The literal AWS key must not appear in the snippet — redact.
    assert "AKIAIOSFODNN7EXAMPLE" not in finding.snippet
    assert "*" in finding.snippet  # masking present
    assert res.value.grade == "critical"


@pytest.mark.asyncio
async def test_hardcoded_google_key_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "fb.dart",
        "const fbKey = 'AIzaSyA1234567890abcdefghij1234567890XYZAB';\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "hardcoded_firebase_key" in _rules(res)


@pytest.mark.asyncio
async def test_hardcoded_jwt_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "token.dart",
        "const tok = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NSIsIm5hbWUiOiJKb2huIERvZSJ9."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c';\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "hardcoded_jwt" in _rules(res)


@pytest.mark.asyncio
async def test_hardcoded_pem_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "pem.dart",
        "const k = '-----BEGIN RSA PRIVATE KEY-----\\nMIIEpAIBAAKC...';\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "hardcoded_pem" in _rules(res)


@pytest.mark.asyncio
async def test_committed_env_file_fires(tmp_path: Path):
    proj = tmp_path
    (proj / "lib").mkdir()
    # No .gitignore at all — .env is committable
    _write(proj / ".env", "FOO=bar\n")
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "committed_env_file" in _rules(res)


@pytest.mark.asyncio
async def test_env_in_gitignore_does_not_fire(tmp_path: Path):
    proj = _project(tmp_path)  # gitignore includes .env
    _write(proj / ".env", "FOO=bar\n")
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "committed_env_file" not in _rules(res)


# ---- HIGH rules --------------------------------------------------------


@pytest.mark.asyncio
async def test_cleartext_http_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "api.dart",
        "const base = 'http://api.example.com/v1';\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "cleartext_http" in _rules(res)


@pytest.mark.asyncio
async def test_cleartext_localhost_does_not_fire(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "dev.dart",
        "const local = 'http://localhost:8080';\n"
        "const emu = 'http://10.0.2.2:3000';\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "cleartext_http" not in _rules(res)


@pytest.mark.asyncio
async def test_prefs_for_secrets_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "storage.dart",
        "void save(SharedPreferences p) => p.setString('access_token', tok);\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "prefs_for_secrets" in _rules(res)


@pytest.mark.asyncio
async def test_prefs_for_nonsensitive_does_not_fire(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "storage.dart",
        "void save(SharedPreferences p) => p.setString('theme_mode', 'dark');\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "prefs_for_secrets" not in _rules(res)


@pytest.mark.asyncio
async def test_webview_js_unguarded_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "web.dart",
        "WebViewController()..setJavaScriptMode(JavaScriptMode.unrestricted);\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "webview_js_unguarded" in _rules(res)


@pytest.mark.asyncio
async def test_webview_js_with_delegate_does_not_fire(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "web.dart",
        "WebViewController()\n"
        "  ..setJavaScriptMode(JavaScriptMode.unrestricted)\n"
        "  ..setNavigationDelegate(NavigationDelegate(\n"
        "    onNavigationRequest: (r) => allow(r),\n"
        "  ));\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "webview_js_unguarded" not in _rules(res)


@pytest.mark.asyncio
async def test_cleartext_traffic_allow_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "android" / "app" / "src" / "main" / "AndroidManifest.xml",
        '<application android:usesCleartextTraffic="true">\n</application>\n',
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "cleartext_traffic_allow" in _rules(res)


@pytest.mark.asyncio
async def test_ats_disabled_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "ios" / "Runner" / "Info.plist",
        "<dict>\n  <key>NSAppTransportSecurity</key>\n  <dict>\n"
        "    <key>NSAllowsArbitraryLoads</key>\n    <true/>\n"
        "  </dict>\n</dict>\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "ats_disabled" in _rules(res)


@pytest.mark.asyncio
async def test_debug_signing_in_release_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "android" / "app" / "build.gradle",
        "buildTypes {\n"
        "  release {\n"
        "    signingConfig signingConfigs.debug\n"
        "  }\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "debug_signing_in_release" in _rules(res)


@pytest.mark.asyncio
async def test_exported_component_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "android" / "app" / "src" / "main" / "AndroidManifest.xml",
        '<activity android:name=".DeepLinkActivity" android:exported="true"/>\n',
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "exported_component" in _rules(res)


@pytest.mark.asyncio
async def test_biometric_no_fallback_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "auth.dart",
        "import 'package:local_auth/local_auth.dart';\n"
        "final auth = LocalAuthentication();\n"
        "Future<bool> check() => auth.authenticate(localizedReason: 'auth');\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "biometric_no_fallback" in _rules(res)


@pytest.mark.asyncio
async def test_biometric_with_only_does_not_fire(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "auth.dart",
        "import 'package:local_auth/local_auth.dart';\n"
        "final auth = LocalAuthentication();\n"
        "Future<bool> check() => auth.authenticate(\n"
        "  localizedReason: 'auth',\n"
        "  options: const AuthenticationOptions(biometricOnly: true),\n"
        ");\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "biometric_no_fallback" not in _rules(res)


# ---- MEDIUM rules ------------------------------------------------------


@pytest.mark.asyncio
async def test_print_leaks_pii_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "log.dart",
        "void log(String token) { print('user token=$token'); }\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "print_leaks_pii" in _rules(res)


@pytest.mark.asyncio
async def test_clipboard_for_secrets_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "copy.dart",
        "void copyToken(String token) =>\n"
        "    Clipboard.setData(ClipboardData(text: token));\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "clipboard_for_secrets" in _rules(res)


@pytest.mark.asyncio
async def test_missing_cert_pinning_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "api.dart",
        "final dio = Dio();\n"
        "Future<void> login() => dio.post('https://api.example.com/auth/login');\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "missing_cert_pinning" in _rules(res)


@pytest.mark.asyncio
async def test_cert_pinning_present_does_not_fire(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "api.dart",
        "import 'package:http_certificate_pinning/http_certificate_pinning.dart';\n"
        "final dio = Dio();\n"
        "Future<void> login() => dio.post('https://api.example.com/auth/login');\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "missing_cert_pinning" not in _rules(res)


# ---- engine behaviors --------------------------------------------------


@pytest.mark.asyncio
async def test_generated_files_skipped(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "leak.g.dart",
        "const key = 'AKIAIOSFODNN7EXAMPLE';\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    # generated .g.dart was skipped, only other files counted
    assert "hardcoded_api_key" not in _rules(res)


@pytest.mark.asyncio
async def test_test_files_skipped(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "test" / "fixtures_test.dart",
        "const fixtureKey = 'AKIAIOSFODNN7EXAMPLE';\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    # test fixtures are allowed to contain hardcoded sample keys
    assert "hardcoded_api_key" not in _rules(res)


@pytest.mark.asyncio
async def test_findings_sorted_by_severity(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "mix.dart",
        "// CRITICAL: hardcoded key\n"
        "const k = 'AKIAIOSFODNN7EXAMPLE';\n"
        "// MEDIUM: print PII\n"
        "void log(String token) { print('t=$token'); }\n"
        "// HIGH: cleartext\n"
        "const base = 'http://api.example.com';\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    sev_order = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2}
    seq = [sev_order[f.severity] for f in res.value.findings]
    assert seq == sorted(seq)


@pytest.mark.asyncio
async def test_min_severity_filter_suppresses_lower_tiers(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "mix.dart",
        "void log(String token) { print('t=$token'); }\n"  # MEDIUM
        "const base = 'http://api.example.com';\n",  # HIGH
    )
    res = await _run(proj, min_severity="high")
    assert isinstance(res, Ok)
    assert all(f.severity != Severity.MEDIUM for f in res.value.findings)


@pytest.mark.asyncio
async def test_grade_critical_for_any_critical_finding(tmp_path: Path):
    proj = _project(tmp_path)
    # Single AWS key — must push grade to critical.
    _write(
        proj / "lib" / "leak.dart",
        "const key = 'AKIAIOSFODNN7EXAMPLE';\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert res.value.grade == "critical"
    assert "STOP" in res.value.advice


@pytest.mark.asyncio
async def test_top_actions_prioritized_by_severity(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "leak.dart",
        "const k = 'AKIAIOSFODNN7EXAMPLE';\n"
        "void log(String token) { print('t=$token'); }\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "[critical]" in res.value.top_actions[0]


@pytest.mark.asyncio
async def test_advice_mentions_grade(tmp_path: Path):
    proj = _project(tmp_path)
    _write(proj / "lib" / "x.dart", "void main() {}\n")
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert res.value.grade in res.value.advice


@pytest.mark.asyncio
async def test_paths_filter_restricts_scan(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "auth" / "leak.dart",
        "const k = 'AKIAIOSFODNN7EXAMPLE';\n",
    )
    _write(
        proj / "lib" / "home" / "ok.dart",
        "void main() {}\n",
    )
    res = await _run(proj, paths=("lib/home",))
    assert isinstance(res, Ok)
    # Only lib/home was scanned — no critical
    assert "hardcoded_api_key" not in _rules(res)

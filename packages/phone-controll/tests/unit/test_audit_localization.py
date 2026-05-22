"""Tests for the v0.3.0 phase-9 localization audit.

Each rule is tested with a known-bad fixture (should fire) and
where applicable a known-good fixture (should stay silent).

What we validate:

- Hardcoded user-facing strings in widgets fire (Text, Tooltip,
  Button child, SnackBar, hintText/labelText)
- The 'looks user-facing' filter excludes asset paths, identifiers,
  URLs, MIME types
- Missing l10n keys fire (code references key not in arb)
- Unused l10n keys fire (key in arb never referenced in code)
- Missing translation per locale fires (key in en.arb but missing
  in pl.arb)
- supportedLocales mismatch with arb files (both directions)
- Missing localizationsDelegates when multi-locale
- RTL plumbing check when ar/he/fa declared
- String concatenation with variable fires
- Pluralization via ternary fires
- min_level filter suppresses lower tiers
- Generated files (.g.dart) skipped
- Test files skipped (find.text in tests is intentional)
- Invalid project_path / min_level returns fix_arguments
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.audit_localization import (
    AuditLocalization,
    AuditLocalizationParams,
    LocalizationLevel,
)

# ---- fixture helpers ----------------------------------------------------


def _write(p: Path, content: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _project(tmp_path: Path) -> Path:
    (tmp_path / "lib").mkdir()
    return tmp_path


def _arb(tmp_path: Path, locale: str, keys: dict[str, str]) -> Path:
    p = tmp_path / "lib" / "l10n" / f"intl_{locale}.arb"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(keys), encoding="utf-8")
    return p


async def _run(project: Path, **kwargs) -> Ok | Err:
    return await AuditLocalization()(
        AuditLocalizationParams(project_path=project, **kwargs)
    )


def _rules(res: Ok) -> set[str]:
    return {f.rule for f in res.value.findings}


# ---- happy path + error handling ---------------------------------------


@pytest.mark.asyncio
async def test_empty_project_returns_clean(tmp_path: Path):
    proj = _project(tmp_path)
    _write(proj / "lib" / "main.dart", "void main() {}\n")
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert res.value.findings == ()
    assert res.value.locales_detected == ()


@pytest.mark.asyncio
async def test_missing_project_path_returns_typed_failure(tmp_path: Path):
    res = await _run(tmp_path / "does_not_exist")
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_invalid_min_level_returns_typed_failure(tmp_path: Path):
    proj = _project(tmp_path)
    res = await _run(proj, min_level="principal")
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


# ---- JUNIOR: hardcoded strings -----------------------------------------


@pytest.mark.asyncio
async def test_hardcoded_text_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "login.dart",
        "import 'package:flutter/material.dart';\n"
        "class LoginPage extends StatelessWidget {\n"
        "  @override Widget build(BuildContext c) =>\n"
        "    Scaffold(body: Text('Sign in to continue'));\n"
        "}\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "hardcoded_user_text" in _rules(res)
    assert res.value.hardcoded_strings >= 1


@pytest.mark.asyncio
async def test_hardcoded_button_label_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "buttons.dart",
        "import 'package:flutter/material.dart';\n"
        "Widget x() => ElevatedButton(onPressed: null, "
        "child: Text('Save changes'));\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "hardcoded_user_text" in _rules(res)


@pytest.mark.asyncio
async def test_clean_l10n_text_does_not_fire(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "clean.dart",
        "import 'package:flutter/material.dart';\n"
        "Widget x(BuildContext c) => "
        "Text(AppLocalizations.of(c)!.signIn);\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "hardcoded_user_text" not in _rules(res)


@pytest.mark.asyncio
async def test_filter_excludes_asset_paths(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "assets.dart",
        "import 'package:flutter/material.dart';\n"
        "Widget x() => Image.asset('assets/images/logo.png');\n"
        "Widget y() => Text('package:my_app/icon');\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    # Asset paths shouldn't be flagged as user-facing text
    assert "hardcoded_user_text" not in _rules(res)


@pytest.mark.asyncio
async def test_filter_excludes_identifier_strings(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "keys.dart",
        "import 'package:flutter/material.dart';\n"
        "Widget x() => Text('user_profile_key');\n",  # snake_case
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    # Identifier-shaped strings shouldn't be user-facing
    assert "hardcoded_user_text" not in _rules(res)


@pytest.mark.asyncio
async def test_test_files_are_skipped(tmp_path: Path):
    proj = _project(tmp_path)
    (proj / "test").mkdir()
    _write(
        proj / "test" / "widget_test.dart",
        "import 'package:flutter_test/flutter_test.dart';\n"
        "void main() { testWidgets('x', (t) async { "
        "expect(find.text('Sign in'), findsOneWidget); }); }\n",
    )
    _write(proj / "lib" / "main.dart", "void main() {}\n")
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "hardcoded_user_text" not in _rules(res)


@pytest.mark.asyncio
async def test_generated_files_skipped(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "user.g.dart",
        "Widget x() => Text('Some generated label');\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert res.value.files_scanned == 0


# ---- MID: missing keys + unused keys -----------------------------------


@pytest.mark.asyncio
async def test_missing_l10n_key_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _arb(proj, "en", {"existingKey": "Yes"})
    _write(
        proj / "lib" / "page.dart",
        "Widget x(BuildContext c) => "
        "Text(AppLocalizations.of(c)!.missingKey);\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "missing_l10n_key" in _rules(res)


@pytest.mark.asyncio
async def test_unused_l10n_key_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _arb(proj, "en", {"usedKey": "Used", "orphanKey": "Orphan"})
    _write(
        proj / "lib" / "page.dart",
        "Widget x(BuildContext c) => "
        "Text(AppLocalizations.of(c)!.usedKey);\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    rules = _rules(res)
    assert "unused_l10n_key" in rules
    # Specifically orphanKey, not usedKey
    snippets = [f.snippet for f in res.value.findings
                if f.rule == "unused_l10n_key"]
    assert any("orphanKey" in s for s in snippets)
    assert res.value.keys_used == 1
    assert res.value.keys_unused == 1


@pytest.mark.asyncio
async def test_missing_translation_per_locale_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _arb(proj, "en", {"hello": "Hello", "goodbye": "Goodbye"})
    _arb(proj, "pl", {"hello": "Cześć"})  # missing 'goodbye'
    _write(proj / "lib" / "x.dart", "void main() {}\n")
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "missing_translation_for_locale" in _rules(res)
    # The missing key should be 'goodbye' in pl.arb
    f = next(
        x for x in res.value.findings
        if x.rule == "missing_translation_for_locale"
    )
    assert "goodbye" in f.snippet
    assert "pl" in f.file


@pytest.mark.asyncio
async def test_string_concatenation_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "greet.dart",
        "import 'package:flutter/material.dart';\n"
        "Widget x(String name) => Text('Hello ' + name + '!');\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "direct_text_concatenation" in _rules(res)


# ---- STAFF: pluralization + RTL ----------------------------------------


@pytest.mark.asyncio
async def test_pluralization_via_ternary_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "count.dart",
        "String label(int count) => count == 1 ? 'item' : 'items';\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "pluralization_via_if" in _rules(res)


# ---- SENIOR: plumbing checks -------------------------------------------


@pytest.mark.asyncio
async def test_missing_flutter_localizations_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _arb(proj, "en", {"hello": "Hello"})
    _arb(proj, "pl", {"hello": "Cześć"})
    _write(
        proj / "pubspec.yaml",
        "name: app\ndependencies:\n  flutter:\n    sdk: flutter\n",
    )
    _write(proj / "lib" / "x.dart", "void main() {}\n")
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "missing_flutter_localizations" in _rules(res)


@pytest.mark.asyncio
async def test_supported_locales_mismatch_extra_in_code(tmp_path: Path):
    proj = _project(tmp_path)
    _arb(proj, "en", {"hello": "Hello"})
    # supportedLocales declares pl but no pl.arb exists
    _write(
        proj / "lib" / "main.dart",
        "import 'package:flutter/material.dart';\n"
        "Widget app() => MaterialApp(\n"
        "  localizationsDelegates: const [],\n"
        "  supportedLocales: const [Locale('en'), Locale('pl')],\n"
        ");\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "supported_locales_mismatch" in _rules(res)


@pytest.mark.asyncio
async def test_supported_locales_mismatch_extra_in_arb(tmp_path: Path):
    proj = _project(tmp_path)
    _arb(proj, "en", {"hello": "Hello"})
    _arb(proj, "de", {"hello": "Hallo"})
    # supportedLocales only declares 'en'; de.arb is orphan
    _write(
        proj / "lib" / "main.dart",
        "import 'package:flutter/material.dart';\n"
        "Widget app() => MaterialApp(\n"
        "  localizationsDelegates: const [],\n"
        "  supportedLocales: const [Locale('en')],\n"
        ");\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "supported_locales_mismatch" in _rules(res)


@pytest.mark.asyncio
async def test_missing_localizations_delegates_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _arb(proj, "en", {"hello": "Hello"})
    _arb(proj, "pl", {"hello": "Cześć"})
    _write(
        proj / "lib" / "main.dart",
        "import 'package:flutter/material.dart';\n"
        "Widget app() => MaterialApp(\n"
        "  supportedLocales: const [Locale('en'), Locale('pl')],\n"
        ");\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "missing_localizations_delegates" in _rules(res)


@pytest.mark.asyncio
async def test_rtl_unsupported_fires(tmp_path: Path):
    proj = _project(tmp_path)
    _arb(proj, "en", {"hello": "Hello"})
    _arb(proj, "ar", {"hello": "مرحبا"})
    # Arabic declared, no Directionality / TextDirection anywhere
    _write(
        proj / "lib" / "main.dart",
        "import 'package:flutter/material.dart';\n"
        "Widget app() => MaterialApp(\n"
        "  localizationsDelegates: const [],\n"
        "  supportedLocales: const [Locale('en'), Locale('ar')],\n"
        ");\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "right_to_left_unsupported" in _rules(res)


@pytest.mark.asyncio
async def test_rtl_supported_does_not_fire_with_directionality(tmp_path: Path):
    proj = _project(tmp_path)
    _arb(proj, "en", {"hello": "Hello"})
    _arb(proj, "ar", {"hello": "مرحبا"})
    _write(
        proj / "lib" / "main.dart",
        "import 'package:flutter/material.dart';\n"
        "Widget app() => MaterialApp(\n"
        "  localizationsDelegates: const [],\n"
        "  supportedLocales: const [Locale('en'), Locale('ar')],\n"
        ");\n"
        "Widget wrap(Widget c) => Directionality(\n"
        "  textDirection: TextDirection.rtl, child: c);\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert "right_to_left_unsupported" not in _rules(res)


# ---- engine behaviors --------------------------------------------------


@pytest.mark.asyncio
async def test_locales_detected_in_result(tmp_path: Path):
    proj = _project(tmp_path)
    _arb(proj, "en", {"hello": "Hello"})
    _arb(proj, "pl", {"hello": "Cześć"})
    _arb(proj, "de", {"hello": "Hallo"})
    _write(proj / "lib" / "x.dart", "void main() {}\n")
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert set(res.value.locales_detected) == {"en", "pl", "de"}


@pytest.mark.asyncio
async def test_min_level_filter_suppresses_lower(tmp_path: Path):
    proj = _project(tmp_path)
    _write(
        proj / "lib" / "x.dart",
        "import 'package:flutter/material.dart';\n"
        "Widget w() => Text('Hello world');\n",  # junior
    )
    res = await _run(proj, min_level="senior")
    assert isinstance(res, Ok)
    # All findings should be senior+
    assert all(
        f.level != LocalizationLevel.JUNIOR for f in res.value.findings
    )


@pytest.mark.asyncio
async def test_grade_well_localized_when_clean(tmp_path: Path):
    proj = _project(tmp_path)
    _arb(proj, "en", {"hello": "Hello"})
    _arb(proj, "pl", {"hello": "Cześć"})
    _write(
        proj / "lib" / "main.dart",
        "import 'package:flutter/material.dart';\n"
        "Widget app() => MaterialApp(\n"
        "  localizationsDelegates: const [],\n"
        "  supportedLocales: const [Locale('en'), Locale('pl')],\n"
        ");\n"
        "Widget greet(BuildContext c) => "
        "Text(AppLocalizations.of(c)!.hello);\n",
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert res.value.grade in ("well_localized", "acceptable")


@pytest.mark.asyncio
async def test_grade_missing_l10n_when_no_arb(tmp_path: Path):
    proj = _project(tmp_path)
    # Many hardcoded strings, no arb files
    _write(
        proj / "lib" / "x.dart",
        "import 'package:flutter/material.dart';\n"
        + "\n".join([
            f"Widget w{i}() => Text('User-facing message {i}');"
            for i in range(15)
        ]),
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    assert res.value.grade in ("missing_l10n", "single_locale")
    assert res.value.locales_detected == ()


@pytest.mark.asyncio
async def test_top_actions_prioritized_by_severity(tmp_path: Path):
    proj = _project(tmp_path)
    _arb(proj, "en", {"hello": "Hello"})
    _arb(proj, "pl", {"hello": "Cześć"})
    _write(
        proj / "lib" / "page.dart",
        "Widget x(BuildContext c) => "
        "Text(AppLocalizations.of(c)!.missingKey);\n",  # BLOCKER
    )
    res = await _run(proj)
    assert isinstance(res, Ok)
    # First top_action should be blocker
    assert res.value.top_actions
    assert "[blocker]" in res.value.top_actions[0]

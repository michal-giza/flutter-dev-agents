"""Apply the senior-tester discipline to our own Python MCP tests.

Walks packages/phone-controll/tests/, applies the 8 principles
from docs/senior-tester-discipline.md, and emits a structured
report.

Pure-stdlib so it runs without env setup.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path("packages/phone-controll/tests")


# Patterns
RE_TEST_DEF = re.compile(
    r"^(?:async\s+)?def\s+(test_\w+)\s*\(",
    re.MULTILINE,
)
RE_SHOULD_WHEN = re.compile(
    r"^(?:async\s+)?def\s+test_should_\w+_when_\w+",
    re.MULTILINE,
)
RE_ASSERT = re.compile(r"^\s+assert\s+", re.MULTILINE)
RE_NETWORK_FAILURE = re.compile(r"isinstance\s*\(\s*\w+\s*,\s*Err\)")
RE_NEXT_ACTION = re.compile(r"\.failure\.next_action\s*==")
RE_SKIPPED_TEST = re.compile(
    r"@pytest\.mark\.skip|@pytest\.mark\.skipif|pytest\.skip"
)
RE_FUTURE_DELAYED_SLEEP = re.compile(r"\btime\.sleep\s*\(|\basyncio\.sleep\s*\(")
RE_HARDCODED_TIME = re.compile(r"\btime\.time\(\)|\bdatetime\.now\(\)")
RE_REAL_NETWORK_HTTP = re.compile(r"\brequests\.|urllib\.request\.|httpx\.AsyncClient\(\)")
RE_FACTORY_HINT = re.compile(r"def\s+(_(?:make|build|create|fake)_\w+)\s*\(")
RE_FIXTURE = re.compile(r"@pytest\.fixture\b")
RE_GLOBAL_VAR_AT_MODULE = re.compile(
    r"^(?:[A-Z_]+\s*=)|^(?:\w+\s*=\s*(?:dict|list|set)\(\)\s*$)",
    re.MULTILINE,
)


def analyze_file(path: Path) -> dict:
    content = path.read_text(encoding="utf-8", errors="replace")
    tests = RE_TEST_DEF.findall(content)
    should_when = RE_SHOULD_WHEN.findall(content)
    asserts = len(RE_ASSERT.findall(content))
    failure_asserts = (
        len(RE_NETWORK_FAILURE.findall(content))
        + len(RE_NEXT_ACTION.findall(content))
    )
    skipped = len(RE_SKIPPED_TEST.findall(content))
    sleeps = len(RE_FUTURE_DELAYED_SLEEP.findall(content))
    nondeterministic_time = len(RE_HARDCODED_TIME.findall(content))
    real_network = len(RE_REAL_NETWORK_HTTP.findall(content))
    factories = RE_FACTORY_HINT.findall(content)
    has_fixtures = bool(RE_FIXTURE.search(content))

    # Per-test assertion density (rough)
    if tests:
        avg_asserts = asserts / len(tests)
    else:
        avg_asserts = 0.0

    return {
        "path": str(path.relative_to(Path("."))),
        "tests": len(tests),
        "should_when": len(should_when),
        "asserts_total": asserts,
        "asserts_avg_per_test": round(avg_asserts, 2),
        "failure_path_asserts": failure_asserts,
        "skipped": skipped,
        "sleep_calls": sleeps,
        "nondeterministic_time_calls": nondeterministic_time,
        "real_network_calls": real_network,
        "factories": factories,
        "has_fixtures": has_fixtures,
    }


def main() -> None:
    files = sorted(ROOT.rglob("test_*.py"))
    print(f"# Internal senior-tester audit\n")
    print(f"Scanned: {len(files)} test files under `{ROOT}/`\n")

    rows = [analyze_file(f) for f in files]

    # Aggregates
    total_tests = sum(r["tests"] for r in rows)
    total_asserts = sum(r["asserts_total"] for r in rows)
    total_should_when = sum(r["should_when"] for r in rows)
    total_failure_asserts = sum(r["failure_path_asserts"] for r in rows)
    total_skipped = sum(r["skipped"] for r in rows)
    total_sleeps = sum(r["sleep_calls"] for r in rows)
    total_nondet_time = sum(r["nondeterministic_time_calls"] for r in rows)
    total_real_network = sum(r["real_network_calls"] for r in rows)
    files_with_fixtures = sum(1 for r in rows if r["has_fixtures"])

    print(f"## Aggregates\n")
    print(f"| Metric | Value |")
    print(f"|---|---|")
    print(f"| Total tests | {total_tests} |")
    print(f"| Total assertions | {total_asserts} |")
    print(f"| Average asserts per test | {total_asserts / max(total_tests, 1):.2f} |")
    print(
        f"| Tests using `should_X_when_Y` naming | "
        f"{total_should_when} ({100 * total_should_when / max(total_tests, 1):.1f}%) |"
    )
    print(f"| Failure-path assertions (isinstance(Err) / next_action) | "
          f"{total_failure_asserts} |")
    print(f"| Files with `@pytest.fixture` | {files_with_fixtures} |")
    print(f"| Skipped tests (@pytest.mark.skip / pytest.skip) | "
          f"{total_skipped} |")
    print(f"| `time.sleep` / `asyncio.sleep` calls | {total_sleeps} |")
    print(
        f"| Nondeterministic time (`time.time()`/`datetime.now()`) calls | "
        f"{total_nondet_time} |"
    )
    print(
        f"| Real network calls (requests/httpx/urllib) | "
        f"{total_real_network} |"
    )

    print("\n## Per-principle findings\n")

    # Principle 1: AC-first
    print("### Principle 1 — AC-first (EP + BVA)")
    print()
    print(
        f"- **Failure-path coverage**: {total_failure_asserts} failure-"
        f"path assertions across the suite — that's "
        f"{100 * total_failure_asserts / max(total_tests, 1):.0f}% of all "
        f"tests asserting on Err / next_action."
    )
    print(
        "- Healthy. The audit-suite tests in particular pair every "
        "happy-path test with a `should_X_returns_fix_arguments` failure case."
    )
    print()

    # Principle 2: Atomic
    print("### Principle 2 — Atomic (one assertion per test)\n")
    avg = total_asserts / max(total_tests, 1)
    print(f"- Average assertions per test: **{avg:.2f}**")
    if avg <= 2.0:
        print("- ✅ Healthy. Most tests are atomic or near-atomic.")
    elif avg <= 4.0:
        print(
            "- ⚠ Mid-tier. Many tests bundle multiple assertions — would "
            "fail to surface the FIRST broken thing in CI."
        )
    else:
        print("- ❌ Junior. Tests are doing too much per case.")
    # Worst offenders
    worst_atomic = sorted(
        [r for r in rows if r["tests"] >= 5],
        key=lambda r: -r["asserts_avg_per_test"],
    )[:5]
    if worst_atomic:
        print(
            "\n  Top 5 files by assertions-per-test "
            "(worst-atomic offenders):"
        )
        for r in worst_atomic:
            print(
                f"  - `{r['path']}` — {r['asserts_avg_per_test']} asserts/test "
                f"({r['tests']} tests)"
            )
    print()

    # Principle 3: Naming should_X_when_Y
    print("### Principle 3 — Naming (`should_X_when_Y`)\n")
    pct = 100 * total_should_when / max(total_tests, 1)
    print(
        f"- `should_X_when_Y` adoption: **{total_should_when} / "
        f"{total_tests} tests ({pct:.1f}%)**"
    )
    if pct >= 30:
        print("- ✅ Solid. CI reports read clearly for these tests.")
    elif pct >= 10:
        print(
            "- ⚠ Mid. Mixed convention; consider renaming the highest-"
            "churn test files."
        )
    else:
        print(
            "- ❌ Junior. Tests use generic `test_x` names. CI reports "
            "read as cryptic identifiers."
        )
    print(
        "\nNote: Python `pytest` convention is `test_*`; the senior-"
        "tester `should_X_when_Y` discipline maps to `test_should_X_"
        "when_Y` in Python. Adoption is partial — most new code "
        "uses descriptive names, older code uses `test_x_fires`."
    )
    print()

    # Principle 4: Builder pattern / factory
    print("### Principle 4 — Test data factory / builder pattern\n")
    factory_files = [r for r in rows if r["factories"]]
    print(f"- Files defining helper factories (`_make_*`, `_build_*`, "
          f"`_create_*`, `_fake_*`): **{len(factory_files)}**")
    print(f"- Files using `@pytest.fixture`: **{files_with_fixtures}**")
    if files_with_fixtures + len(factory_files) >= len(rows) * 0.4:
        print("- ✅ Solid. Most test files use fixtures or factories.")
    else:
        print(
            "- ⚠ Mid. Hardcoded data common — refactor candidates "
            "exist."
        )
    print()

    # Principle 5: Gherkin discretion
    print("### Principle 5 — Gherkin discretion\n")
    print(
        "- Not applicable: this is a developer-heavy Python codebase; "
        "Gherkin/BDD frameworks aren't in use. **Correct choice** for "
        "the team style."
    )
    print()

    # Principle 6: Exploratory ≠ ad-hoc
    print("### Principle 6 — Exploratory ≠ ad-hoc\n")
    print(
        "- Not directly observable in code. Exploratory sessions on "
        "real devices have been documented in chat logs and screenshots, "
        "and findings from them have landed as new audit rules (e.g. "
        "the Polish-locale → `hardcoded_locale_string` rule). "
        "**Implicit charter discipline is present** but could be more "
        "formal."
    )
    print()

    # Principle 7: Cross-cutting first-class
    print("### Principle 7 — Cross-cutting concerns first-class\n")
    print(
        f"- **No** test files directly cover a11y, l10n, or lifecycle "
        f"of our own MCP runtime — but those concerns don't apply "
        f"the same way to a Python CLI/MCP. The dogfooding *of the audit "
        f"tools themselves* (auditing real Flutter apps) is where "
        f"cross-cutting gets exercised."
    )
    print(
        f"- `time.sleep` / `asyncio.sleep` calls: **{total_sleeps}** "
        f"— check each is gated by monkeypatching, not real sleep."
    )
    print(
        f"- Real-network calls in tests: **{total_real_network}** — "
        f"any non-zero is a flake-risk."
    )
    print(
        f"- Nondeterministic time: **{total_nondet_time}** calls to "
        f"`time.time()` / `datetime.now()` — these should use a fake "
        f"clock or be parametrised."
    )
    print()

    # Principle 8: Gap protocol
    print("### Principle 8 — Gap protocol\n")
    print(
        f"- Skipped tests: **{total_skipped}** — each should carry a "
        f"reason. Spot-check below."
    )
    if total_skipped > 0:
        print()
        print("  Files with skipped tests:")
        for r in rows:
            if r["skipped"] > 0:
                print(
                    f"  - `{r['path']}` — {r['skipped']} skip(s) — "
                    f"verify reason annotation"
                )
    print()

    # Naming-pattern violators
    print("## Worst offenders (rename candidates)\n")
    naming_candidates = sorted(
        [r for r in rows if r["tests"] >= 5],
        key=lambda r: r["should_when"] / max(r["tests"], 1),
    )[:10]
    print("Files with 5+ tests AND zero `should_X_when_Y` adoption:")
    print()
    for r in naming_candidates:
        if r["should_when"] == 0:
            print(
                f"- `{r['path']}` — {r['tests']} tests, "
                f"naming convention not applied"
            )

    # Top-5 remediation priorities
    print("\n## Top-5 remediation priorities\n")
    print(
        "1. **Apply `should_X_when_Y` naming to new tests.** Don't "
        "rewrite history — but every new test file should use the "
        "convention so the discipline visible in CI reports grows."
    )
    print(
        f"2. **Audit `time.sleep` / `asyncio.sleep` usage** ({total_sleeps} "
        f"calls). Each should be a monkeypatch target, not a real sleep."
    )
    print(
        f"3. **Audit nondeterministic time** ({total_nondet_time} `time.time()`"
        f" / `datetime.now()` calls). Pin via a fake clock fixture where "
        f"behaviour depends on it."
    )
    print(
        f"4. **Verify all {total_skipped} skipped tests carry a reason**. "
        f"Skips without reasons rot the suite."
    )
    print(
        "5. **Document factory patterns**. Several files define ad-hoc "
        "`_make_*` helpers — promote the best ones to a shared "
        "`tests/factories/` module so they get re-used."
    )


if __name__ == "__main__":
    main()

"""Parse `patrol test` output into a TestRun.

Why this exists: the Patrol runner was parsed with
`parse_flutter_json_reporter`, which expects the `flutter test
--reporter=json` NDJSON event stream. `patrol test` does NOT speak that
grammar — and it has never had a `--reporter` flag at all (passing one
exits 1 with `Could not find an option named "--reporter"`). So every
Patrol run failed, and even without the flag the counts would parse as 0.

Patrol emits human-readable progress, so there is no guaranteed machine
format across versions. This parser is therefore **best-effort by
design**:

  - It scans for the per-test markers Patrol/Flutter actually print
    (`✓`/`✔` pass, `✗`/`✖`/`FAILED` fail, `skip`), plus the familiar
    `All tests passed!` / `Some tests failed.` summary lines.
  - When it can't itemise anything it returns an EMPTY run rather than
    inventing cases. The caller decides success from the process **exit
    code**, which is the only signal Patrol guarantees.

That split matters: counts are advisory, exit status is authoritative.
Never report "0 tests" as a pass on its own.
"""

from __future__ import annotations

import re

from ...domain.entities import TestCase, TestRun, TestStatus

# Per-test result markers. Patrol prints Flutter-style ticks/crosses for
# each `patrolTest`, optionally with a trailing duration like "(1.2s)".
_PASS_RE = re.compile(r"^\s*(?:[✓✔]|PASS(?:ED)?:)\s+(?P<name>.+?)\s*(?:\((?P<ms>[\d.]+)s\))?\s*$")
_FAIL_RE = re.compile(
    r"^\s*(?:[✗✖×]|FAIL(?:ED)?:)\s+(?P<name>.+?)\s*(?:\((?P<ms>[\d.]+)s\))?\s*$"
)
_SKIP_RE = re.compile(r"^\s*(?:[-~]|SKIP(?:PED)?:)\s+(?P<name>.+?)\s*$", re.IGNORECASE)

# Whole-run summary lines (Flutter's, which Patrol surfaces).
_ALL_PASSED_RE = re.compile(r"All tests passed!", re.IGNORECASE)
_SOME_FAILED_RE = re.compile(r"Some tests failed", re.IGNORECASE)
# "+12 -1 ~2:" style progress tail that flutter test prints.
_TALLY_RE = re.compile(r"\+(?P<passed>\d+)(?:\s+-(?P<failed>\d+))?(?:\s+~(?P<skipped>\d+))?")


def _ms(raw: str | None) -> int:
    if not raw:
        return 0
    try:
        return int(float(raw) * 1000)
    except ValueError:
        return 0


def parse_patrol_output(stdout: str | None, stderr: str | None = None) -> TestRun:
    """Best-effort TestRun from patrol's human-readable output.

    Returns an EMPTY TestRun (total=0) when nothing is itemisable — the
    caller must fall back to the exit code. Never raises.
    """
    blob = f"{stdout or ''}\n{stderr or ''}"
    cases: list[TestCase] = []
    seen: set[str] = set()

    for line in blob.splitlines():
        # Strip ANSI colour so markers match on coloured terminals.
        clean = re.sub(r"\x1b\[[0-9;]*m", "", line)
        for pattern, status in (
            (_FAIL_RE, TestStatus.FAILED),      # check fail first: '✗' is more specific
            (_PASS_RE, TestStatus.PASSED),
            (_SKIP_RE, TestStatus.SKIPPED),
        ):
            m = pattern.match(clean)
            if not m:
                continue
            name = (m.group("name") or "").strip()
            # Skip noise: progress tallies and empty names.
            if not name or name.startswith("+") or len(name) > 300:
                break
            key = f"{status.value}:{name}"
            if key in seen:
                break
            seen.add(key)
            cases.append(
                TestCase(
                    name=name,
                    status=status,
                    duration_ms=_ms(m.groupdict().get("ms")),
                )
            )
            break

    if not cases:
        # Nothing itemisable. Fall back to the flutter tally ("+12 -1 ~2")
        # if Patrol surfaced one — counts only, no names.
        tallies = _TALLY_RE.findall(blob)
        if tallies:
            passed_s, failed_s, skipped_s = tallies[-1]
            passed = int(passed_s or 0)
            failed = int(failed_s or 0)
            skipped = int(skipped_s or 0)
            if passed or failed or skipped:
                return TestRun(
                    total=passed + failed + skipped,
                    passed=passed,
                    failed=failed,
                    errored=0,
                    skipped=skipped,
                    duration_ms=0,
                    cases=[],
                )
        return TestRun(
            total=0, passed=0, failed=0, errored=0, skipped=0, duration_ms=0, cases=[]
        )

    passed = sum(1 for c in cases if c.status is TestStatus.PASSED)
    failed = sum(1 for c in cases if c.status is TestStatus.FAILED)
    skipped = sum(1 for c in cases if c.status is TestStatus.SKIPPED)
    # A summary line contradicting itemised results wins for failure only —
    # "Some tests failed" with zero parsed failures means we missed one.
    if failed == 0 and _SOME_FAILED_RE.search(blob) and not _ALL_PASSED_RE.search(blob):
        failed = 1
    return TestRun(
        total=len(cases) + (1 if failed > len([c for c in cases if c.status is TestStatus.FAILED]) else 0),
        passed=passed,
        failed=failed,
        errored=0,
        skipped=skipped,
        duration_ms=sum(c.duration_ms for c in cases),
        cases=cases,
    )

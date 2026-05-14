"""Minimal JUnit XML emitter for PlanRun.

Targets the JUnit-XML schema understood by GitHub Actions, GitLab Runners,
Jenkins, Buildkite, etc. — one <testsuite> per plan, one <testcase> per phase.

Failures and errors are distinguished:
- A failed phase whose error_code suggests *test* failure (TestExecutionFailure,
  HotReloadFailure, UiElementNotFoundFailure) becomes <failure>.
- Anything else (DeviceBusyFailure, FlutterCliFailure, etc.) becomes <error>.

VERDICT_BLOCKED auto-injected phases are skipped from the report — they're
just propagation markers, not real test cases.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from ..domain.entities import PlanRun

_FAILURE_CODES = frozenset(
    {
        "TestExecutionFailure",
        "HotReloadFailure",
        "UiElementNotFoundFailure",
        "TimeoutFailure",
        "VisionFailure",
    }
)


def write_junit(run: PlanRun, output_path: Path) -> Path:
    """Emit a JUnit-XML file at output_path. Returns the path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    suite = ET.Element("testsuite")
    suite.set("name", run.plan_name)
    suite.set("timestamp", run.started_at.isoformat())
    suite.set("time", f"{run.duration_ms / 1000.0:.3f}")

    real_phases = [p for p in run.phases if p.phase != "VERDICT_BLOCKED"]
    failures = [p for p in real_phases if not p.ok and (p.error_code in _FAILURE_CODES)]
    errors = [p for p in real_phases if not p.ok and p.error_code not in _FAILURE_CODES]
    skipped = [p for p in real_phases if p.actual_outcome == "skipped_after_terminal"]

    suite.set("tests", str(len(real_phases)))
    suite.set("failures", str(len(failures)))
    suite.set("errors", str(len(errors)))
    suite.set("skipped", str(len(skipped)))

    for phase in real_phases:
        case = ET.SubElement(suite, "testcase")
        case.set("name", phase.phase)
        case.set("classname", run.plan_name)
        case.set("time", f"{phase.duration_ms / 1000.0:.3f}")

        if phase in skipped:
            ET.SubElement(case, "skipped").text = phase.notes or "skipped"
            continue
        if not phase.ok:
            tag = "failure" if phase.error_code in _FAILURE_CODES else "error"
            element = ET.SubElement(case, tag)
            element.set("type", phase.error_code or "Failure")
            element.set("message", phase.error_message or "")

    tree = ET.ElementTree(suite)
    ET.indent(tree, space="  ")
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    return output_path

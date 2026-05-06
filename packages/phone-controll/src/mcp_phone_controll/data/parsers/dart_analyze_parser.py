"""Parse `dart analyze --format=json` output.

Output shape (Dart SDK ≥ 2.18):
    {
      "version": 1,
      "diagnostics": [
        {
          "code": "unused_import",
          "severity": "INFO" | "WARNING" | "ERROR",
          "type": "LINT" | "HINT" | ...,
          "location": { "file": "...", "range": { "start": {"offset": ..., "line": ..., "column": ...}}},
          "problemMessage": "...",
          "documentation": "..."
        },
        ...
      ]
    }

Older versions emit a slightly different shape; we handle both.
"""

from __future__ import annotations

import json
from pathlib import Path

from ...domain.entities import AnalyzerIssue, AnalyzerSeverity


def parse_analyze_json(stdout: str) -> list[AnalyzerIssue]:
    text = stdout.strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, dict):
        return []
    diagnostics = payload.get("diagnostics") or []
    issues: list[AnalyzerIssue] = []
    for diag in diagnostics:
        if not isinstance(diag, dict):
            continue
        severity_token = str(diag.get("severity", "INFO")).upper()
        try:
            severity = AnalyzerSeverity(severity_token.lower())
        except ValueError:
            severity = AnalyzerSeverity.INFO
        location = diag.get("location") or {}
        loc_range = location.get("range") or {}
        start = loc_range.get("start") or {}
        file_raw = location.get("file")
        issues.append(
            AnalyzerIssue(
                severity=severity,
                code=str(diag.get("code", "")),
                message=str(diag.get("problemMessage") or diag.get("message", "")),
                file=Path(file_raw) if file_raw else None,
                line=start.get("line"),
                column=start.get("column"),
            )
        )
    return issues

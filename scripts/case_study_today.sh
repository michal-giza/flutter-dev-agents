#!/usr/bin/env bash
# case_study_today.sh — open today's case-study journal entry.
#
# Creates docs/internal/case-study-journal/YYYY-MM-DD.md from
# _template.md if it doesn't exist, with placeholders filled in
# (date, day-of-week, MCP version, git SHA, tool tier).
#
# Then opens it in $EDITOR (or VS Code if EDITOR unset).
#
# Idempotent — running twice in the same day opens the existing
# entry, never overwrites.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JOURNAL_DIR="${ROOT}/docs/internal/case-study-journal"
TEMPLATE="${JOURNAL_DIR}/_template.md"

if [[ ! -f "${TEMPLATE}" ]]; then
    echo "ERROR: template not found at ${TEMPLATE}" >&2
    exit 1
fi

DATE_ISO=$(date +%Y-%m-%d)
DAY_OF_WEEK=$(date +%A)
ENTRY="${JOURNAL_DIR}/${DATE_ISO}.md"

# Pull version + sha from the canonical sources so the journal
# entry is self-dating. Failures are non-fatal — fall back to
# "unknown" so a missing repo doesn't block the journal.
PYPROJECT="${ROOT}/packages/phone-controll/pyproject.toml"
VERSION=$(
    sed -nE 's/^version = "([^"]+)".*/\1/p' "${PYPROJECT}" 2>/dev/null \
        | head -1 || echo "unknown"
)
GIT_SHA=$(git -C "${ROOT}" rev-parse --short HEAD 2>/dev/null || echo "unknown")
TOOL_TIER="${MCP_TOOL_TIER:-unset (full 110-tool surface)}"

if [[ -f "${ENTRY}" ]]; then
    echo "✓ entry already exists for ${DATE_ISO} — opening"
else
    # Substitute placeholders. Avoid `sed -i` because the syntax
    # diverges between macOS BSD sed and GNU sed; build the new
    # content with a Python one-liner that handles either.
    python3 - <<PY
from pathlib import Path
src = Path("${TEMPLATE}").read_text()
out = (
    src
    .replace("{DATE}", "${DATE_ISO}")
    .replace("{DAY_OF_WEEK}", "${DAY_OF_WEEK}")
    .replace("{VERSION}", "${VERSION}")
    .replace("{GIT_SHA}", "${GIT_SHA}")
    .replace("{TOOL_TIER}", "${TOOL_TIER}")
)
Path("${ENTRY}").write_text(out)
PY
    echo "✓ created ${ENTRY}"
fi

# Open in editor. Order: $EDITOR explicit > code > nano > cat.
if [[ -n "${EDITOR:-}" ]] && command -v "${EDITOR}" >/dev/null 2>&1; then
    exec "${EDITOR}" "${ENTRY}"
elif command -v code >/dev/null 2>&1; then
    exec code "${ENTRY}"
elif command -v nano >/dev/null 2>&1; then
    exec nano "${ENTRY}"
else
    echo "(no editor found; the entry is at ${ENTRY})"
    exit 0
fi

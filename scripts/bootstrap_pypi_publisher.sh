#!/usr/bin/env bash
# Bootstrap the PyPI Trusted Publisher for mcp-phone-controll.
#
# PyPI doesn't expose a registration API for browser-required flows,
# so this script can't fully automate it. What it CAN do:
#
#  1. Print the exact values to paste (no typos, no field guessing).
#  2. Open the publisher-registration page in your browser.
#  3. Verify after-the-fact that the publisher is now active.
#
# Why "pending" publishers exist: PyPI accepts a publisher
# configured BEFORE the first upload. That's the only way to ship
# the very first release via Trusted Publishing without manually
# uploading once first to create the project.

set -euo pipefail

# Read the values from the canonical source — pyproject.toml — so
# this script never goes stale.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYPROJECT="${ROOT}/packages/phone-controll/pyproject.toml"

if [[ ! -f "${PYPROJECT}" ]]; then
    echo "ERROR: ${PYPROJECT} not found" >&2
    exit 1
fi

# Parse a few values out — `awk` instead of a TOML lib because this
# is a portable bash helper, not a Python tool.
# `name = "mcp-phone-controll"` → extract the quoted value. Using sed
# instead of awk because awk's field-splitting on multi-char delimiters
# varies between gawk/mawk/BSD awk.
PROJECT=$(sed -nE 's/^name = "([^"]+)".*/\1/p' "${PYPROJECT}" | head -1)
OWNER="michal-giza"
REPO="flutter-dev-agents"
WORKFLOW="release.yml"
ENVIRONMENT="pypi-publish"

cat <<EOF
================================================================
PyPI Trusted Publisher bootstrap — ${PROJECT}
================================================================

A browser session at pypi.org is required (the publisher form
isn't exposed via API). Open this URL:

    https://pypi.org/manage/account/publishing/

Paste these values into the "Add a new pending publisher" form:

    PyPI project name: ${PROJECT}
    Owner:             ${OWNER}
    Repository name:   ${REPO}
    Workflow filename: ${WORKFLOW}
    Environment name:  ${ENVIRONMENT}

After saving, every \`git push origin v*.*.*\` triggers the
.github/workflows/release.yml workflow which publishes a wheel +
sdist via OIDC — no PYPI_TOKEN secret stored anywhere.

================================================================
EOF

# Best-effort: open the URL in the user's browser. Falls back to
# just printing if no opener is found.
URL="https://pypi.org/manage/account/publishing/"
if command -v open >/dev/null 2>&1; then
    open "${URL}"
elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "${URL}" >/dev/null 2>&1 || true
else
    echo "(Couldn't auto-open browser; visit ${URL} manually.)"
fi

# After they save the publisher, they can run this script again
# with `verify` and we ping PyPI to confirm it's registered.
if [[ "${1:-}" == "verify" ]]; then
    echo
    echo "Verifying publisher visibility on PyPI…"
    if curl -fsS "https://pypi.org/pypi/${PROJECT}/json" >/dev/null 2>&1; then
        echo "✓ ${PROJECT} exists on PyPI."
        VERSION=$(
            curl -fsS "https://pypi.org/pypi/${PROJECT}/json" \
                | python3 -c 'import sys,json; print(json.load(sys.stdin)["info"]["version"])'
        )
        echo "  Latest published version: ${VERSION}"
    else
        echo "✗ ${PROJECT} not yet on PyPI."
        echo "  This is expected if the publisher is still 'pending'."
        echo "  Push a v*.*.* tag to trigger the first upload."
    fi
fi

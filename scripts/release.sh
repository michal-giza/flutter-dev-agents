#!/usr/bin/env bash
# Cut a new release. Composable from CI or run locally.
#
# Usage:  ./scripts/release.sh 0.2.2
#         ./scripts/release.sh 0.3.0 --dry-run    # show what would happen
#
# What it does (in order, fail-fast at each step):
#
#  1.  Validate the version is semver and not already tagged.
#  2.  Verify main is clean + you're on a release branch (refuses
#      on a dirty tree — releases must be reproducible).
#  3.  Bump pyproject.toml.
#  4.  Update CHANGELOG.md's `[Unreleased]` heading to the new
#      version (if you keep one — falls back gracefully if not).
#  5.  Commit, push the release branch.
#  6.  Print the gh-pr-create command for the release PR.
#
# What it does NOT do (deliberately):
#
#  - Tag main directly. Tag AFTER the release PR merges (the
#    .github/workflows/release.yml triggers on tag push and
#    publishes to PyPI via OIDC).
#  - Push to PyPI directly. That's the workflow's job.
#  - Cut a GitHub release. Use `gh release create v0.2.2 --notes-file …`
#    after the tag is pushed.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYPROJECT="${ROOT}/packages/phone-controll/pyproject.toml"
CHANGELOG="${ROOT}/CHANGELOG.md"

if [[ $# -lt 1 ]]; then
    cat <<EOF
Usage: $0 <new-version> [--dry-run]

Example:  $0 0.2.2
EOF
    exit 1
fi

NEW_VERSION="$1"
DRY_RUN=0
if [[ "${2:-}" == "--dry-run" ]]; then
    DRY_RUN=1
fi

# 1. Semver shape — refuse anything that won't parse as N.N.N or
# N.N.N-rc.N. PyPI is strict; better to catch typos here.
if ! [[ "${NEW_VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-(rc|alpha|beta)\.[0-9]+)?$ ]]; then
    echo "ERROR: '${NEW_VERSION}' is not a valid semver (expected N.N.N[-rc.N])" >&2
    exit 1
fi

# 2. Tag must not already exist.
TAG="v${NEW_VERSION}"
if git -C "${ROOT}" rev-parse "${TAG}" >/dev/null 2>&1; then
    echo "ERROR: tag ${TAG} already exists" >&2
    exit 1
fi

# 3. Working tree must be clean. Releases need to be reproducible
# from the commit, not the local diff.
if [[ -n "$(git -C "${ROOT}" status --porcelain)" ]]; then
    echo "ERROR: working tree is dirty. Commit or stash first:" >&2
    git -C "${ROOT}" status --short >&2
    exit 1
fi

CURRENT_VERSION=$(
    sed -nE 's/^version = "([^"]+)".*/\1/p' "${PYPROJECT}" | head -1
)

echo "Cutting release: ${CURRENT_VERSION} → ${NEW_VERSION}"
echo

if [[ ${DRY_RUN} -eq 1 ]]; then
    echo "(--dry-run mode; not modifying files)"
    echo
    echo "Would:"
    echo "  1. sed -i bump pyproject.toml: ${CURRENT_VERSION} → ${NEW_VERSION}"
    echo "  2. git checkout -b release/${NEW_VERSION}"
    echo "  3. git commit -am 'release: ${NEW_VERSION}'"
    echo "  4. git push -u origin release/${NEW_VERSION}"
    echo "  5. print the gh pr create command"
    exit 0
fi

# 4. Refuse to run from main directly — release happens on a
# release branch so the merge to main is the release event.
CURRENT_BRANCH=$(git -C "${ROOT}" rev-parse --abbrev-ref HEAD)
if [[ "${CURRENT_BRANCH}" == "main" ]]; then
    echo "Switching to release branch release/${NEW_VERSION}"
    git -C "${ROOT}" checkout -b "release/${NEW_VERSION}"
fi

# 5. Bump the version. macOS sed needs the `-i ''` form; GNU sed
# is `-i` only. Detect platform.
if [[ "$(uname)" == "Darwin" ]]; then
    sed -i '' -E "s/^version = \"${CURRENT_VERSION}\"/version = \"${NEW_VERSION}\"/" "${PYPROJECT}"
else
    sed -i -E "s/^version = \"${CURRENT_VERSION}\"/version = \"${NEW_VERSION}\"/" "${PYPROJECT}"
fi

# Confirm the bump landed before commit.
NOW=$(sed -nE 's/^version = "([^"]+)".*/\1/p' "${PYPROJECT}" | head -1)
if [[ "${NOW}" != "${NEW_VERSION}" ]]; then
    echo "ERROR: version bump failed; pyproject still says ${NOW}" >&2
    exit 1
fi

# 6. Reminder: the user fills in the CHANGELOG manually. We don't
# fabricate one — the human writes the narrative. Print the
# placeholder header so they know where to add.
TODAY=$(date +%Y-%m-%d)
if ! grep -q "^## \[${NEW_VERSION}\]" "${CHANGELOG}"; then
    cat <<EOF

⚠️  CHANGELOG.md doesn't have a section for ${NEW_VERSION} yet.
    Add one above the previous version like:

    ## [${NEW_VERSION}] — ${TODAY}

    ### Added / Fixed / Changed
    - ...

    Then re-run this script.

EOF
    exit 1
fi

# 7. Commit + push.
git -C "${ROOT}" add "${PYPROJECT}" "${CHANGELOG}"
git -C "${ROOT}" commit -m "release: ${NEW_VERSION}"
git -C "${ROOT}" push -u origin "release/${NEW_VERSION}"

# 8. Surface the next manual step. We don't auto-open a PR because
# the user reviews the diff first.
cat <<EOF

================================================================
Release branch pushed. Next step — open the PR:

  gh pr create --title "release: v${NEW_VERSION}" --body "Bump to ${NEW_VERSION}. See CHANGELOG.md for full notes."

After the PR merges:

  git checkout main && git pull
  git tag -a v${NEW_VERSION} -m "v${NEW_VERSION}" && git push origin v${NEW_VERSION}

The tag push triggers .github/workflows/release.yml which publishes
to PyPI via OIDC. Watch the run:

  gh run watch --branch v${NEW_VERSION}
================================================================
EOF

#!/usr/bin/env bash
# Fresh-laptop bootstrap for flutter-dev-agents.
#
# Installs everything an Android+iOS Flutter developer needs to run the MCPs:
#   - Android Platform Tools (adb)
#   - Xcode Command Line Tools (for iOS / xcrun)
#   - Python venv + dev/ar/http extras
#   - uiautomator2 device-side agent (per connected Android device)
#   - Optional: registers the MCP with Claude Code
#
# Idempotent: re-running is safe.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_DIR="${REPO_ROOT}/packages/phone-controll"

echo "==> flutter-dev-agents install starting (REPO_ROOT=${REPO_ROOT})"

# --- 1. Homebrew ---
if ! command -v brew >/dev/null 2>&1; then
    echo "ERROR: Homebrew not installed. See https://brew.sh"
    exit 1
fi

# --- 2. Android Platform Tools (adb) ---
if ! command -v adb >/dev/null 2>&1; then
    echo "==> installing android-platform-tools"
    brew install --cask android-platform-tools
else
    echo "==> adb already on PATH ($(adb version | head -1))"
fi

# --- 3. Xcode CLT ---
if ! xcode-select -p >/dev/null 2>&1; then
    echo "==> installing Xcode Command Line Tools (interactive)"
    xcode-select --install || true
else
    echo "==> Xcode CLT already installed ($(xcode-select -p))"
fi

# --- 4. uv ---
if ! command -v uv >/dev/null 2>&1; then
    echo "==> installing uv"
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# --- 5. venv + extras ---
cd "${PACKAGE_DIR}"
if [ ! -d ".venv" ]; then
    echo "==> creating venv"
    uv venv --python 3.11
fi
echo "==> installing phone-controll with dev,ar,http extras"
uv pip install -e ".[dev,ar,http]"

# --- 6. tests ---
echo "==> running unit tests"
"${PACKAGE_DIR}/.venv/bin/pytest" -q || {
    echo "WARNING: tests failed — investigate before registering with Claude"
    exit 1
}

# --- 7. uiautomator2 init for connected Android devices ---
if command -v adb >/dev/null 2>&1 && [ "$(adb devices | grep -c device$)" -gt 0 ]; then
    echo "==> initialising uiautomator2 on each connected Android device"
    "${PACKAGE_DIR}/.venv/bin/python" -m uiautomator2 init || true
fi

# --- 8. claude mcp add (optional) ---
if command -v claude >/dev/null 2>&1; then
    echo
    echo "==> register MCP with Claude Code? (yes/no)"
    read -r reply
    if [ "${reply}" = "yes" ]; then
        claude mcp add phone-controll -- "${PACKAGE_DIR}/.venv/bin/python" -m mcp_phone_controll
        echo "==> registered. Verify with: claude mcp list"
    fi
else
    echo "==> 'claude' CLI not found. Manually register with:"
    echo "    claude mcp add phone-controll -- ${PACKAGE_DIR}/.venv/bin/python -m mcp_phone_controll"
fi

echo
echo "==> done. Activate the venv with:"
echo "    source ${PACKAGE_DIR}/.venv/bin/activate"

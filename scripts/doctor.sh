#!/usr/bin/env bash
# Quick local environment doctor — same checks as the MCP's `check_environment`
# tool, runnable from a terminal without booting Claude.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${REPO_ROOT}/packages/phone-controll/.venv/bin/python"

if [ ! -x "${PYTHON}" ]; then
    echo "ERROR: venv not set up. Run scripts/install.sh first."
    exit 1
fi

"${PYTHON}" -c "
import asyncio, json
from mcp_phone_controll.container import build_runtime
async def main():
    _, d = build_runtime()
    res = await d.dispatch('check_environment', {})
    print(json.dumps(res, indent=2, default=str))
asyncio.run(main())
"

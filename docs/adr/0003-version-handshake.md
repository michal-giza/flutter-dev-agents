# ADR-0003: Version handshake via `mcp_ping` + boot self-check

**Status:** accepted
**Date:** 2026-05-14

## Context

Three times this week, an agent claimed a feature was missing when it
was actually present on disk. The cause was always the same: the MCP
subprocess was running pre-fix code. Editable installs
(`uv pip install -e .`) update the source on disk, but the running
Python interpreter only loads new code on restart. Claude Code keeps
the MCP subprocess alive across `/clear` and even across some session
resets. The agent couldn't distinguish "feature missing" from "stale
subprocess running old code."

## Decision

Capture version state at MCP-process import time and expose two
diagnostic surfaces:

1. **`mcp_ping`** tool — returns `{package_version, git_sha,
   git_branch, git_dirty, started_at, uptime_s, python_version,
   pid, image_backends, n_tools}`. The agent calls this first when
   a feature appears missing.

2. **Boot self-check log** — one stderr line per MCP-subprocess
   start:

   ```
   [phone-controll] startup: version=0.1.0 sha=fc99e94 branch=main
   python=3.11.15 image_backends=cv2,PIL,sips pid=78788
   ```

   Suppressible via `MCP_QUIET=1` (used in the test suite).

3. **Version ride-along** on `describe_capabilities` — `mcp_version`
   and `mcp_git_sha` fields. Detection without a second tool call.

The user diffs `git_sha` against `git -C <repo> rev-parse --short
HEAD`; mismatch → `exit` + `claude` to restart.

## Consequences

**Easier.** Stale-subprocess class of bugs is now one-tool-call
detectable. Every future "why isn't this working?" debug session
starts at `mcp_ping`. Boot log gives operators a receipt that the
right code loaded.

**Harder.** None significant.

**Accepted.** Importing `subprocess` once at module-load time to
read git status. ~10 ms boot cost.

## Alternatives considered

- **Inline `git rev-parse` per tool call** — too expensive.
- **Read SHA from `__version__`** — would need release tooling we
  don't have.
- **Hash the source tree** — overkill; SHA captures it.

## References

- `src/mcp_phone_controll/version_info.py`
- `src/mcp_phone_controll/domain/usecases/mcp_ping.py`
- `tests/unit/test_mcp_ping.py`
- Commit `fc99e94`

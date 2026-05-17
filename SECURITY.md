# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 0.2.x   | :white_check_mark: |
| 0.1.x   | :x: (pre-release) |

Pre-1.0, only the latest 0.x line gets security fixes. Once 1.0 ships,
this table will be updated with a multi-line backport policy.

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Email: **msquaregiza@gmail.com** with subject prefix `[flutter-dev-agents
SECURITY]`. Include:

1. A description of the vulnerability and how to trigger it.
2. The version (`mcp_ping.git_sha`) where you found it.
3. Your assessment of impact (information disclosure, code execution,
   DoS, privilege escalation).
4. (Optional) A proposed fix.

You should expect:

- An acknowledgement within **3 business days**.
- A triage decision (accepted / not-a-vulnerability / duplicate) within
  **10 business days**.
- For accepted reports: a fix in the next minor release, with public
  credit in the changelog unless you ask to stay anonymous.
- For critical issues (RCE, sandbox escape, secret exfiltration): an
  out-of-band patch release within **5 business days** of accepted
  triage, plus a CVE filing.

## Threat Model — what's in scope, what isn't

### In scope
- **Prompt-injected path arguments.** Tools that accept disk paths
  (`fetch_artifact`, `compress_png`, `install_app`, etc.) MUST refuse
  paths outside an allowed-root list. See
  `domain/path_guard.py` + `ADR-0006`. Report any tool that accepts
  arbitrary paths without `check_path_allowed()`.
- **Shell injection via tool arguments.** All subprocess calls use
  `asyncio.create_subprocess_exec(*cmd)` — never `shell=True`. Report
  any code path that violates this.
- **Path-traversal symlink attacks.** `check_path_allowed()` uses
  `Path.resolve()` to follow symlinks; report any guard that doesn't
  resolve before comparison.
- **Secret leakage in logs.** `observability.emit` should not log full
  argument values. Report any code path that does (e.g. an `auth_bearer`
  string ending up in `tool_dispatch_start` arg_keys).
- **Webhook SSRF.** `notify_webhook` enforces an allowlist
  (`MCP_WEBHOOK_ALLOWLIST`). Report any way to bypass it.
- **HTTP adapter auth bypass.** `MCP_HTTP_API_KEY` gates `/tools` +
  `/tools/{name}`. Report any way to call a tool without the key when
  one is configured.

### Out of scope (won't fix)
- The MCP runs as the invoking user; it inherits their permissions
  by design. Tools like `patch_apply_safe` can edit files the user
  could edit anyway. This is the developer-loop use case, not a
  multi-tenant server.
- The host (Claude Desktop, Claude Code) is trusted. A compromised
  host can call any tool with any arguments — that's the host's
  threat model, not ours.
- Denial-of-service via legitimate but excessive tool calls is
  bounded by the host's rate limits and per-session timeouts;
  per-session backpressure inside the MCP is a roadmap item, not a
  security-tier promise.

## Known security-relevant artifacts

- `docs/adr/0006-patch-apply-safe-injection-audit.md` — full proof
  the git-shell-out path can't escalate.
- `domain/path_guard.py` — the shared allowlist helper. All
  path-accepting tools should route through `check_path_allowed()`.
- `presentation/image_safety_net.py` — hard 1900-px ceiling
  independent of env overrides, so a misconfigured `MCP_MAX_IMAGE_DIM`
  can't leak.
- `tests/unit/test_patch_apply_safe.py` — canary-file tripwires
  that break if anyone re-enables shell mode.

## Responsible disclosure timeline

We commit to:

- **Acknowledge** within 3 business days.
- **Triage** within 10 business days.
- **Patch** within the next minor release for non-critical,
  within 5 business days for critical (RCE, secret exfil, sandbox
  escape).
- **Coordinate disclosure** with the reporter. We will not publicly
  disclose until a fixed version is available.

## Hall of fame

Security reports that lead to a fix will be credited here (with the
reporter's consent).

_(No reports yet — this file is the policy, not the history.)_

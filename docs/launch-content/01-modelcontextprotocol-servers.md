# 1 · modelcontextprotocol/servers (the official list)

**URL:** https://github.com/modelcontextprotocol/servers
**Effort:** 20 minutes (one PR)
**Why first-priority:** Anthropic-curated. The canonical list every
MCP-aware host pulls from. Inclusion here drives downstream
discovery on PulseMCP, Smithery, mcp.so, and Claude Desktop's
"Browse connectors" panel.

## What you're submitting

A single new entry in their `README.md` under
**"🌎 Community Servers"** (alphabetical order — drop it under
the `f` letter).

## Step-by-step

1. Fork `modelcontextprotocol/servers` (top-right "Fork" button).
2. Edit `README.md` directly in the GitHub UI (pencil icon).
3. Find the **"🌎 Community Servers"** section.
4. Find the alphabetical position for `flutter-dev-agents` (it
   sorts between any existing `f*` entries; if there are none,
   between the last `e*` and the first `g*`).
5. Paste this line:

```markdown
- **[flutter-dev-agents](https://github.com/michal-giza/flutter-dev-agents)** - MCP server for autonomous Flutter testing on real iPhones and Android devices. 110 tools spanning Android (uiautomator2 + adb), iOS (WebDriverAgent + pymobiledevice3) and Flutter (Patrol + `flutter run --machine`). Cross-session device locking, tiered tool surface for small LLMs, production-grade with SBOM + CVE gating.
```

6. Commit message:

```
Add flutter-dev-agents to Community Servers
```

7. Open the PR. Title:

```
Add flutter-dev-agents (Flutter / mobile-device testing) to Community Servers
```

8. PR description (paste verbatim):

```markdown
Hi maintainers — proposing `flutter-dev-agents` for the Community
Servers list.

## What it is

An MCP server that lets autonomous agents build, deploy and test
Flutter apps on real iPhones and Android devices. First MCP in
this category — every other mobile-testing MCP I could find is
either iOS-simulator-only (`mobile-mcp` via idb), web-only
(Playwright MCPs), or desktop-only (computer-use).

## Why I think it fits Community Servers

- Implements MCP 2025-06-18 (tool annotations, outputSchema, contract snapshot test).
- 110 tools, tiered (BASIC=26 / INTERMEDIATE / EXPERT) so hosts with tool-count ceilings (Cursor=40, Claude Desktop UI) get a curated surface via `MCP_TOOL_TIER=basic`.
- Apache 2.0 license.
- Production hardening: CycloneDX SBOM in CI, pip-audit gating, structured JSON logs, Prometheus `/metrics`, k8s `/health` + `/ready`, Docker image, GitHub Action wrapper.
- 556 hermetic unit tests, 5 real-device tests gated on `MCP_REAL_DEVICE=1`.
- Documented top-10 production failure modes with concrete fixes (`docs/runbook.md`).

## Verification

- `pip install mcp-phone-controll` (or via the GitHub source).
- `claude mcp add phone-controll -- python -m mcp_phone_controll`
- `mcp_ping` tool returns server identity (version, git_sha, tool count) for sanity checking.

Thanks for reviewing — happy to incorporate any edits to the description.
```

## After it merges

- Verify your repo appears at https://modelcontextprotocol.io/servers (rebuilds from the README within ~24h).
- Star + watch the upstream repo so you see future spec changes.

## If the maintainers ask for changes

Common requests:

- **Trim the description.** They prefer one-liners (< 200 chars).
  Backup version:
  ```
  - **[flutter-dev-agents](https://github.com/michal-giza/flutter-dev-agents)** - Test Flutter apps on real iPhones and Android devices from any MCP-aware host. 110 tools, cross-session device locking, Patrol + WebDriverAgent + uiautomator2.
  ```
- **Move to a sub-category.** They sometimes group by tech (database, search, IDE…). "Mobile / Testing" is the natural one. Be flexible.
- **Remove the bullet list inside the README** (only allowed on the GH PR description, not the README entry).

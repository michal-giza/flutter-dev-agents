# 4 · Smithery.ai

**URL:** https://smithery.ai/new
**Effort:** 15 minutes
**Why:** Smithery is the most agent-builder-focused directory.
Their CLI (`npx @smithery/cli install`) is becoming a common
install path for developers who run multiple MCPs. Strong
SEO for "mcp" + framework queries.

## Submission method

Smithery uses a **`smithery.yaml`** manifest at the repo root.
Submit by adding one to your repo, then claim the listing on
their dashboard.

## Step 1 — add the manifest

Create `smithery.yaml` at the repo root with this content:

```yaml
# Smithery directory manifest. https://smithery.ai/docs
startCommand:
  type: stdio
  configSchema:
    type: object
    properties:
      MCP_TOOL_TIER:
        type: string
        enum: ["basic", "intermediate", "expert"]
        default: "basic"
        description: |
          Curates the tool surface. 'basic' (24 tools) fits under any
          host's tool-count ceiling — recommended starting point.
          'intermediate' adds ~16 more (build/install/test/dev-session).
          'expert' exposes all 110 tools.
      MCP_WDA_TEAM_ID:
        type: string
        description: |
          Apple Developer Team ID (10-char) for WebDriverAgent signing
          on physical iPhones. Required for iOS real-device testing.
      MCP_LOG_FORMAT:
        type: string
        enum: ["text", "json"]
        default: "text"
  commandFunction: |-
    (config) => ({
      command: "python",
      args: ["-m", "mcp_phone_controll"],
      env: {
        MCP_TOOL_TIER: config.MCP_TOOL_TIER || "basic",
        MCP_WDA_TEAM_ID: config.MCP_WDA_TEAM_ID || "",
        MCP_LOG_FORMAT: config.MCP_LOG_FORMAT || "text"
      }
    })
```

Commit + push that file (small follow-up PR after the launch one).

## Step 2 — claim the listing

1. Sign in at https://smithery.ai with GitHub.
2. Click **"Submit a server"** → paste your repo URL.
3. Smithery auto-detects the `smithery.yaml` and creates the listing.
4. Edit the **Description** field (paste verbatim):

```
The first MCP server for autonomous Flutter testing on real iPhones and Android devices.

110 tools spanning Android, iOS, and Flutter. Cross-session device locking, tiered tool surface for small LLMs, production-grade with SBOM and CVE gating. Apache 2.0.

Works with Claude Desktop, Claude Code, Cursor — or any MCP-aware host.
```

5. **Tags** (Smithery uses these for search):

```
flutter
mobile
ios
android
testing
patrol
ui-automation
agent
autonomous
claude
real-device
```

6. **Cover image**: upload your social preview if you have it.

## Step 3 — verify the install command works

Smithery's install command becomes:

```bash
npx -y @smithery/cli@latest install flutter-dev-agents --client claude
```

Test it on your machine BEFORE marking the listing as public. If
it errors, the dashboard has a "Test installation" button that
surfaces what failed.

## Common gotcha

If users hit `python: command not found` after Smithery install,
they're missing Python on PATH. Add a note in the listing:
"Requires Python 3.11+ on PATH."

## Listing URL after publish

`https://smithery.ai/server/flutter-dev-agents`

# 2 · PulseMCP

**URL:** https://www.pulsemcp.com/submit
**Effort:** 10 minutes
**Why:** Curated directory that feeds several MCP-host UIs
(including the pipeline behind Claude Desktop's "Browse
connectors" panel rollout). High signal-to-noise traffic — every
visitor is actively shopping for an MCP.

## What they ask for

A submission form with these fields. Paste exactly:

### Server name
```
flutter-dev-agents
```

### Short description (one line, ~100 chars)
```
MCP server for autonomous Flutter testing on real iPhones and Android devices.
```

### Long description (paste verbatim)
```
The first MCP server that lets autonomous agents build, deploy and test Flutter apps on real iPhones and Android devices.

110 tools spanning Android (uiautomator2 + adb), iOS (WebDriverAgent + pymobiledevice3) and Flutter (Patrol + `flutter run --machine`). Cross-session device locking lets multiple Claude windows operate on different phones without colliding. A tiered tool surface (BASIC=26 / INTERMEDIATE / EXPERT=110) keeps the server visible inside hosts that cap at 40 tools.

Production-grade out of the gate: CycloneDX SBOM, pip-audit CVE gating, structured JSON logs, Prometheus /metrics, k8s /health + /ready, Docker image, GitHub Action wrapper, top-10 failure-mode runbook. 556 hermetic tests + 5 real-device tests.

Works with Claude Desktop, Claude Code, Cursor, or any MCP-aware host. Also runs in fully autonomous mode against any OpenAI-compat local LLM via the HTTP adapter.
```

### Repository URL
```
https://github.com/michal-giza/flutter-dev-agents
```

### Installation command
```
pip install mcp-phone-controll
```

### MCP-host config example (if asked for a JSON snippet)
```json
{
  "mcpServers": {
    "phone-controll": {
      "command": "python",
      "args": ["-m", "mcp_phone_controll"],
      "env": { "MCP_TOOL_TIER": "basic" }
    }
  }
}
```

### Category (pick the closest if their taxonomy is rigid)
- Primary: **Testing**
- Secondary: **Mobile**
- Tertiary: **Developer Tools**

### Tags / keywords (if free-form)
```
flutter, mobile, ios, android, patrol, testing, autonomous, ui-automation, claude, agent, real-device
```

### Author / maintainer
```
Michal Giza · msquaregiza@gmail.com
```

### License
```
Apache-2.0
```

### Logo / icon URL (if they ask)
Use your repo's social preview image once you've uploaded it:
```
https://repository-images.githubusercontent.com/<repo-id>/social-preview
```
or — easier — leave blank and let them pull the OG image automatically.

## Important boxes to tick

- [x] **"This MCP is open source"**
- [x] **"I am the maintainer"**
- [x] **"Allow indexing in MCP host UIs"** (this is what gets you into Claude Desktop's connectors panel)

## After submission

PulseMCP typically reviews within 48–72 hours. Watch for a welcome
email; they sometimes request a small description tweak.

Once approved, your entry appears at:
`https://www.pulsemcp.com/servers/flutter-dev-agents`

Save that URL — Variant C of the LinkedIn post links to it.

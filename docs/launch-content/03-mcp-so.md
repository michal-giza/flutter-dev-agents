# 3 · mcp.so

**URL:** https://mcp.so/submit
**Effort:** 10 minutes
**Why:** Community marketplace, Chinese and EU developer reach.
Auto-detects new releases on tagged repos but explicit submission
gets you placement faster + curated featured slots.

## Submission fields

### Name
```
flutter-dev-agents
```

### Tagline (~80 chars, used in cards)
```
MCP for autonomous Flutter testing on real iPhones and Android devices
```

### Description (markdown, ~500 chars renders well in their cards)
```markdown
The first MCP server that lets autonomous agents build, deploy and test Flutter apps on real iPhones and Android devices.

**Highlights**
- 110 tools across Android (uiautomator2 + adb), iOS (WebDriverAgent + pymobiledevice3), Flutter (Patrol + `flutter run --machine`).
- Tiered tool surface (BASIC / INTERMEDIATE / EXPERT) — set `MCP_TOOL_TIER=basic` to fit under Cursor/Claude-Desktop tool-count ceilings.
- Cross-session device locks so multiple Claude windows don't collide.
- Production-ready: CycloneDX SBOM, pip-audit gating, JSON logs, Prometheus metrics, Docker image.
- Apache 2.0, 556 tests, MCP 2025-06-18 compliant.

Works with Claude Desktop, Claude Code, Cursor, or any MCP-aware host.
```

### GitHub URL
```
https://github.com/michal-giza/flutter-dev-agents
```

### Install instructions (they have a dedicated field)
```bash
# Stdio (Claude Desktop / Claude Code)
pip install mcp-phone-controll
claude mcp add phone-controll -- python -m mcp_phone_controll

# HTTP (k8s / Docker)
docker run -p 8765:8765 ghcr.io/michal-giza/mcp-phone-controll:0.2.1
```

### Categories (mcp.so taxonomy)
- **Developer Tools**
- **Testing**
- **Mobile**

### Tags
```
flutter, ios, android, mobile-testing, patrol, claude, anthropic, agent, autonomous, ui-automation, webdriveragent, uiautomator2, dart
```

### Featured screenshot (optional, but recommended)
Your social preview image works. Spec: 1280×640, < 1 MB.

### Demo video URL (optional)
Leave blank for now — populate once you record the 30-second demo.

## Authentication

mcp.so requires GitHub OAuth login before submission. Use the
same account that owns the repo so they can verify maintainership
automatically.

## Listing URL after approval

`https://mcp.so/server/flutter-dev-agents`

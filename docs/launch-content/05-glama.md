# 5 · Glama.ai

**URL:** https://glama.ai/mcp/servers (top-right "Submit server" button)
**Effort:** 10 minutes
**Why:** Glama's MCP directory is search-driven (you can query
"flutter testing" and get filtered results), which makes it
valuable specifically for your niche keywords.

## Submission flow

1. Sign in with GitHub at https://glama.ai.
2. Click **"Submit MCP Server"**.
3. Paste your repo URL → Glama auto-pulls README + metadata.
4. Edit these fields:

### Title
```
flutter-dev-agents
```

### Tagline (~120 chars)
```
First MCP server for autonomous Flutter testing on real iPhones and Android devices. 110 tools, Apache 2.0.
```

### Description (paste verbatim — supports markdown)
```markdown
An MCP server that lets autonomous agents build, deploy and test Flutter apps on real iPhones and Android devices.

## What it covers

- **Android**: uiautomator2 + adb. Polish-localization-aware `tap_text` (NBSP fold, NFC normalization, case-insensitive substring). Samsung One UI tap fallback via direct `adb shell input tap`.
- **iOS**: WebDriverAgent + pymobiledevice3. iOS 17+ `--rsd` routing via tunneld. `setup_webdriveragent(team_id=...)` for physical-device signing.
- **Flutter**: Patrol-driven `tap_and_verify`, `assert_no_errors_since`, hot-reload via `flutter run --machine`, dev-session lifecycle, debug-log streaming.

## Why it's different

- **Tiered tool surface** (`MCP_TOOL_TIER=basic|intermediate|expert`) so the 110-tool catalog fits under any host's tool-count ceiling.
- **Cross-session device locks** so 4 concurrent Claude windows can drive 4 phones without colliding.
- **Defense-in-depth image cap** that survived three production "2000 px API limit" incidents.
- **`inspect_image_safety` + `compress_png` on BASIC tier** for handling screenshots produced by other MCPs (computer-use, raw adb).
- **Production-grade**: CycloneDX SBOM, pip-audit CVE gating, structured JSON logs, Prometheus metrics, k8s health/ready, Docker image, GitHub Action wrapper.

## Tested with

Claude Desktop, Claude Code, Cursor. Also runs autonomous against any OpenAI-compat local LLM via the HTTP adapter.

[GitHub](https://github.com/michal-giza/flutter-dev-agents) · [PyPI](https://pypi.org/project/mcp-phone-controll/) · [Changelog](https://github.com/michal-giza/flutter-dev-agents/blob/main/CHANGELOG.md)
```

### Category
- **Testing & QA**
- **Mobile Development**

### Keywords / tags
```
mcp, model-context-protocol, flutter, dart, android, ios, mobile, patrol, ui-automation, webdriveragent, uiautomator2, claude, anthropic, agent, autonomous, real-device, testing
```

### License
```
Apache-2.0
```

### Maturity / stability
- **Production-ready** (v0.2.1, 556 tests passing, used internally by maintainer for daily work)

### Operating systems supported
- [x] macOS (full functionality — iOS + Android)
- [x] Linux (Android-only)
- [ ] Windows (not supported — adb works but WDA needs Xcode)

## Glama's "Quality score" — what they check

They auto-grade submitted MCPs on:

1. **README quality** — yours has badges, quick-start, integrations. ✅
2. **Test coverage** — `tests/unit` count is in the README. ✅
3. **License presence** — LICENSE file at root. ✅
4. **Activity** — commits in last 30 days. ✅
5. **Documented config schema** — your `smithery.yaml` covers this. ✅

Aim for the "Quality verified" badge — it boosts ranking in their
search results.

## Listing URL after approval
`https://glama.ai/mcp/servers/flutter-dev-agents`

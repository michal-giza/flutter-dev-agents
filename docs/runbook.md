# Production runbook

Operational playbook for `mcp-phone-controll`. Aimed at: on-call
engineer or ops team who didn't write the code but now has to keep
it running.

This document covers the top failure modes seen in the field plus
the standard deployment / monitoring / recovery operations.

## Quick diagnosis

```
# 1. Is the MCP alive?
curl -fsS http://<host>:8765/health

# 2. Is it ready to serve?
curl -fsS http://<host>:8765/ready

# 3. What version is running?
curl -fsS http://<host>:8765/health | jq '.git_sha,.version'

# 4. Are screenshots being capped properly?
curl -fsS http://<host>:8765/metrics | grep mcp_image_cap_px
# Expected: mcp_image_cap_px 1600  (or whatever MCP_MAX_IMAGE_DIM is set to)

# For stdio mode (Claude Desktop / Claude Code):
# Inside the chat, ask the agent to call mcp_ping.
# Expected envelope contains git_sha, image_cap_px, n_tools.
```

## Top 10 production failures (and the fix)

### 0. Claude Desktop Connectors panel shows "no tools available"

**Cause**: Claude Desktop's UI silently drops the tool inventory when
our 109-tool surface exceeds whatever ceiling the host applies (Cursor
documents 40; Claude Desktop is undocumented). The MCP server delivers
all 109 tools — the Connectors UI just doesn't display them.

**Fix**: set `MCP_TOOL_TIER=basic` in the env block. The server then
advertises only the 24 BASIC tools, well under any ceiling.

```bash
CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
cp "$CONFIG" "$CONFIG.bak.$(date +%s)"
jq '.mcpServers["phone-controll"].env.MCP_TOOL_TIER = "basic"' "$CONFIG" \
    > "$CONFIG.tmp" && mv "$CONFIG.tmp" "$CONFIG"
# Then cmd+Q Claude Desktop and start a NEW chat.
```

Other tier values:
- `intermediate` — BASIC + INTERMEDIATE (~40 tools)
- `expert` or `all` or unset — all 109 (default)

Verify with `mcp_ping` (always BASIC tier) — if it returns, you're
fixed. Calling a tool that's NOT in the advertised set still works
for clients that know its name; the filter only affects what's
listed.

### 1. "An image in the conversation exceeds the dimension limit (2000px)"

**Cause** (in order of field frequency):

1. **The agent used raw `adb exec-out screencap -p` via Bash instead
   of `take_screenshot`.** Our 1600px cap runs inside the MCP — when
   the agent goes around it through Bash, the cap doesn't fire. Pixel
   emulators ship at 1080×2400, blowing the 2000px limit on every
   shot.

   **Fix**: instruct the agent to use `take_screenshot` exclusively.
   If a bot routinely reaches for raw adb (small models often do
   when they've already used `Bash` for `adb shell input tap`), call
   `compress_png(path=…)` on the raw output before reading it. Both
   tools are on the BASIC tier so they're always available.

   May 2026 incident: an overnight automation accumulated 5 raw-adb
   PNGs at 2400px each, crashed on the 6th. The MCP itself was
   working correctly — the agent never invoked it for screenshots.

2. **Stale subprocess running pre-`fe00b85` code with the 1920 cap.**

**Fix**:
```bash
# stdio (Claude Desktop / Code):
# Full app quit (cmd+Q on macOS) + relaunch. NOT close window.
pkill -f "mcp_phone_controll"   # kill any orphans
# Then relaunch the host.

# Verify recovery: ask agent to call mcp_ping. Expect image_cap_px=1600.
```

If `image_cap_px` is already 1600 but the error persists, the leak
is from a different MCP in the same conversation (e.g.
`computer-use`). Use `compress_png(path=…)` from this MCP on the
offending file.

### 2. "Request too large (max 32MB)"

**Cause**: cumulative byte budget of all images in the conversation
exceeds 32MB.
**Fix**:
```bash
# One-shot maintenance — re-compress all historical artifacts:
.venv/bin/python -m scripts.audit_artifact_dimensions \
    --root ~/.mcp_phone_controll/sessions \
    --cap --max-dim 1600 --max-bytes-kb 250
```
Then start a fresh agent session. The shipped agent will from now
on auto-cap with the palette-mode compressor (3-5× smaller per shot).

### 2b. `setup_webdriveragent` fails with "requires a development team"

**Cause**: WDA build needs `DEVELOPMENT_TEAM` for physical-device
code-signing. The Appium WDA project ships with empty signing
settings on purpose, so xcodebuild fails until a team is selected.

**Symptom**:
```
error: Signing for 'WebDriverAgentRunner' requires a development team.
Select a development team in the Signing & Capabilities editor.
```

**Fix**: pass `team_id` (your 10-char Apple Developer Team ID):

```
setup_webdriveragent(udid="…", team_id="ABCDE12345")
```

Or set it once and forget:

```bash
export MCP_WDA_TEAM_ID=ABCDE12345
# (add to ~/.zshrc to persist)
```

Find your team ID in: Xcode → Settings → Accounts → click team →
"Manage Certificates" (the 10-char string above the table). Or:

```bash
xcrun altool --list-providers \
    -u <your-apple-id> -p @keychain:AC_PASSWORD 2>/dev/null \
    | grep -E "^\s+[A-Z0-9]{10}\s"
```

The MCP surfaces `next_action: "provide_team_id"` when this
specific signing error is detected so agents know exactly what to
do next.

### 2c. `tap_text` misses Polish/French diacritics or NBSP-separated strings

**Cause**: Android localization sometimes uses U+00A0 (NO-BREAK SPACE)
or U+202F (NARROW NBSP) between words for typography. Visually
identical to ASCII space on screen, byte-unequal in the dump. Same
class of bug as combining diacritics (NFC vs NFD).

**Symptom**: `tap_text("Podczas używania aplikacji")` returns
`UiElementNotFoundFailure` even though the button is visible.

**Fix (already in v0.2.1+)**: the dump-scan fallback now NFC-normalizes,
folds NBSP/NNBSP/thin space to ASCII, strips zero-width chars, and
case-folds in substring mode. No agent action needed — call as
normal:

```
tap_text(text="Podczas używania aplikacji")
```

If it still misses on a specific string, the dump may have it split
across multiple text nodes (Flutter widget composition). Workaround:
match a shorter unique substring with `tap_text(text="używania", exact=false)`.

### 3. iPhone 17 simulator: `'NoneType' has no attribute 'make_http_connection'`

**Cause**: WebDriverAgent not running on the simulator.
**Fix**: agent should call `start_wda_on_simulator(udid="…")`. If
that returns `next_action: "setup_webdriveragent"`, run that one
first.

### 4. iOS physical device: `next_action: "start_tunneld"`

**Cause**: `pymobiledevice3 remote tunneld` daemon not running.
**Fix**:
```bash
# Check whether pymobiledevice3 is installed:
which pymobiledevice3
# If empty: pipx install pymobiledevice3

# Start the daemon (leave it running):
sudo $(which pymobiledevice3) remote tunneld
```

### 5. `select_device` returns `DeviceBusyFailure`

**Cause**: another session holds the lock. Stale lock if the holder
process died.

**Diagnosis**:
```bash
# Inside the agent:
list_locks    # shows all locks with holder session_id + pid

# From a shell:
ls ~/.mcp_phone_controll/locks/   # raw view
```

**Fix**:
```bash
# If the holder pid is gone (process died), the lock auto-cleans on
# next list_locks. If it's truly stuck:
force_release_lock(serial="<serial>")     # via agent
# or
rm ~/.mcp_phone_controll/locks/<serial>.lock   # manual
```

### 6. MCP timed out on first `build_app`

**Cause**: first-run Gradle pulls AGP + AAPT2 + KGP, easily 10+
minutes on a slow link. Our default timeout (1500 s = 25 min) covers
this, but the host's MCP-call timeout may be shorter.

**Fix**: run `gradle dependencies` once via bash before the first
`build_app` call. Subsequent `build_app` runs are 30-90 s.

### 7. `tap_text` refused with `next_action: "use_patrol"`

**Cause**: a Patrol session is active; raw `tap_text` is blocked to
prevent drift from the Patrol-driven test state.

**Fix**: either route through `run_patrol_test`, or — for true OS
dialogs (Allow camera?, etc.) — pass `system=true`:
```
tap_text(text="Allow", system=true)
```

### 8. CVE detected by CI security workflow

**Where**: `Security audit` job in `.github/workflows/ci.yml`.
**Fix**:
1. Read the pip-audit output — does the affected package have a
   `Fix Versions` column populated?
   - YES: pin the new version in `pyproject.toml`. Commit + push.
   - NO: the upstream hasn't patched yet. Evaluate the vulnerability
     against our actual usage; if non-applicable, add to the
     `--ignore-vuln` list in the workflow with a comment explaining
     why. Re-evaluate quarterly.
2. After the fix, ensure pip-audit exits 0 locally:
   ```bash
   cd packages/phone-controll
   .venv/bin/pip-audit --skip-editable --ignore-vuln <ignored-ids…>
   ```

### 9. `/ready` returns 503

**Cause**: dispatcher has no tools (config broken) OR no image-cap
backend (cv2/PIL/sips all missing).

**Diagnosis**:
```bash
curl -fsS http://<host>:8765/ready | jq .reasons
```

**Fix**:
- "no tools registered": something's very wrong; restart the
  container, then check stderr for import errors.
- "no image-cap backend available":
  ```bash
  pip install pillow
  # then restart the process
  ```

### 10. Orphaned `flutter run --machine` / `xcodebuild test-without-building` processes

**Cause**: SIGTERM not delivered cleanly; signal-handler bypass.
**Fix**:
```bash
pkill -f "flutter.*--machine"
pkill -f "xcodebuild.*test-without-building"
```
Then restart Claude Desktop / Claude Code so the dispatcher
re-initializes child-process tracking.

## Deployment

### Stdio mode (Claude Desktop, Claude Code)

```json
// ~/Library/Application Support/Claude/claude_desktop_config.json
{
  "mcpServers": {
    "phone-controll": {
      "command": "/path/to/.venv/bin/python",
      "args": ["-m", "mcp_phone_controll"]
    }
  }
}
```

After every code change: **fully quit** Claude Desktop (cmd+Q, not
close window) and relaunch.

### HTTP mode (Docker / Kubernetes)

```bash
# Image build (see packages/phone-controll/Dockerfile):
docker build -t mcp-phone-controll:0.2.0 packages/phone-controll/

# Run:
docker run -d --name mcp \
  -p 8765:8765 \
  -e MCP_HTTP_API_KEY=$(openssl rand -hex 32) \
  -e MCP_LOG_FORMAT=json \
  mcp-phone-controll:0.2.0

# Kubernetes liveness:
#   livenessProbe: { httpGet: { path: /health, port: 8765 } }
# Kubernetes readiness:
#   readinessProbe: { httpGet: { path: /ready, port: 8765 } }
# Prometheus scrape:
#   metricsPath: /metrics
```

## Monitoring

### Metrics to alert on

| Metric | Threshold | Why |
|---|---|---|
| `mcp_image_backends_available` | == 0 | every screenshot will fail the 2000px gate |
| `mcp_image_cap_px` | > 1900 | hard ceiling bypassed — config drift |
| `mcp_tools_total` | < expected | tool registration broken |
| `up{job="mcp-phone-controll"}` | == 0 for > 1 min | process down |

### Logs

`MCP_LOG_FORMAT=json` produces one JSON object per line on stderr.
Pipe to your aggregator (Datadog, Honeycomb, Loki, …).

Key events to alert on:
- `level=error event=*` — any error
- `level=warn event=image_safety_net_refused` — cap pipeline broken
- `level=warn event=tool_dispatch_end ok=false` — failure rate
  threshold (e.g. > 5%/5min)

## Security incidents

See `SECURITY.md` for the disclosure policy. If you suspect an
active compromise:

1. Stop the affected MCP processes:
   ```bash
   pkill -f "mcp_phone_controll"
   ```
2. Capture forensics:
   ```bash
   tar czf /tmp/mcp-forensics-$(date +%s).tgz \
       ~/.mcp_phone_controll/sessions/ \
       ~/.mcp_phone_controll/locks/
   ```
3. Rotate `MCP_HTTP_API_KEY` if it was in use.
4. Email `msquaregiza@gmail.com` with subject
   `[flutter-dev-agents SECURITY] active compromise` — include the
   forensics tarball.

## Upgrade procedure

```bash
# 1. Read the CHANGELOG.md entry for the new version.
# 2. Update the config — version pin if you use one.
# 3. Stage: deploy to a non-production env first.
# 4. Verify: hit /health and /ready; confirm version, git_sha,
#    image_backends, tools count match expectations.
# 5. Production: rolling restart.
# 6. Watch: dispatch error rate + image_safety_net_refused for 1 hour.
```

If something breaks, the previous version's image is the rollback.
Stdio users: revert the claude_desktop_config.json to the prior
venv path.

## Where to look for more

- `README.md` — overview + getting started
- `SECURITY.md` — threat model + disclosure
- `CONTRIBUTING.md` — how to add a new tool / framework
- `docs/code-review-*.md` — historical reviews documenting why
  each design choice is shaped the way it is
- `docs/adr/` — Architecture Decision Records for load-bearing
  choices (image cap, middleware chain, version handshake, etc.)
- `docs/walkthrough-vscode-test.md` — end-to-end test script you
  can copy-paste into a Claude session
- `docs/teaching/` — pedagogical materials for the public course

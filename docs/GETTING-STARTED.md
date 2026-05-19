# Getting started — first 15 minutes

If you've never used `mcp-phone-controll` before, this is the doc.
By minute 15 you'll have:

- The MCP installed and registered with Claude Desktop or Claude Code.
- A real Android phone (or emulator) under agent control.
- A screenshot, a tap, and a verified outcome — all driven from a
  Claude conversation, no Python code written by you.

If iOS is your priority, skip ahead to **[iOS prerequisites](#ios)**
before starting; iOS needs ~30 extra minutes of one-time signing
setup that this tutorial doesn't cover.

> **What's "MCP"?** Model Context Protocol — the standard for
> giving an AI agent safe, structured access to tools and data.
> Claude Desktop / Claude Code / Cursor all speak it. This MCP
> server exposes 110 tools for driving phones.

---

## Prerequisites checklist (5 minutes)

Tick each before you start:

- [ ] **macOS 13+ or Linux** (Windows works for the package itself
      but Android device control needs adb and iOS needs Xcode).
- [ ] **Python 3.11+** on PATH (`python --version`).
- [ ] **Claude Desktop OR Claude Code** installed.
- [ ] **One Android device** plugged in via USB with **Developer
      Options + USB Debugging** enabled; OR an Android emulator
      already created (`avdmanager list avd`).
- [ ] **`adb`** on PATH: `brew install --cask android-platform-tools`
      (macOS) or `apt install android-tools-adb` (Linux).

Verify the device is visible:

```bash
adb devices
# List of devices attached
# R3CYA05CHXB    device           ← real phone
# emulator-5554  device           ← or an emulator
```

If the device shows `unauthorized`, tap **Allow** on the phone's
USB-debug prompt. If it shows nothing, USB debugging isn't
enabled — the [Android docs walk you through it
here](https://developer.android.com/studio/debug/dev-options#enable).

---

## Install (2 minutes)

```bash
pip install mcp-phone-controll
```

Or, for a development checkout with editable install:

```bash
git clone https://github.com/michal-giza/flutter-dev-agents.git
cd flutter-dev-agents/packages/phone-controll
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,ar,http]"
```

Sanity-check that the entry-points work:

```bash
python -m mcp_phone_controll --help
```

You should see the stdio MCP usage info.

---

## Register with Claude (3 minutes)

### Option A — Claude Desktop (recommended for first-time users)

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`
on macOS (`%APPDATA%\Claude\claude_desktop_config.json` on Windows;
`~/.config/Claude/claude_desktop_config.json` on Linux):

```json
{
  "mcpServers": {
    "phone-controll": {
      "command": "python",
      "args": ["-m", "mcp_phone_controll"],
      "env": {
        "MCP_TOOL_TIER": "basic"
      }
    }
  }
}
```

> **Why `MCP_TOOL_TIER=basic`?** The full server exposes 110 tools.
> Claude Desktop's UI has an undocumented tool-count ceiling — if
> you exceed it, the Connectors panel shows "no tools available".
> `basic` exposes a curated 26-tool subset that fits under every
> known host's ceiling. You can switch to `intermediate` or
> `expert` later. See [`CONFIGURATION.md`](CONFIGURATION.md).

Fully quit Claude Desktop (cmd+Q on macOS — closing the window is
not enough) and relaunch. Open the **🔌 Connectors** panel — you
should see `phone-controll` with 26 tools.

### Option B — Claude Code (CLI)

```bash
claude mcp add phone-controll --scope user \
  -- python -m mcp_phone_controll
```

Restart your shell. Run `claude mcp list` to confirm:

```
phone-controll
  Type: stdio
  Status: ✓ Connected (26 tools)
```

---

## Hello-world: take a screenshot (3 minutes)

Open Claude (Desktop or Code) and paste this exact prompt:

```
Using the phone-controll MCP, please:

1. Run mcp_ping and tell me the version and tool count.
2. Call list_devices and pick the first one as my target.
3. Call select_device on that serial.
4. Take a screenshot with label "hello-world".
5. Tell me where the file was saved.

Read the screenshot back to me at the end.
```

What should happen, in order:

1. **`mcp_ping`** returns `{ok: true, version: "0.2.2",
   tool_count: 26}`. If it doesn't, the MCP isn't connected —
   re-do the Claude Desktop / Claude Code registration step.

2. **`list_devices`** returns an array containing your phone's
   serial. For a Galaxy S25 it'll look like `R3CYA05CHXB`. For an
   emulator it'll look like `emulator-5554`.

3. **`select_device`** acquires a filesystem lock on that device
   so other Claude sessions can't drive it concurrently. Returns
   `ok: true`.

4. **`take_screenshot`** captures the device screen, caps it at
   1600 px long-edge, and saves under
   `~/.mcp_phone_controll/sessions/<sid>/screenshot-hello-world-*.png`.

5. The agent reads the PNG back and you see it in the conversation.

If any step fails, the failure envelope has a `next_action` field
telling Claude exactly what to do next. Don't fight the error —
the structured errors are the contract.

---

## A real flow: tap-and-verify (2 minutes)

Once the hello-world worked, try a slightly meatier prompt:

```
Using phone-controll:

1. Open the Settings app on the connected device.
2. Tap on "Network & internet" (or whatever the equivalent is on
   this OS version — use exact=False if the wording differs).
3. Take a screenshot and confirm the screen now shows network
   settings.
4. Release the device.
```

This exercises:

- `launch_app(package_id="com.android.settings")` — opens Settings.
- `tap_text(text="Network & internet", exact=False)` — taps the menu.
- `take_screenshot` — captures the result.
- `release_device` — frees the lock for the next session.

The `tap_text` tool handles NFC normalization, Polish/French
NBSP folding, and falls back to a UI-tree XML scan if the
primary selector path misses. You don't need to think about any
of that.

---

## Where to go next

| If you want to… | Read this |
|---|---|
| **Avoid the 4 most common pitfalls** | [`operational-gotchas.md`](operational-gotchas.md) — 5 minute read, will save you hours |
| **Test iOS devices** | [`ios_setup.md`](ios_setup.md) — Xcode + WDA + tunneld setup |
| **Run automated test plans (YAML)** | [`../examples/README.md`](../examples/README.md) + the 6 templates in `examples/templates/` |
| **Integrate from n8n / CI / a custom agent** | [`../INTEGRATIONS.md`](../INTEGRATIONS.md) |
| **Tune behavior via env vars** | [`CONFIGURATION.md`](CONFIGURATION.md) |
| **Run the full end-to-end walkthrough** | [`walkthrough-vscode-test.md`](walkthrough-vscode-test.md) — a complete Flutter dev session driven by the agent |
| **Diagnose a production failure** | [`runbook.md`](runbook.md) |
| **Add a new framework or tool** | [`adding_a_framework.md`](adding_a_framework.md), [`adding_an_mcp.md`](adding_an_mcp.md) |
| **Common questions** | [`FAQ.md`](FAQ.md) |

---

## <a id="ios"></a>iOS prerequisites (skip if Android-only)

iOS device control requires Apple's developer tooling, which is
**macOS-only**. Plan ~30 minutes for first-time setup:

1. **Xcode** installed (App Store) + Command Line Tools (`xcode-select --install`).
2. **Apple Developer account** (free tier is enough for personal-device testing).
3. **Developer Mode** ON in iOS Settings → Privacy & Security.
4. **pymobiledevice3** installed: `pipx install pymobiledevice3`.
5. **tunneld daemon** running (for iOS 17+): `sudo pymobiledevice3 remote tunneld`.
6. **WebDriverAgent** built for your device:
   ```
   setup_webdriveragent(udid="<your-udid>", team_id="<your-team-id>")
   ```

[Full step-by-step in `ios_setup.md`](ios_setup.md). The doctor
tool also helps: ask Claude to run `check_environment` — it
returns red items with the exact fix commands.

---

## Troubleshooting the first 15 minutes

| Symptom | Cause | Fix |
|---|---|---|
| Claude Desktop shows "no tools available" | Tool-count ceiling | Confirm `MCP_TOOL_TIER=basic` is in the env block + fully quit (cmd+Q) and relaunch |
| `list_devices` returns empty | adb not seeing the device | Check `adb devices` from a terminal first; if empty, USB-debug isn't authorized — tap "Allow" on the phone |
| `take_screenshot` errors with "2000px API limit" | A different MCP fed Claude an oversized PNG | Call `compress_png(path="…")` on the offending file; it's BASIC tier so always available |
| iOS: `tap` returns `WdaUnreachable` | WebDriverAgent isn't running | `setup_webdriveragent` first (physical) or `start_wda_on_simulator` (sim) |
| `select_device` returns `DeviceBusyFailure` | Another Claude session holds the lock | `list_locks` to see who; `force_release_lock(serial="…")` if the holder is gone |

Anything else → [`runbook.md`](runbook.md) covers the top 10
production failure modes with the exact remediation each one
needs.

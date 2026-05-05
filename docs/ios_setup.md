# iOS prerequisites — physical device setup

iOS 17+ moved most "developer" services (screenshot, app launch, syslog stream, instruments) onto a per-host **tunnel** that the macOS-side `tunneld` daemon serves. On top of that, **WebDriverAgent** is the runtime your tap-driven UI tests need to actually move the focus dial, capture photos, etc. The four prerequisites below are one-time per device (except `tunneld`, which you run once per terminal session). Once they're satisfied, every iOS tool the MCP exposes works.

If you skip any, the failure envelopes will tell you which one — `next_action: "start_tunneld"` from `take_screenshot` is the obvious tell that #3 is missing.

> **TL;DR**, in order:
> 1. Enable **Developer Mode** on the phone (`amfi enable-developer-mode` + reboot + Settings toggle).
> 2. Mount the **Developer Disk Image** (`mounter auto-mount`).
> 3. Start `**tunneld**` (`sudo pymobiledevice3 remote tunneld` — leave running).
> 4. Build **WebDriverAgent** for the device (`xcodebuild build-for-testing` — or call the MCP tool `setup_webdriveragent`).

---

## 1. Developer Mode

Required since iOS 16 for any developer-tier service.

```bash
.venv/bin/pymobiledevice3 amfi enable-developer-mode --udid <UDID>
```

The phone reboots. After it boots:

1. **Settings → Privacy & Security → Developer Mode → On**
2. Phone reboots again, asks you to confirm.
3. Enter your passcode and tap **Turn On**.

Verify:

```bash
.venv/bin/pymobiledevice3 amfi developer-mode-status --udid <UDID>
# expected: true
```

If `developer-mode-status` keeps returning `false` after a reboot, the toggle isn't actually flipped. Settings → Privacy & Security → scroll → toggle.

---

## 2. Developer Disk Image (DDI)

Required for every developer service except syslog (which routes through the tunnel below). One-time per iOS major version.

```bash
.venv/bin/pymobiledevice3 mounter auto-mount --udid <UDID>
```

Verify:

```bash
.venv/bin/pymobiledevice3 mounter list --udid <UDID>
# expected: a "Personalized" or "DeveloperDiskImage" entry with isMounted: true
```

If iOS major version is newer than your installed Xcode, auto-mount can fail (Xcode ships the DDI). Update Xcode from the App Store, then unmount + remount:

```bash
.venv/bin/pymobiledevice3 mounter umount-developer --udid <UDID>
.venv/bin/pymobiledevice3 mounter auto-mount --udid <UDID>
```

---

## 3. tunneld — the per-host iOS 17+ tunnel daemon

**Leave this running in a separate terminal for every session that uses physical-iPhone screenshot / launch / over-tunnel syslog.** It's the most common gotcha in our setup.

```bash
sudo /Users/<you>/Desktop/flutter-dev-agents/packages/phone-controll/.venv/bin/pymobiledevice3 remote tunneld
```

You should see:

```
INFO:     Started server process [...]
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:49151 (Press CTRL+C to quit)
```

The MCP's `check_environment` tool actively probes `127.0.0.1:49151` — if tunneld isn't running, the report's `ios_tunneld` check is red with the exact `sudo` command in `fix`. Likewise, `take_screenshot` against an iPhone returns `next_action: "start_tunneld"` when the daemon isn't reachable, with the command in `details.fix_command`.

Common tunneld pitfalls:

- "QUIC protocol error" — sometimes shows up while tunneld bootstraps; usually self-resolves on retry.
- Started but no devices listed — phone isn't trusted to this host. Unplug, replug, tap "Trust this computer" on the phone.
- macOS keeps killing it — check System Settings → Privacy & Security → Network for any prompts.

---

## 4. WebDriverAgent — required for tap-driven iOS UI

Without WDA, the MCP can install / launch / read logs / screenshot but cannot **drive the UI** (move sliders, tap buttons, type into text fields, dismiss the ATT prompt). For Patrol tests the rendering pipeline is exercised but the user-flow timing isn't.

### Option A — let the MCP do it

```python
# from any Claude Code session against your device
setup_webdriveragent(udid="00008120-001A42542E30201E")
```

This clones https://github.com/appium/WebDriverAgent.git into `~/.mcp_phone_controll/WebDriverAgent` and runs `xcodebuild build-for-testing` against your device. Long-running — expect minutes. The tool returns the tail of stdout/stderr on success or a typed `FlutterCliFailure` with `next_action: "check_xcode_signing"` on a signing problem.

### Option B — manual (matches what you already discovered)

```bash
git clone https://github.com/appium/WebDriverAgent.git
cd WebDriverAgent
xcodebuild build-for-testing -project WebDriverAgent.xcodeproj \
  -scheme WebDriverAgentRunner \
  -destination "platform=iOS,id=<UDID>"
```

After it succeeds, the runner is installed on the device. The MCP's `WdaUiRepository` connects via usbmux (no iproxy needed) the next time a UI tool fires.

### When WDA build fails

The two common causes:

- **No matching provisioning profile.** Open `WebDriverAgent.xcodeproj` in Xcode, select the `WebDriverAgentRunner` target, choose a development team, then re-run `setup_webdriveragent`.
- **Xcode CLT not pointed at full Xcode.** Run `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer`.

---

## Verifying everything is good

From any Claude Code session:

```
1. check_environment           — ios_tunneld and adb/flutter all green
2. list_devices                — your iPhone appears with platform: ios
3. select_device <UDID>        — acquires the lock
4. take_screenshot              — produces a real PNG
5. dump_widget_tree (after a debug session) — proves WDA + tunneld together
```

If anything fails, the failure envelope's `next_action` and `details.docs_url` point back here.

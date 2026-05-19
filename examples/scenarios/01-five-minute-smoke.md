# Scenario 1 — Five-minute smoke test

**You have**: one connected Android device, a Flutter app already
installed on it.
**You want**: confirm the MCP + device + app are all healthy
before starting your day.

## What you'll do

1. Confirm the MCP is alive (`mcp_ping`).
2. Confirm the device is locked to your session.
3. Confirm the app launches and renders.
4. Capture a baseline screenshot for the day.
5. Release the device.

## Prompt (paste into Claude)

```
Using phone-controll, run my morning smoke test:

1. mcp_ping — tell me the version + tool count.
2. list_devices and pick the first Android device.
3. select_device on that serial.
4. prepare_for_test for com.example.myapp (clears data, grants
   common permissions).
5. launch_app for com.example.myapp.
6. take_screenshot with label "morning-smoke".
7. assert_no_errors_since 30 (last 30 seconds).
8. release_device.

If any step fails, STOP and tell me exactly which next_action
the failure surfaced.
```

## Expected output

8 tool calls, all `ok: true`, total wall-clock ~12 seconds:

```
mcp_ping             0.04s  v0.2.2 / 26 tools / git abc1234
list_devices         0.18s  [Galaxy S25 R3CYA05CHXB]
select_device        0.12s  ok=true
prepare_for_test     3.20s  data cleared, permissions granted
launch_app           1.40s  ok=true
take_screenshot      0.42s  /sessions/<sid>/screenshot-morning-smoke-001.png
assert_no_errors_since 0.30s ok=true (0 errors in last 30s)
release_device       0.05s  ok=true
```

The PNG is your "the app launched cleanly today" baseline.

## What to read in the response

| Field | Why it matters |
|---|---|
| `mcp_ping.data.image_cap_px` | Should be 1600. If higher, you're running a stale subprocess. |
| `take_screenshot.data.path` | Where the baseline went. Save the path; you can `compare_screenshot` against it later. |
| `assert_no_errors_since.data.matches` | Should be `[]`. Anything in the array is a bug to triage. |

## Common variations

- **Two phones plugged in?** Pass the serial explicitly to step 3:
  `select_device on serial "R3CYA05CHXB"`. Otherwise the agent
  picks the first one alphabetically.
- **No app installed yet?** Add a step before `prepare_for_test`:
  `install_app from bundle_path "<path to your APK>"`.
- **You want screenshots of multiple screens?** Add taps between
  steps 6 and 7. The Polish-locale scenario (`02-`) shows the
  pattern.

## Total tool calls in BASIC tier

8 of the 8 are BASIC tier — no `MCP_TOOL_TIER=intermediate` needed.
This scenario works on Claude Desktop with the default
configuration.

## Make it a daily routine

Save the prompt above as `~/.mcp_phone_controll/prompts/morning.md`
and paste it every morning. Or wrap in a YAML plan
(`examples/templates/smoke.yaml` is close — fork it).

# 30-second demo GIF — recording script

Frame-by-frame plan for the launch-day demo GIF. Total wall-clock:
~12 minutes of setup + ~30 seconds of actual recording + 5 minutes
of editing. Produces a < 8 MB GIF that auto-plays inline on
LinkedIn.

## What the demo shows

A real Android phone (Galaxy S25 or Pixel emulator) under autonomous
agent control: select device → take screenshot → tap a labeled
button → verify the new screen → release. **Five visible tool
calls, five visible structured envelopes, one obvious "this is
real" moment when the phone actually moves.**

The constraint: must read on mute, no narration. Caption-hardcode
every key tool name into the recording so the value prop survives
LinkedIn's silent autoplay.

## Setup (~10 minutes, do this once)

### 1. Choose your device

Best signal-to-noise:

- **Real Galaxy S25** — most credibility, viewers see Samsung's
  One UI which signals "real production device, not a lab toy."
  Polish-locale buttons in the dialog (`Podczas używania
  aplikacji`) add a bonus "international ready" beat.
- **Pixel 8 emulator** — easier, no USB cable in the frame, still
  reads as a real Android device. Use if you don't have an S25
  handy.

The iPhone is harder for first demo because the iOS Settings UI
isn't visually distinctive enough on a small recording.

### 2. App under test

Easiest path: use the device's built-in Settings app — it's
guaranteed installed, has stable labels, and demonstrates that the
MCP isn't tied to a specific app. The Polish "Podczas używania
aplikacji" beat works against Settings' Location permission flow.

If you have a Flutter app ready, even better — open it instead and
demo `tap_and_verify` against a real Sign-in button.

### 3. Window layout

Two side-by-side windows that fit a 1920×1080 recording cleanly:

```
┌─────────────────────────────┬──────────────┐
│                             │              │
│  Claude Desktop             │   Device     │
│  (or Claude Code in VS)     │   mirror     │
│  640 × 1080                 │   (scrcpy    │
│                             │   on left;   │
│                             │   QuickTime  │
│                             │   on Mac)    │
│                             │              │
│                             │  500 × 1080  │
│                             │              │
│                             │              │
└─────────────────────────────┴──────────────┘
```

- **Claude window**: 640 wide, full height. Pre-zoom the font to
  18 px so labels read at GIF resolution.
- **Device mirror**: `scrcpy --window-borderless --max-size 1080`
  for Android, QuickTime `New Movie Recording → Camera: <iPhone>`
  for iOS.

### 4. Recording tool

| Tool | Output | Best for |
|---|---|---|
| **Kap** (free, macOS) | GIF or MP4 | One-click record + auto-compress |
| **CleanShot X** (paid) | GIF / MP4 / WebP | Best polish; cursor highlight + clicks |
| **macOS built-in** (cmd+shift+5) | MOV | Convert to GIF via `ffmpeg -i in.mov -vf "fps=15,scale=1280:-1:flags=lanczos" out.gif` |

Target: **15 fps, 1280 px wide, GIF, under 8 MB.** LinkedIn
auto-plays GIFs under 8 MB inline; over 8 MB it gates behind a
click-to-play.

## Recording script (~30 seconds)

**Pre-roll (0–2s) — context establishes:** screen shows the two
windows. Claude Desktop is open on a fresh chat. Device mirror
shows the home screen.

**The prompt (2–4s) — caption overlay reads "Real prompt typed
into Claude":** start typing this prompt at slow-but-not-slow pace
(don't paste — typing it on camera makes it credibly real):

```
Using phone-controll, run mcp_ping, then pick the connected
device, take a screenshot labeled "demo-1", tap "Settings", then
verify with a second screenshot. Release the device.
```

**Tool dispatch begins (4–10s) — caption overlay "5 tool calls,
fully autonomous":** Claude's "Calling tool…" indicators stream
visibly. The right pane (device mirror) doesn't move yet.

**The visible win (10–22s) — caption overlay reads "Real phone,
real taps":** the device mirror shows:

1. Home screen briefly (post `take_screenshot`).
2. Settings opens (post `tap`).
3. The second screenshot fires — you see Claude's preview unfurl
   it inline.

**Closing (22–28s) — caption overlay "110 tools. Apache 2.0.
github.com/michal-giza/flutter-dev-agents":** Claude's final
message renders ("✓ All steps complete, device released"). Both
windows visible.

**End-card (28–30s) — full-frame still:** the social preview PNG
from `docs/design/social-preview.png` shown for 2 seconds so the
GIF has a clean stopping point that's screenshottable.

## Captions to hardcode

Use the recording tool's caption feature (Kap supports this
natively). One caption per beat, large readable font:

| Time | Caption |
|---|---|
| 0–2s | (none — let the layout breathe) |
| 2–4s | "Real prompt typed into Claude" |
| 4–10s | "5 tool calls, fully autonomous" |
| 10–22s | "Real phone, real taps" |
| 22–28s | "110 tools. Apache 2.0." |
| 28–30s | "github.com/michal-giza/flutter-dev-agents" |

## Compressing to under 8 MB

If your raw recording is over 8 MB:

```bash
# Start at 15 fps, 1280 wide. If still too big, drop to 12 fps.
ffmpeg -i demo-raw.mov \
  -vf "fps=15,scale=1280:-1:flags=lanczos,palettegen=stats_mode=diff" \
  -y /tmp/palette.png

ffmpeg -i demo-raw.mov -i /tmp/palette.png \
  -lavfi "fps=15,scale=1280:-1:flags=lanczos [v]; [v][1:v] paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" \
  -y demo.gif

# Check size:
ls -lh demo.gif
```

If still over 8 MB, knock the width to 960 or fps to 12. Below
960 the tool-call labels stop being legible.

## What to do with the GIF

1. **Drop into the LinkedIn post** (drafted in the maintainer's private launch playbook).
   LinkedIn re-encodes; this is fine.
2. **Embed in the README** under a `<details>` tag so it doesn't
   weigh down the rendered page:
   ```markdown
   <details>
   <summary>📽️ 30-second demo (click to play)</summary>

   ![demo](docs/design/demo.gif)
   </details>
   ```
3. **Upload to the GitHub release** as a binary asset on the
   v0.2.2 release page.
4. **Twitter/X**: post the MP4 version (Twitter compresses GIFs
   poorly).

## If something goes wrong during recording

Common failure modes and recovery:

- **Phone goes to sleep mid-take**: pre-record, `adb shell svc
  power stayon true` to keep it awake.
- **Tap_text picks the wrong "Settings"** (there's a header and
  a row label): re-do the prompt with `exact=True`. The demo
  *should* show the discipline.
- **The `mcp_ping` returns an old version** (stale subprocess):
  fully quit Claude Desktop, relaunch, start over. This is the
  failure mode the demo demonstrates the MCP catches — don't
  paper over it.
- **Settings is in English on a Polish device**: that's actually
  *better* footage — switch to a Polish-labeled button mid-demo
  (e.g. *Ustawienia* if your Settings is localized) and the
  `tap_text` NBSP-fold story tells itself.

## Output checklist

- [ ] `demo.gif` ≤ 8 MB, 15 fps, 1280 px wide
- [ ] All 6 captions readable at 50% browser zoom
- [ ] Final frame is the social preview card (screenshottable)
- [ ] No personal data visible (notification badges, real phone
      number in the dialer, etc.)
- [ ] No timestamps visible that contradict the launch date
- [ ] Uploaded to: LinkedIn post / GitHub release / README embed

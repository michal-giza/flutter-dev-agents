# Brief 05 — 90-second demo video

## Goal

A short, no-voiceover-required loop that shows the product working
on a real phone. Hosted in the landing-page hero AND on the GitHub
README. Killer asset for social sharing.

## Audience

P1 (indie shipper) first — they're the ones who watch demos on
mute. P3 (agent-builder) second — they want to see the tool
envelopes.

## Format

- **Length**: 60-90 seconds. Hard cap at 100s.
- **Aspect**: 16:9, 1920×1080 (1080p). Vertical 9:16 crop also
  shipped for X/Twitter feed embeds.
- **Bitrate**: H.264, ~6 Mbps for the 1080p; ~3 Mbps for the
  vertical.
- **No sound required**. Captions hard-burned into the frame.
- **Auto-play, looped, muted** on the landing page; click for
  full-screen.

## The story (3 acts, 30 seconds each)

### Act 1 — "Real phone, real test" (0:00 – 0:30)

Visual: split-screen.
- LEFT: a Claude Code chat window. Text appears as if typed:
  > _"Smoke-test the latest build on my S25."_
- RIGHT: a Samsung S25 mounted on a desk stand, screen visible.

Agent reasons (1-2 line summary appears as caption near the bottom):
- "I'll boot up the build, install, then run the smoke plan."

Cuts to the agent calling:
```
> check_environment
> list_devices
> select_device(R3CYA05CHXB)
```

Each tool envelope flashes briefly on the LEFT, with the green
"ok: true" pulsing momentarily.

### Act 2 — "Autonomous test loop" (0:30 – 1:00)

Visual: the LEFT shows tool calls scrolling. The RIGHT shows the S25
booting the app, navigating, the agent tapping buttons that visibly
light up on the device.

The narration captions (still no voiceover):
- "It runs `prepare_for_test` to clean state…"
- "Then `run_test_plan smoke.yaml` against the device…"
- "Captures evidence with `take_screenshot`…"
- "Validates with `tap_and_verify` + `assert_no_errors_since`…"

Action on screen: ~5 fast cuts of the agent tapping things, the
device responding, screenshots being captured. Each screenshot
"pops" up briefly on the LEFT panel — small thumbnail in the
chat — then disappears.

### Act 3 — "Result + release" (1:00 – 1:30)

Visual: the agent's final reply scrolls into the LEFT chat:
```
> Smoke passed.
> 8/8 phases ok. Evidence in artifacts/20260518-…
> Released device R3CYA05CHXB.
```

The device on the RIGHT goes dark (the agent has stopped the app).

Final 5 seconds: the screen transitions to a single end-card with:
- Logo + wordmark
- Tagline: "Your factory of Flutter agents."
- URL: `flutter-dev-agents.dev` (or your domain)
- "★ Star us on GitHub" CTA

## What to film

You'll need:
- Samsung S25 (R3CYA05CHXB serial — already paired in your dev
  setup) on a tabletop stand, well-lit.
- A second camera angle on the laptop screen showing the Claude
  Code window.
- The actual smoke test running — record the live session, NOT a
  mock. Authenticity is the entire point.

## Editing notes

- Speed up between tool calls (1.5× – 2× during long install).
- Don't fake the latency. If `run_test_plan` takes 90 seconds, the
  video should be SHORTER than that — cut to the result without
  pretending the wall-clock was 30 s.
- Pulse the green "ok" envelope briefly — viewers should register
  the success signal even at 720p compressed.
- No music. Or if music, a single sub-bass drone that's at
  -24 dB and dies in the last 10 seconds. Most viewers will mute.
- Hard-burn captions in **JetBrains Mono 32px**, off-white, with a
  semi-transparent black background strip.

## Anti-patterns

- ❌ Stock office b-roll between cuts.
- ❌ "Hi, I'm Michal, today I'll show you…" intro. Cut straight
  to the work.
- ❌ Hand pointing at the phone screen. Show the phone reacting,
  not a human directing.
- ❌ Voiceover overlay on the tool calls. Captions are enough.
- ❌ Cinematic colour grade. The phone screen IS the colour.

## Deliverables

- `assets/demo-90s.mp4` (1920×1080, H.264, ~50 MB)
- `assets/demo-90s-vertical.mp4` (1080×1920 crop for socials)
- `assets/demo-poster.png` (the still that shows before play)
- `assets/demo-captions.srt` (open captions for accessibility)
- A 30-second cut for embed previews that need to be tiny

## Definition of done

- Loop reads without sound on a 720p compressed playback.
- Captions are legible at 480p (worst-case Twitter preview).
- The phone interaction is REAL — same serial R3CYA05CHXB, same
  Samsung S25, same MCP version (`mcp_ping.git_sha` visible in one
  frame for receipts).
- File size under 60 MB so the landing-page LCP budget survives.

## Claude / video-tool prompt

```
I have a real screen recording of:
1. A Claude Code chat where I asked it to smoke-test a Flutter
   app on my Samsung S25.
2. The Samsung S25 itself running the app while the agent drives it.

Edit these into a 60-90s product demo, 1920×1080, H.264, with
hard-burned captions (JetBrains Mono 32px, off-white on
semi-transparent black). No voiceover. Three acts:

Act 1 (0-30s): split-screen. Show me typing the prompt, then the
first 3-4 tool envelopes flashing with green "ok: true".

Act 2 (30-60s): tool calls scroll on the left, phone reacts on
the right. ~5 fast cuts. Each take_screenshot pops a small
thumbnail in the chat side.

Act 3 (60-90s): final summary message scrolls in, device goes
dark, end-card with logo + "Your factory of Flutter agents." +
flutter-dev-agents.dev + "★ Star us on GitHub".

No music or a single low drone at -24dB. No stock b-roll. Speed
up long installs to 1.5-2×.

Output: 1080p MP4, 9:16 vertical crop, poster PNG, .srt captions,
and a 30-second cut for tiny embeds.
```
